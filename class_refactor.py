'''
temporary file

refactoring all the functions in mus_backend for retrieving items from apis, scrapers etc 
-> from function-based into class-based

instead of calling the functions one after another we'll use classes to manage it all

main structure:
-> base class that manages the current update process
-> creates instances of all kinds of other classes that will hold/retrieve the data
-> take note that we want to bundle api calls and db operations in batches instead of one at a time


implement some multiprocessing/threading/asyncio where it makes sense

import multiprocessing as mp
from concurrent.futures import ProcessPoolExecutor

'''
from pymongo import MongoClient
from pymongo.collection import Collection
from django.conf import settings
import pyalex
from pyalex import Works, Authors, Sources, Funders,  Institutions
from itertools import chain
from loguru import logger
from typing import Iterable
from pyalex.api import BaseOpenAlex
from habanero import Crossref


class MusMongoClient:
    '''
    creates connections to mongodb
    stores references to the relevant collections as attributes
    wraps search and update functions
    '''
    def __init__(self):
        MONGOURL = getattr(settings, "MONGOURL")
        self.mongoclient = MongoClient(MONGOURL)['metadata_unificiation_system']
        
        self.works_openalex = self.mongoclient['works_openalex']
        self.authors_openalex = self.mongoclient['authors_openalex']
        self.sources_openalex = self.mongoclient['sources_openalex']
        self.funders_openalex = self.mongoclient['funders_openalex']
        self.topics_openalex = self.mongoclient['topics_openalex']
        self.institutions_openalex = self.mongoclient['institutions_openalex']

        self.items_pure_oaipmh = self.mongoclient['items_pure_oaipmh']
        self.items_pure_reports = self.mongoclient['items_pure_reports']
        self.items_datacite = self.mongoclient['items_datacite']
        self.items_crossref = self.mongoclient['items_crossref']
        self.items_openaire = self.mongoclient['items_openaire']
        self.items_zenodo = self.mongoclient['items_zenodo']
        self.items_semantic_scholar = self.mongoclient['items_semantic_scholar']

        self.deals_journalbrowser = self.mongoclient['deals_journalbrowser']
        self.employees_peoplepage = self.mongoclient['employees_peoplepage']

