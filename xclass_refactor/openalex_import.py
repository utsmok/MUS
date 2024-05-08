
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
from xclass_refactor.constants import ROR, INSTITUTE_ALT_NAME, INSTITUTE_NAME, OPENALEX_INSTITUTE_ID
import asyncio
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
    def __init__(self,years:list[int]=None, openalex_requests:dict = None, ):
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
        if not years:
            self.years = [2018, 2019, 2020, 2021, 2022, 2023, 2024 , 2025]
        else:
            self.years = years
        self.mongoclient = MusMongoClient()
        self.results = {}
        self.init_pyalex()

    def init_pyalex(self):
        APIEMAIL = getattr(settings, "APIEMAIL", "no@email.com")
        pyalex.config.email = APIEMAIL
        pyalex.config.max_retries = 5
        pyalex.config.retry_backoff_factor = 0.2
        pyalex.config.retry_http_codes = [429, 500, 503]

    async def run(self):
        # make parallel/async/mp? -> No, api limit!
        from datetime import datetime
        results = []
        tasks = []
        for request in self.openalex_requests:
            if request == 'works_openalex':
                start = datetime.now()
                print('running OpenAlexQuery for works')
                res = await OpenAlexQuery(mongoclient=self.mongoclient, mongocollection=self.mongoclient.works_openalex, pyalextype='works', item_ids=self.requested_works, years=self.years).run()
                print(f'took {datetime.now()-start}')
                results.append(res)
            if request == 'authors_openalex':
                print('running OpenAlexQuery for authors')
                tasks.append(OpenAlexQuery(self.mongoclient, self.mongoclient.authors_openalex, 'authors', self.requested_authors).run())

            if request == 'sources_openalex':
                print('running OpenAlexQuery for sources')
                tasks.append(OpenAlexQuery(self.mongoclient, self.mongoclient.sources_openalex, 'sources', self.requested_sources).run())

            if request == 'funders_openalex':
                print('running OpenAlexQuery for funders')
                tasks.append(OpenAlexQuery(self.mongoclient, self.mongoclient.funders_openalex, 'funders', self.requested_funders).run())

            if request == 'institutions_openalex':
                print('running OpenAlexQuery for institutions')
                tasks.append(OpenAlexQuery(self.mongoclient, self.mongoclient.institutions_openalex, 'institutions', self.requested_institutions).run())

            if request == 'topics_openalex':

                print('running OpenAlexQuery for topics')
                tasks.append(OpenAlexQuery(self.mongoclient, self.mongoclient.topics_openalex, 'topics', self.requested_topics).run())

        result_group = asyncio.gather(*tasks)
        for result in result_group:
            results.append(result)

        return results
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
        self.results = []
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
                            institutions={"ror":ROR},
                            publication_year=year))
                else:
                    if not self.item_ids:
                        self.item_ids = []
                    authorlist = set()
                    sourcelist = set()
                    funderlist = set()
                    institutionlist = set()
                    topiclist = set()

                    # all other types: generate a list of ids extracted from available works
                    # then call add_query_by_ids to construct the batched queries
                    if self.pyalextype == 'authors':
                        async for work in self.mongoclient.works_openalex.find({}, projection={'authorships':1}, sort=[('authorships.0.author.id', 1)]):
                            if 'authorships' in work:
                                for authorship in work['authorships']:
                                    if 'institutions' in authorship:
                                        for institution in authorship['institutions']:
                                            if any([institution['ror'] == ROR,
                                            institution['id'] == OPENALEX_INSTITUTE_ID,
                                            INSTITUTE_NAME.lower() in institution['display_name'].lower(),
                                            INSTITUTE_ALT_NAME.lower() in institution['display_name'].lower()]):
                                                authorlist.add(authorship['author']['id'])
                                                break
                    if self.pyalextype == 'sources':
                        async for work in self.mongoclient.works_openalex.find({}, projection={'locations':1}, sort=[('locations.0.source.id', 1)]):
                            if 'locations' in work:
                                for location in work['locations']:
                                    try:
                                        if 'source' in location.keys():
                                            if location['source']:
                                                sourcelist.add(location['source']['id'])
                                    except AttributeError:
                                        pass
                    if self.pyalextype == 'funders':
                        async for work in self.mongoclient.works_openalex.find({}, projection={'grants':1}, sort=[('grants.0.funder.id', 1)]):
                            if 'grants' in work:
                                for grant in work['grants']:
                                    funderlist.add(grant['funder'])
                    if self.pyalextype == 'institutions':
                        async for work in self.mongoclient.works_openalex.find({}, projection={'authorships':1}, sort=[('authorships.0.institutions.0.id', 1)]):
                            for authorship in work['authorships']:
                                if 'institutions' in authorship:
                                    for institution in authorship['institutions']:
                                        institutionlist.add(institution['id'])
                    if self.pyalextype == 'topics':
                        async for work in self.mongoclient.works_openalex.find({}, projection={'topics':1}, sort=[('topics.0.id', 1)]):
                            if 'topics' in work:
                                for topic in work['topics']:
                                    topiclist.add(topic['id'])

                    for l in [authorlist, sourcelist, funderlist, institutionlist, topiclist]:
                        l=list(l)
                        if l:
                            print(f'found {len(l)} {self.pyalextype} ids')
                        for t in l:
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

    async def run(self) -> list:
        print(f'running {self.pyalextype}')
        if self.pyalextype == 'works' and not self.querylist:
            print(f'Getting works for {self.years}')
            for year in self.years:
                print(f'Getting works for year {year}')
                stop = False
                cursor = '*'
                amountperpage = 25
                while not stop:
                    try:
                        response = await self.httpxclient.get(f'https://api.openalex.org/works?filter=publication_year:{year},institutions.ror:{ROR}&per-page={amountperpage}&cursor={cursor}')
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
                    if json_r.get('results'):
                        print(f'got {len(json_r["results"])} openalex work results for year {year}')
                        for item in json_r['results']:
                            await self.collection.find_one_and_update({"id":item['id']}, {'$set':item}, upsert=True)
                            self.results.append(item['id'])
        else:
            if not self.querylist:
                print(f'adding default queries for {self.pyalextype}')
                await self.add_to_querylist()
            if not self.querylist:
                print(f'no queries to run for {self.pyalextype}.')
                return self.results
            print(f'running queries for {self.pyalextype}')
            for i, query in enumerate(self.querylist):
                querynum=i+1
                print(f'running query {querynum} of {len(self.querylist)} of {self.pyalextype}')
                try:
                    for item in chain(*query.paginate(per_page=100, n_max=None)):
                            updt =await self.collection.find_one_and_update({"id":item['id']}, {'$set':item}, upsert=True)
                            if updt:
                                if updt['updated_date']==item['updated_date']:
                                    self.results.append(item['id'])
                except Exception as e:
                    print(f'error {e} while retrieving {self.pyalextype}')
                    continue
        print(f'finished {self.pyalextype}, added/updated {len(self.results)} {self.pyalextype}')

        return {'results':self.results,'type':self.pyalextype}
