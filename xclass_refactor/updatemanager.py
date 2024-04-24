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

from loguru import logger
from xclass_refactor.pure_import import PureAPI, PureReports, PureAuthorCSV
from xclass_refactor.openalex_import import OpenAlexAPI, OpenAlexQuery
from xclass_refactor.mus_mongo_client import MusMongoClient
from xclass_refactor.journal_browser_scraper import JournalBrowserScraper
from xclass_refactor.other_apis_import import CrossrefAPI, DataCiteAPI, OpenAIREAPI, SemanticScholarAPI, ZenodoAPI, ORCIDAPI
from xclass_refactor.people_page_scraper import PeoplePageScraper
from xclass_refactor.matching import AuthorMatcher


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
        note: add some sort of multiprocessing/threading/asyncio/scheduling here
        '''
        print(self.include)
        print(self.years)
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
            print('running OpenAlexAPI')
            OpenAlexAPI(openalex_requests, self.years, self.mongoclient).run()
            if 'authors_openalex' in openalex_requests:
                print('running AuthorMatcher')
                AuthorMatcher(self.mongoclient).run()
        if self.include.get('items_pure_oaipmh'):
            self.queries.append(PureAPI(self.years, self.mongoclient))
        if self.include.get('items_pure_reports'):
            self.queries.append(PureReports(self.mongoclient))
        if self.include.get('items_datacite'):
            self.queries.append(DataCiteAPI(self.mongoclient))
        if self.include.get('items_crossref'):
            print('running CrossrefAPI')
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

def main():
    PureAPI(list(range(2012,2025))).run()
    #DataCiteAPI().run()
    #AuthorMatcher().run()
    #mngr = UpdateManager(list(range(2012,2025)), {'works_openalex':True, 'authors_openalex':True, 'sources_openalex':True, 'funders_openalex':True, 'institutions_openalex':True, 'topics_openalex':True})
    #mngr.run()
    ...