class UpdateManager:
    def __init__(self, years: list[int], include: dict):
        '''
        years: the publication years of the items to retrieve
        include: a dict detailing which apis/scrapes to run.
            default: 
            {
                'works_openalex': True,
                'items_pure_oaipmh': True,
            }
            instead of True, you can also pass a list of ids to retrieve from that api as a value instead.
            e.g. {'works_openalex': ['https://openalex.org/W2105846236', 'https://openalex.org/W2105846237'], 'items_pure_oaipmh': True}
            '''

        if not include:
            include = {
                'works_openalex': True,
                'authors_openalex': True,
                'items_pure_oaipmh': True,
            }

        self.years = years
        self.include = include
        self.mongoclient = MusMongoClient()
        self.results = {}
        self.queries = []

    def run(self):
        '''
        runs the queries based on the include dict
        '''
        print(self.include)
        openalex_results = ['works_openalex', 'authors_openalex', 'sources_openalex', 'funders_openalex', 'institutions_openalex', 'topics_openalex']
        if not self.include.keys():
            raise KeyError('dict UpdateManager.include is empty or invalid -- no updates to run.')
        openalex_requests = {}
        for key,item in self.include.items():
            if key in openalex_results:
                if not isinstance(item, list):
                    openalex_requests[key]=None
                else:
                    openalex_requests[key]=item
    
        if openalex_requests:
            print('running openalex')
            OpenAlexAPI(openalex_requests, self.years, self.mongoclient).run()
        if self.include.get('items_pure_oaipmh'):
            self.queries.append(PureAPI(self.years, self.mongoclient))
        if self.include.get('items_pure_reports'):
            self.queries.append(PureReports(self.mongoclient))
        if self.include.get('items_datacite'):
            self.queries.append(DataCiteAPI(self.mongoclient))
        if self.include.get('items_crossref'):
            print('running crossref')
            CrossrefAPI(self.years, self.mongoclient).run()
        if self.include.get('items_openaire'):
            self.queries.append(OpenAIREAPI(self.mongoclient))
        if self.include.get('items_zenodo'):
            self.queries.append(ZenodoAPI(self.mongoclient))
        if self.include.get('items_semantic_scholar'):
            self.queries.append(SemanticScholarAPI(self.mongoclient))
        if self.include.get('deals_journalbrowser'):
            self.queries.append(JournalBrowserScraper(self.mongoclient))
        if self.include.get('employees_peoplepage'):
            self.queries.append(PeoplePageScraper(self.mongoclient))

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
        pyalex.config.retry_backoff_factor = 0.4
        pyalex.config.retry_http_codes = [429, 500, 503]

    def run(self):
        # make parallel/async/mp?
        for request in self.openalex_requests:
            if request == 'works_openalex':
                OpenAlexQuery(mongoclient=self.mongoclient, mongocollection=self.mongoclient.works_openalex, pyalextype='works', item_ids=self.requested_works, years=self.years).run()
            if request == 'authors_openalex':
                OpenAlexQuery(self.mongoclient, self.mongoclient.authors_openalex, 'authors', self.requested_authors).run()
            if request == 'sources_openalex':
                OpenAlexQuery(self.mongoclient, self.mongoclient.sources_openalex, 'sources', self.requested_sources).run()
            if request == 'funders_openalex':
                OpenAlexQuery(self.mongoclient, self.mongoclient.funders_openalex, 'funders', self.requested_funders).run()
            if request == 'institutions_openalex':
                OpenAlexQuery(self.mongoclient, self.mongoclient.institutions_openalex, 'institutions', self.requested_institutions).run()

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
    def __init__(self, mongoclient:MusMongoClient, mongocollection:Collection, pyalextype:str, item_ids:Iterable[str]=None, years:list[int]=[2023,2024,2025]):
        self.mongoclient:MusMongoClient = mongoclient
        self.collection:Collection = mongocollection
        self.item_ids:Iterable[str]  = item_ids
        if self.item_ids:
            self.set_query()
        self.querylist:list[BaseOpenAlex] = []
        self.years = years

        self.pyalexmapping = {
            'works': Works,
            'authors': Authors,
            'sources': Sources,
            'funders': Funders,
            'institutions': Institutions
        }
        self.pyalextype = pyalextype
        
    def add_to_querylist(self,query: BaseOpenAlex=None) -> None:
        '''
        adds the pyalex query to the list of queries to run for this itemtype
        if no query is provided, it will add a default query for the itemtype
        '''
        if not query:
            # first try making query using item_ids if provided
            by_ids = self.add_query_by_ids() 
            if not by_ids:
                # no item_ids, no query: make default query for itemtype
                if self.pyalextype == 'works':
                    # works have a single default query
                    self.querylist.append(Works().filter(
                        institutions={"ror":"https://ror.org/006hf6230"},
                        publication_year="|".join([str(x) for x in self.years])
                    ))
                else:
                    # all other types: generate a list of ids extracted from available works
                    # then call add_query_by_ids to construct the batched queries
                    if self.pyalextype == 'authors':
                        if not self.item_ids:
                            self.item_ids = []
                        for work in self.mongoclient.works_openalex.find():
                            if 'authorships' in work:
                                for authorship in work['authorships']:
                                    if 'institutions' in authorship:
                                        for institution in authorship['institutions']:
                                            if institution['ror'] == 'https://ror.org/006hf6230' \
                                            or institution['id'] == 'https://openalex.org/I94624287' \
                                            or 'twente' in institution['display_name'].lower():
                                                self.item_ids.append(authorship['author']['id'])
                                                break
                        self.item_ids=list(set(self.item_ids))
                    elif self.pyalextype == 'sources':
                        # note: only retrieves journals, not all sources
                        if not self.item_ids:
                            self.item_ids = []
                        elif not isinstance(self.item_ids, list):
                            self.item_ids = [self.item_ids]
                        for item in self.mongoclient.works_openalex.find():
                            if 'locations' in item:
                                for location in item['locations']:
                                    try:
                                        if 'source' in location.keys():
                                            if 'type' in location['source'].keys():
                                                if location['source']['type']=='journal':
                                                    self.item_ids.append(location['source']['id'])
                                    except AttributeError:
                                        pass
                        self.item_ids=list(set(self.item_ids))
                    elif self.pyalextype == 'funders':
                        self.add_funder_query()
                    elif self.pyalextype == 'institutions':
                        self.add_institution_query()
                    
                    self.add_query_by_ids()
        else:
            # query is provided: add to list
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
            return True
        else:
            return False

    def run(self) -> None:
            if not self.querylist:
                self.add_to_querylist()
            for query in self.querylist:
                for item in chain(*query.paginate(per_page=100, n_max=None)):
                    self.collection.find_one_and_update({"id":item['id']}, {'$set':item}, upsert=True)

