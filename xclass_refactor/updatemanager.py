'''
temporary file

refactoring all the functions in mus_backend for retrieving items from apis, scrapers etc
: from function-based into class-based

instead of calling the functions one after another we'll use classes to manage it all

main structure:
: base class that manages the current update process
: creates instances of all kinds of other classes that will hold/retrieve the data
: take note that we want to bundle api calls and db operations in batches instead of one at a time


implement some multiprocessing/threading/asyncio where it makes sense

import multiprocessing as mp
from concurrent.futures import ProcessPoolExecutor

'''

from loguru import logger
from xclass_refactor.pure_report_import import PureReport
from xclass_refactor.pure_import import PureAPI,PureAuthorCSV
from xclass_refactor.openalex_import import OpenAlexAPI
from xclass_refactor.mus_mongo_client import MusMongoClient
from xclass_refactor.journal_browser_scraper import JournalBrowserScraper
from xclass_refactor.other_apis_import import CrossrefAPI, DataCiteAPI, OpenAIREAPI, ORCIDAPI
from xclass_refactor.people_page_scraper import PeoplePageScraper
from xclass_refactor.matching import AuthorMatcher
from xclass_refactor.constants import *
import asyncio
import time
from datetime import datetime
class UpdateManager:
    def __init__(self, years: list[int] = None):
        '''
        years: get items published in these years -- used for retrieving works from pure OAI-PMH & openalex for instance

        '''
        if years:
            self.years = years
        else:
            self.years = None

    async def run(self):
        '''
        runs the queries based on the include dict
        note: add some sort of multiprocessing/threading/asyncio/scheduling here
        '''
        from rich import print
        from rich.console import Console, SVG_EXPORT_THEME
        from rich.table import Table
        cons = Console()
        cons.print("Starting update manager...")
        cons.print("Notes:")
        cons.print("- this is a temporary update manager that will be replaced with a more robust one in the future")
        cons.print("- the current update manager is not completely tested")
        cons.print("- the result outputs are not yet usable or structured")
        cons.print("- some of the APIs are not yet implemented")
        cons.print("- some of the APIs are not yet tested")
        cons.print("- errors are not all handled properly")
        cons.print("- matching / combining data not properly implemented")
        cons.print("- no work done yet for moving data to SQL")
        cons.print("- for some data cleanup is needed; e.g. datacite: only 3 columns, one of which holds almost all relevant data as a dict -> move this to top level")


        cons.rule('1. Running base APIs')
        cons.print("Gathering data from OpenAlex and Pure (OAI-PMH and any report exports found)")
        await asyncio.gather(
            OpenAlexAPI().run(),
            PureAPI().run(),
            PureAuthorCSV().run(),
        )
        cons.rule('2. Running other API and scrapers')
        cons.print("currently including: DataCite, OpenAIRE, ORCID, Journal Browser, UT People Page")
        cons.print('Crossref is skipped at the moment, needs updates.')
        await asyncio.gather(
            #CrossrefAPI().run(), #! needs better implementation before running
            DataCiteAPI().run(),
            ORCIDAPI().run(),
            OpenAIREAPI().run(),
            JournalBrowserScraper().run(),
            PeoplePageScraper().run(),
        )
        cons.rule('3. Running author matching')
        cons.print('matching authors from OpenAlex and Pure')

        await AuthorMatcher().run()

        cons.rule('Done!')


def main():
    mngr = UpdateManager()
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(mngr.run())
    ...


#! MongoDB find calls:
# force use of index, see https://www.mongodb.com/community/forums/t/how-to-speed-up-find-projection-id-true-on-a-large-collection/124514

#! When implementing the new update manager into current MUS code:
# collections need to be renamed in mus_backend and PureOpenAlex.
#
# 'rough' Mapping (from old to new) listed below.
# however: take care to check actual usage of the collections in the backend -- e.g. the fields could have different names or structures etc etc.

mongo_mapping = {
'api_responses_works_openalex':'works_openalex',
'api_responses_pure':'items_pure_oaipmh',
'api_responses_datacite':'items_datacite',
'api_responses_crossref':'items_crossref',
'api_responses_openaire':'items_openaire',
'api_responses_authors_openalex':'authors_openalex',
'api_responses_UT_authors_openalex':'None',# unknown? check implementation
'api_responses_openalex':'works_openalex',
'api_responses_journals_openalex':'sources_openalex',
'api_responses_UT_authors_peoplepage':'employees_peoplepage',
'api_responses_journals_dealdata_scraped':'deals_journalbrowser',
'pure_report_start_tcs':'items_pure_reports',
'pure_report_ee':'items_pure_reports',
'pure_xmls': 'None',
}