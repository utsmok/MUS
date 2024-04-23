
from itertools import chain
from typing import Iterable
from django.conf import settings
import pyalex
from xclass_refactor.mus_mongo_client import MusMongoClient
from pyalex import Authors, Funders, Institutions, Sources, Works, Topics
from pyalex.api import BaseOpenAlex
from rich import print
import httpx
from collections import defaultdict
import motor.motor_asyncio

class OpenAlexAPI():
    '''
    class to get data from the OpenAlex API and store it in MongoDB

    Parameters
    ----------
    openalex_requests: dict
    default: all
        a dict containing which itemtypes to retrieve from OpenAlex
    years: list
    default: [2023,2024,2025]
        the publication years of the works to retrieve

    mongoclient: MusMongoClientq

    '''
    def __init__(self, openalex_requests:dict, years:list[int], mongoclient: MusMongoClient):
        if openalex_requests:
            self.openalex_requests = openalex_requests
        else:
            self.openalex_requests = {
                'works_openalex': None,
                'authors_openalex': None,
                'sources_openalex': None,
                'funders_openalex': None,
                'institutions_openalex': None,
                'topics_openalex': None
            }
        self.requested_works = self.openalex_requests.get('works_openalex')
        self.requested_authors = self.openalex_requests.get('authors_openalex')
        self.requested_sources = self.openalex_requests.get('sources_openalex')
        self.requested_funders = self.openalex_requests.get('funders_openalex')
        self.requested_institutions = self.openalex_requests.get('institutions_openalex')
        self.requested_topics = self.openalex_requests.get('topics_openalex')
        self.years = years
        self.mongoclient = mongoclient
        self.results = {}
        self.init_pyalex()

    def init_pyalex(self):
        APIEMAIL = getattr(settings, "APIEMAIL", "no@email.com")
        pyalex.config.email = APIEMAIL
        pyalex.config.max_retries = 5
        pyalex.config.retry_backoff_factor = 0.2
        pyalex.config.retry_http_codes = [429, 500, 503]

    def run(self):
        # make parallel/async/mp?
        for request in self.openalex_requests:
            if request == 'works_openalex':
                print('running OpenAlexQuery for works')
                OpenAlexQuery(mongoclient=self.mongoclient, mongocollection=self.mongoclient.works_openalex, pyalextype='works', item_ids=self.requested_works, years=self.years).run()
            if request == 'authors_openalex':
                print('running OpenAlexQuery for authors')
                OpenAlexQuery(self.mongoclient, self.mongoclient.authors_openalex, 'authors', self.requested_authors).run()
            if request == 'sources_openalex':
                print('running OpenAlexQuery for sources')
                OpenAlexQuery(self.mongoclient, self.mongoclient.sources_openalex, 'sources', self.requested_sources).run()
            if request == 'funders_openalex':
                print('running OpenAlexQuery for funders')
                OpenAlexQuery(self.mongoclient, self.mongoclient.funders_openalex, 'funders', self.requested_funders).run()
            if request == 'institutions_openalex':
                print('running OpenAlexQuery for institutions')
                OpenAlexQuery(self.mongoclient, self.mongoclient.institutions_openalex, 'institutions', self.requested_institutions).run()
            if request == 'topics_openalex':
                print('running OpenAlexQuery for topics')
                OpenAlexQuery(self.mongoclient, self.mongoclient.topics_openalex, 'topics', self.requested_topics).run()