class PureAPI():
    def __init__(self, years, mongoclient):
        self.years = years
        self.mongoclient = mongoclient
        self.results = {}

class PureReports():
    def __init__(self, mongoclient):
        self.mongoclient = mongoclient
        self.results = {}

class DataCiteAPI():
    def __init__(self, mongoclient):
        self.mongoclient = mongoclient
        self.results = {}

class CrossrefAPI():
    def __init__(self, years: list = [2023, 2024, 2025], mongoclient: MusMongoClient = None, dois: list[str] = None):
        self.mongoclient = mongoclient
        if not self.mongoclient:
            self.mongoclient = MusMongoClient()
        self.collection = mongoclient.items_crossref
        self.results = []
        self.crossref = Crossref(mailto=APIEMAIL)
        self.pagesize=100
        self.dois = dois
        self.years = years
    def get_results(self):
        if not self.dois:
            print('getting default queries for crossref')
            self.results.append(self.crossref.works(filter = {'from-pub-date':f'{self.years[-1]}-01-01','until-pub-date': f'{self.years[0]}-12-31'}, query_affiliation='twente', cursor = "*", limit = self.pagesize, cursor_max=100000))
            self.dois = [str(x['doi']).replace('https://doi.org/','') for x in self.mongoclient.works_openalex.find()]
            print(f'found {len(self.dois)} dois')
            print('ONLY GETTING FIRST 100 DOIS')
            for doi in self.dois[:100]:
                try:
                    self.results.append(self.crossref.works(ids=doi))
                except Exception as e:
                    pass
            print(f'prepared {len(self.results)} crossref queries')
        else:
            self.results.append(self.crossref.works(ids=self.dois, cursor = "*", limit = self.pagesize, cursor_max=100000))
            pass
    def store_results(self):
        if not self.results:
            raise Warning('CrossrefAPI instance has no results to store')
        else:
            for result in self.results:
                articles = []
                if isinstance(result, list):
                    for page in result:
                        for article in page['message']['items']:
                            articles.append(article)
                else:
                    for article in page['message']['items']:
                        articles.append(article)
                for article in articles:
                    self.collection.find_one_and_update({"DOI":article['doi']}, {'$set':article}, upsert=True)
    def run(self):
        self.get_results()
        self.store_results()

class OpenAIREAPI():
    def __init__(self, mongoclient):
        self.mongoclient = mongoclient
        self.results = {}

class ZenodoAPI():
    def __init__(self, mongoclient):
        self.mongoclient = mongoclient
        self.results = {}

class SemanticScholarAPI():
    def __init__(self, mongoclient):
        self.mongoclient = mongoclient
        self.results = {}

class JournalBrowserScraper():
    def __init__(self, mongoclient):
        self.mongoclient = mongoclient
        self.results = {}

class PeoplePageScraper():
    def __init__(self, mongoclient):
        self.mongoclient = mongoclient
        self.results = {}


def main():
    mngr = UpdateManager([2023,2024,2025], {'items_crossref': True})
    mngr.run()

import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "mus.settings")
import django
django.setup()
APIEMAIL = getattr(settings, "APIEMAIL", "no@email.com")

main()