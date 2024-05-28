
from itertools import chain
from typing import Iterable
import pyalex
from xclass_refactor.mus_mongo_client import MusMongoClient
from pyalex import Authors, Funders, Institutions, Sources, Works, Topics, Publishers
from pyalex.api import BaseOpenAlex
from rich.console import Console

import httpx
import motor.motor_asyncio
from xclass_refactor.constants import APIEMAIL, ROR, INSTITUTE_ALT_NAME, INSTITUTE_NAME, OPENALEX_INSTITUTE_ID
import asyncio

cons = Console(markup=True)
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
                'topics_openalex': None,
                'publishers_openalex': None
            }
        self.requested_works = self.openalex_requests.get('works_openalex')
        self.requested_authors = self.openalex_requests.get('authors_openalex')
        self.requested_sources = self.openalex_requests.get('sources_openalex')
        self.requested_funders = self.openalex_requests.get('funders_openalex')
        self.requested_institutions = self.openalex_requests.get('institutions_openalex')
        self.requested_topics = self.openalex_requests.get('topics_openalex')
        self.requested_publishers = self.openalex_requests.get('publishers_openalex')
        if not years:
            self.years = [2022, 2023, 2024 , 2025]
        else:
            self.years = years
        self.mongoclient = MusMongoClient()
        self.init_pyalex()

    def init_pyalex(self):
        pyalex.config.email = APIEMAIL
        pyalex.config.max_retries = 5
        pyalex.config.retry_backoff_factor = 0.2
        pyalex.config.retry_http_codes = [429, 500, 503]

    async def run(self):
        from datetime import datetime
        results = []
        tasks = []
        tasks2 = []
        for request in self.openalex_requests:
            if request == 'works_openalex':
                start = datetime.now()
                cons.print('running OpenAlexQuery for works')
                res = await OpenAlexQuery(mongoclient=self.mongoclient, mongocollection=self.mongoclient.works_openalex, pyalextype='works', item_ids=self.requested_works, years=self.years).run()
                cons.print(f'took {datetime.now()-start}')
                results.append(res)
            if request == 'authors_openalex':
                cons.print('running OpenAlexQuery for authors')
                tasks.append(OpenAlexQuery(self.mongoclient, self.mongoclient.authors_openalex, 'authors', self.requested_authors).run())
            if request == 'non_institution_authors_openalex':
                cons.print('running OpenAlexQuery for non-institution authors')
                tasks.append(OpenAlexQuery(self.mongoclient, self.mongoclient.non_instution_authors_openalex, 'authors', self.requested_authors).run())
            if request == 'sources_openalex':
                cons.print('running OpenAlexQuery for sources')
                tasks.append(OpenAlexQuery(self.mongoclient, self.mongoclient.sources_openalex, 'sources', self.requested_sources).run())
            if request == 'funders_openalex':
                cons.print('running OpenAlexQuery for funders')
                tasks.append(OpenAlexQuery(self.mongoclient, self.mongoclient.funders_openalex, 'funders', self.requested_funders).run())
            if request == 'institutions_openalex':
                cons.print('running OpenAlexQuery for institutions')
                tasks.append(OpenAlexQuery(self.mongoclient, self.mongoclient.institutions_openalex, 'institutions', self.requested_institutions).run())
            if request == 'topics_openalex':
                cons.print('running OpenAlexQuery for topics')
                tasks.append(OpenAlexQuery(self.mongoclient, self.mongoclient.topics_openalex, 'topics', self.requested_topics).run())
            if request == 'publishers_openalex':
                cons.print('running OpenAlexQuery for publishers')
                tasks2.append(OpenAlexQuery(self.mongoclient, self.mongoclient.publishers_openalex, 'publishers', self.requested_publishers).run())

        results2 = await asyncio.gather(*tasks)
        results3 = await asyncio.gather(*tasks2)
        if not isinstance(results, list):
            results2 = [results]
        if isinstance(results, list):
            results.extend(results2)
        if not results:
            results = results2
        results.extend(results3)

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

    def __init__(self, mongoclient:MusMongoClient, mongocollection:motor.motor_asyncio.AsyncIOMotorCollection, pyalextype:str, item_ids:Iterable[str]=None, years:list[int]=[2019, 2020, 2021, 2022, 2023, 2024 , 2025]):
        self.mongoclient:MusMongoClient = mongoclient
        self.collection:motor.motor_asyncio.AsyncIOMotorCollection = mongocollection
        self.item_ids:Iterable[str]  = item_ids
        self.non_institution_authors: Iterable[str] = []
        self.querylist:list[BaseOpenAlex] = []
        self.years = years
        self.httpxclient : httpx.AsyncClient = httpx.AsyncClient()
        if self.collection == self.mongoclient.non_instution_authors_openalex:
            self.only_institute = False
        else:
            self.only_institute = True
        self.pyalexmapping = {
            'works': Works,
            'authors': Authors,
            'sources': Sources,
            'funders': Funders,
            'institutions': Institutions,
            'topics': Topics,
            'publishers': Publishers
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
                self.add_query_by_ids(self.item_ids)
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
                    publisherlist = set()
                    # all other types: generate a list of ids extracted from available works
                    # then call add_query_by_ids to construct the batched queries
                    if self.pyalextype == 'authors':
                        async for work in self.mongoclient.works_openalex.find({}, projection={'authorships':1}, sort=[('authorships', 1)]):
                            if 'authorships' in work:
                                for authorship in work['authorships']:
                                    if not self.only_institute:
                                        authorlist.add(authorship['author']['id'])
                                    elif 'institutions' in authorship:
                                        for institution in authorship['institutions']:
                                            if any([institution['ror'] == ROR,
                                            institution['id'] == OPENALEX_INSTITUTE_ID,
                                            INSTITUTE_NAME.lower() in institution['display_name'].lower(),
                                            institution['display_name'].lower() in [name.lower() for name in INSTITUTE_ALT_NAME]]):
                                                authorlist.add(authorship['author']['id'])
                                                break

                    if self.pyalextype == 'sources':
                        async for work in self.mongoclient.works_openalex.find({}, projection={'locations':1}, sort=[('locations', 1)]):
                            if 'locations' in work:
                                for location in work['locations']:
                                    try:
                                        if 'source' in location.keys():
                                            if location['source']:
                                                sourcelist.add(location['source']['id'])
                                    except AttributeError:
                                        pass
                    if self.pyalextype == 'funders':
                        async for work in self.mongoclient.works_openalex.find({}, projection={'grants':1}, sort=[('grants', 1)]):
                            if 'grants' in work:
                                for grant in work['grants']:
                                    funderlist.add(grant['funder'])
                    if self.pyalextype == 'institutions':
                        async for work in self.mongoclient.works_openalex.find({}, projection={'authorships':1}, sort=[('authorships', 1)]):
                            for authorship in work['authorships']:
                                if 'institutions' in authorship:
                                    for institution in authorship['institutions']:
                                        institutionlist.add(institution['id'])
                    if self.pyalextype == 'topics':
                        async for work in self.mongoclient.works_openalex.find({}, projection={'topics':1}, sort=[('topics', 1)]):
                            if 'topics' in work:
                                for topic in work['topics']:
                                    topiclist.add(topic['id'])
                    if self.pyalextype == 'publishers':
                        async for work in self.mongoclient.sources_openalex.find({}, projection={'host_organization_lineage':1}, sort=[('host_organization_lineage', 1)]):
                            for item in work['host_organization_lineage']:
                                if str(item).startswith('https://openalex.org/P'):
                                    publisherlist.add(item)

                    for l in [authorlist, sourcelist, funderlist, institutionlist, topiclist, publisherlist]:
                        l=list(l)
                        if l:
                            cons.print(f'found {len(l)} {self.pyalextype} ids')
                        for t in l:
                            if not await self.collection.find_one({'id':t}):
                                self.item_ids.append(t)

                    cons.print(f'{len(self.item_ids)} {self.pyalextype} ids remaining after filtering')
                    if self.item_ids:
                        self.add_query_by_ids(self.item_ids)
        else:
            # query is provided: just add to the list
            if not isinstance(query, list):
                self.querylist.append(query)
            else:
                self.querylist.extend(query)

    def add_query_by_ids(self, item_ids:Iterable[str]=None) -> bool:
        '''
        creates queries for all ids in item_ids for the itemtype of this instance of OpenAlexQuery
        '''

        batch = []
        for id in item_ids:
            batch.append(id)
            if len(batch) == 50:
                itemids="|".join(batch)
                if not self.pyalextype == 'publishers':
                    self.querylist.append(self.pyalexmapping[self.pyalextype]().filter(openalex=itemids))
                else:
                    self.querylist.append(self.pyalexmapping[self.pyalextype]().filter(ids={'openalex':itemids}))
                batch = []
        itemids="|".join(batch)
        self.querylist.append(self.pyalexmapping[self.pyalextype]().filter(openalex=itemids))



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
        cons.print(f'running {self.pyalextype}')
        if self.pyalextype == 'works' and not self.querylist:
            cons.print(f'Getting works for {self.years}')
            for year in self.years:
                cons.print(f'Getting works for year {year}')
                stop = False
                cursor = '*'
                amountperpage = 25
                while not stop:
                    try:
                        response = await self.httpxclient.get(f'https://api.openalex.org/works?filter=publication_year:{year},institutions.ror:{ROR}&per-page={amountperpage}&cursor={cursor}')
                    except Exception as e:
                        cons.print(f'error {e} while getting response, retrying with less papers per page')
                        amountperpage = amountperpage-5
                        if amountperpage < 5:
                            cons.print('too many retries, stopping this iteration')
                            stop = True
                            continue
                        continue
                    if response.status_code == 403 and 'pagination' in str(response.content).lower():
                        stop = True
                        continue
                    if response.status_code == 503 or response.status_code == 473:
                        cons.print('503 or 473 error, retrying with less papers per page')
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
                            cons.print(f'error {e} while getting json')
                            break
                    if json_r.get('results'):
                        for item in json_r['results']:
                            updt = await self.collection.find_one_and_update({"id":item['id']}, {'$set':item}, upsert=True)
                            if updt:
                                if updt['updated_date']!=item['updated_date']:
                                    self.results.append(item['id'])
        else:
            if not self.querylist:
                cons.print(f'adding default queries for {self.pyalextype}')
                await self.add_to_querylist()
            if not self.querylist:
                cons.print(f'no queries to run for {self.pyalextype}.')
                return {'results':self.results,'type':self.pyalextype}
            cons.print(f'running queries for {self.pyalextype}')
            for i, query in enumerate(self.querylist):
                querynum=i+1
                cons.print(f'running query {querynum} of {len(self.querylist)} of {self.pyalextype}')
                try:
                    for item in chain(*query.paginate(per_page=100, n_max=None)):
                            updt = await self.collection.find_one_and_update({"id":item['id']}, {'$set':item}, upsert=True)
                            if updt:
                                self.results.append(item['id'])
                except Exception as e:
                    cons.print(f'error {e} while retrieving {self.pyalextype}')
                    continue
        cons.print(f'finished {self.pyalextype}, added/updated {len(self.results)} {self.pyalextype}')

        return {'results':self.results,'type':self.pyalextype}