class OpenAlexQuery():
    '''
    Generic class to query OpenAlex and store results in MongoDB

    Parameters
    ----------
    mongoclient: MusMongoClient - a client to the MongoDB database
    mongocollection: Collection - the primary collection to store results in for this item
    pyalextype: BaseOpenAlex - the pyalex type to query; e.g. Works, Authors, Sources, Funders, Institutions
    item_ids: Iterable[str] - a list of item_ids to query; if None, will use the default query for the itemtype

    Functions
    ---------
    add_to_querylist(query) - adds a query to the list of queries to run. if no query is provided, it will add default queries for the itemtype
    run() - runs the query and updates the database, if no queries are initialized, it calls add_to_querylist() to add default queries based on itemtype

    '''
    def __init__(self, mongoclient:MusMongoClient, mongocollection:motor.motor_asyncio.AsyncIOMotorCollection, pyalextype:str, item_ids:Iterable[str]=None, years:list[int]=[2023,2024,2025]):
        self.mongoclient:MusMongoClient = mongoclient
        self.collection:motor.motor_asyncio.AsyncIOMotorCollection = mongocollection
        self.item_ids:Iterable[str]  = item_ids
        if self.item_ids:
            self.set_query()
        self.querylist:list[BaseOpenAlex] = []
        self.years = years
        self.httpxclient : httpx.AsyncClient = httpx.AsyncClient()

        self.pyalexmapping = {
            'works': Works,
            'authors': Authors,
            'sources': Sources,
            'funders': Funders,
            'institutions': Institutions,
            'topics': Topics
        }
        self.pyalextype = pyalextype

    async def add_to_querylist(self,query: BaseOpenAlex=None) -> None:
        '''
        adds the pyalex query to the list of queries to run for this itemtype
        if no query is provided, it will add a default query for the itemtype
        '''
        if not query:
            # first try making query using item_ids if provided
            if self.item_ids:
                self.add_query_by_ids()
            else:
                # no item_ids, no query: make default query for itemtype
                if self.pyalextype == 'works':
                    # works have a single default query
                    for year in self.years:
                        self.querylist.append(Works().filter(
                            institutions={"ror":"https://ror.org/006hf6230"},
                            publication_year=year))
                else:
                    if not self.item_ids:
                        self.item_ids = []
                    templist = []

                    # all other types: generate a list of ids extracted from available works
                    # then call add_query_by_ids to construct the batched queries
                    if self.pyalextype == 'authors':
                        async for work in self.mongoclient.works_openalex.find():
                            if 'authorships' in work:
                                for authorship in work['authorships']:
                                    if 'institutions' in authorship:
                                        for institution in authorship['institutions']:
                                            if institution['ror'] == 'https://ror.org/006hf6230' \
                                            or institution['id'] == 'https://openalex.org/I94624287' \
                                            or 'twente' in institution['display_name'].lower():
                                                templist.append(authorship['author']['id'])
                                                break

                    elif self.pyalextype == 'sources':
                        async for item in self.mongoclient.works_openalex.find():
                            if 'locations' in item:
                                for location in item['locations']:
                                    try:
                                        if 'source' in location.keys():
                                            if location['source']:
                                                templist.append(location['source']['id'])
                                    except AttributeError:
                                        pass

                    elif self.pyalextype == 'funders':
                        async for item in self.mongoclient.works_openalex.find():
                            if 'grants' in item:
                                for grant in item['grants']:        
                                    templist.append(grant['funder'])

                    elif self.pyalextype == 'institutions':
                        async for item in self.mongoclient.works_openalex.find():
                            for authorship in item['authorships']:
                                if 'institutions' in authorship:
                                    for institution in authorship['institutions']:
                                        templist.append(institution['id'])
                    elif self.pyalextype == 'topics':
                        async for item in self.mongoclient.works_openalex.find():
                            if 'topics' in item:
                                for topic in item['topics']:
                                    templist.append(topic['id'])
                    # process the ids in templist: remove dupes and items already in collection, 
                    # then build the queries
                    templist=list(set(templist))
                    print(f'found {len(templist)} {self.pyalextype} ids')
                    for t in templist:
                        if not await self.collection.find_one({'id':t}):
                            self.item_ids.append(t)
                    print(f'{len(self.item_ids)} {self.pyalextype} ids remaining after filtering')
                    if self.item_ids:
                        self.add_query_by_ids()
        else:
            # query is provided: just add to the list
            if not isinstance(query, list):
                self.querylist.append(query)
            else:
                self.querylist.extend(query)

    def add_query_by_ids(self) -> bool:
        '''
        creates queries for all ids in self.item_ids for the itemtype of this instance of OpenAlexQuery
        if self.item_ids is empty it will return False
        '''
        if self.item_ids:
            batch = []
            for id in self.item_ids:
                batch.append(id)
                if len(batch) == 50:
                    itemids="|".join(batch)
                    self.querylist.append(self.pyalexmapping[self.pyalextype]().filter(openalex=itemids))
                    batch = []
            itemids="|".join(batch)
            self.querylist.append(self.pyalexmapping[self.pyalextype]().filter(openalex=itemids))
        else:
            raise Exception(f'no item_ids present in this instance of OpenAlexQuery for {self.pyalextype}')
    def add_query_by_orcid(self, orcids:list[str]) -> None:
        '''
        from a list of orcids, create queries for this instance of OpenAlexQuery
        '''
        if not self.pyalextype == 'authors':
            raise Exception('add_query_by_orcid only works for authors')
        batch = []
        for orcid in orcids:
            batch.append(orcid)
            if len(batch) == 50:
                orcid_batch="|".join(batch)
                self.querylist.append(self.pyalexmapping[self.pyalextype]().filter(orcid=orcid_batch))
                batch = []
        orcid_batch="|".join(batch)
        self.querylist.append(self.pyalexmapping[self.pyalextype]().filter(orcid=orcid_batch))

    async def run(self) -> None:
            print(f'running {self.pyalextype}')
            if self.pyalextype == 'works' and not self.querylist:
                added = defaultdict(int)
                async for year in self.years:
                    stop = False
                    cursor = '*'
                    amountperpage = 25
                    while not stop:
                        try:
                            response = await self.httpxclient.get(f'https://api.openalex.org/works?filter=publication_year:{year},institutions.ror:https://ror.org/006hf6230&per-page={amountperpage}&cursor={cursor}')
                        except Exception as e:
                            print(f'error {e} while getting response, retrying with less papers per page')
                            amountperpage = amountperpage-5
                            if amountperpage < 5:
                                print('too many retries, stopping this iteration')
                                stop = True
                                continue
                            continue
                        if response.status_code == 403 and 'pagination' in str(response.content).lower():
                            stop = True
                            continue
                        if response.status_code == 503 or response.status_code == 473:
                            print('503 or 473 error, retrying with less papers per page')
                            amountperpage = amountperpage-5
                            if amountperpage < 1:
                                amountperpage = 1
                            continue
                        amountperpage = 25
                        try:
                            json_r = response.json()
                            cursor = json_r['meta']['next_cursor']
                        except Exception as e:
                            if json_r.get('error'):
                                if json_r['error'] == 'Pagination error.':
                                    stop = True
                                    continue
                            else:
                                print(f'error {e} while getting json')
                                break
                        items=[]
                        if json_r.get('results'):
                            async for item in json_r['results']:
                                if not await self.collection.find_one({"id":item['id']}):
                                    items.append(item)
                            if items:
                                await self.collection.insert_many(items)
                                added[year] += len(items)
                    print(added)
            else:
                if not self.querylist:
                    print('adding default queries')
                    self.mongoclient.call_async(self.add_to_querylist())
                if not self.querylist:
                    print(f'no queries to run for {self.pyalextype}.')
                    return
                print('running queries')
                for i, query in enumerate(self.querylist):
                    querynum=i+1
                    print(f'running query {querynum} of {len(self.querylist)} of {self.pyalextype}')
                    try:
                        for item in chain(*query.paginate(per_page=100, n_max=None)):
                                await self.collection.find_one_and_update({"id":item['id']}, {'$set':item}, upsert=True)
                    except Exception as e:
                        print(f'error {e} while retrieving {self.pyalextype}')
                        continue
