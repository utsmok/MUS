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
from xclass_refactor.constants import MONGOURL
from xclass_refactor.create_sql import CreateSQL
import asyncio
import time
from datetime import datetime
import motor.motor_asyncio
from xclass_refactor.utils import get_mongo_collection_mapping
import json

class UpdateManager:
    def __init__(self, years: list[int] = None):
        '''
        years: get items published in these years -- used for retrieving works from pure OAI-PMH & openalex for instance

        '''
        if years:
            self.years = years
        else:
            self.years = None
        self.motorclient : motor.motor_asyncio.AsyncIOMotorClient = motor.motor_asyncio.AsyncIOMotorClient(MONGOURL).metadata_unificiation_system

    async def run(self, include: dict[str,bool] = None):
        '''
        runs the queries based on the include dict
        example: include = {'pure':True, 'openalex':True, 'journalbrowser':True, 'orcid':True}
        '''

        '''mapping = await get_mongo_collection_mapping()
        filename = 'mapping_export.json'
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(mapping,f)'''
        if False:
            from rich import print, box
            from rich.console import Console, SVG_EXPORT_THEME
            from rich.table import Table
            from rich.panel import Panel
            from rich.progress import Progress
            full_results = {}
            cons = Console(markup=True)
            notes = Table(title="Notes", show_lines=False, box=box.SIMPLE_HEAD, title_style='bold magenta', show_header=False)
            notes.add_column('', style='cyan')
            notes.add_row("this is a temporary update manager that will be replaced with a more robust one in the future")
            notes.add_row("the current update manager is not tested")
            notes.add_row("the result outputs for the run() calls are not yet usable or structured")
            notes.add_row("some of the APIs are not yet implemented")
            notes.add_row("some of the APIs are not yet tested")
            notes.add_row("errors are not all handled properly")
            notes.add_row("matching / combining data not properly implemented")
            notes.add_row("moving data to SQL partly implemented, barely tested")
            notes.add_row("for some data cleanup is needed; e.g. datacite: only 3 columns, one of which holds almost all relevant data as a dict -> move this to top level")
            cons.print(Panel(notes, title="MUS Update Manager", style='magenta'))

            overview = Table(show_lines=False, box=box.SIMPLE_HEAD, show_header=False)
            overview.add_column('')
            overview.add_column('')
            overview.add_row(":arrow_right:", "1. Get data from OpenAlex & Pure", style='cyan')
            overview.add_row(":blue_square:","2. Run other APIs and scrapers, e.g. ORCID, OpenAIRE, JournalBrowser, etc")
            overview.add_row(":blue_square:", "3. Cleaning, matching & deduplication of items")
            overview.add_row(":blue_square:", "4. Gather and process data to import into SQL database")
            overview.add_row(":blue_square:", "5. Import data into SQL database & report results")
            cons.print(Panel(overview, title="Progress", style='magenta'))

            async with asyncio.TaskGroup() as tg:
                if 'openalex' in include:
                    openalex =tg.create_task(OpenAlexAPI().run())
                else:
                    openalex = None
                if 'pure' in include:
                    pure = tg.create_task(PureAPI().run())
                else:
                    pure = None
                if 'pure_csv_authors' in include:
                    pure_csv_authors = tg.create_task(PureAuthorCSV().run())
                else:
                    pure_csv_authors = None

            if openalex:
                for result in openalex.result():
                    full_results[result['type']] = len(result['results'])
            else:
                full_results['openalex'] = 0
            if pure:
                full_results['pure_oai_pmh'] = pure.result()['total']
            else:
                full_results['pure_oai_pmh'] = 0
            if pure_csv_authors:
                full_results['pure_csv_authors'] = pure_csv_authors.result()['total']
            else:
                full_results['pure_csv_authors'] = 0

            stats = Table(title='Retrieved items', title_style='dark_violet', show_header=True)
            stats.add_column('Source', style='cyan')
            stats.add_column('# added/updated', style='orange1')
            for key in full_results:
                stats.add_row(str(key), str(full_results[key]))
            cons.print(stats)

            overview = Table(show_lines=False, box=box.SIMPLE_HEAD, show_header=False)
            overview.add_column('')
            overview.add_column('')
            overview.add_row(":white_check_mark:", "1. Get data from OpenAlex & Pure", style='dim')
            overview.add_row(":arrow_right:","2. Run other APIs and scrapers, e.g. ORCID, OpenAIRE, JournalBrowser, etc", style='cyan')
            overview.add_row(":blue_square:", "3. Cleaning, matching & deduplication of items")
            overview.add_row(":blue_square:", "4. Gather and process data to import into SQL database")
            overview.add_row(":blue_square:", "5. Import data into SQL database & report results")
            cons.print(Panel(overview, title="Progress", style='magenta'))
            apilists = Table(title='Number of items per API', show_lines=True,title_style='bold cyan')
            apilists.add_column('API')
            apilists.add_column('item source')
            apilists.add_column('id type')
            apilists.add_column('number of items')

            cons.print("APIs included: Crossref, DataCite, OpenAIRE, ORCID, Journal Browser, UT People Page")
            if any(['openaire' in include, 'datacite' in include, 'crossref' in include]):
                with Progress() as p:
                    numpapers = await self.motorclient['works_openalex'].count_documents({})
                    task = p.add_task("Getting list of dois for Datacite/Crossref/OpenAIRE", total=numpapers)

                    datacitelist = []
                    openairelist = []
                    crossreflist = []
                    orcidlist = []
                    async for paper in self.motorclient['works_openalex'].find({}, projection={'id':1, 'doi':1}, sort=[('id', 1)]):
                        if paper.get('doi'):
                            if not await self.motorclient['items_datacite'].find_one({'id':paper['id']}, projection={'id': 1}):
                                datacitelist.append({'doi':paper['doi'].replace('https://doi.org/',''), 'id':paper['id']})
                            if not await self.motorclient['items_openaire'].find_one({'id':paper['id']}, projection={'id': 1}):
                                openairelist.append({'doi':paper['doi'].replace('https://doi.org/',''), 'id':paper['id']})
                            if not await self.motorclient['items_crossref'].find_one({'id':paper['id']}, projection={'id': 1}):
                                crossreflist.append({'doi':paper['doi'].replace('https://doi.org/',''), 'id':paper['id']})
                        p.update(task, advance=1)
                apilists.add_row('DataCite','works openalex','doi', str(len(datacitelist)))
                apilists.add_row('OpenAIRE','works openalex','doi', str(len(openairelist)))
                apilists.add_row('Crossref','works openalex','doi', str(len(crossreflist)))
            if 'orcid' in include:
                with Progress() as p:
                    numauths = await self.motorclient['authors_openalex'].count_documents({'ids.orcid':{'$exists':True}})
                    task = p.add_task("Getting list of orcids ", total=numauths)
                    async for auth in self.motorclient['authors_openalex'].find({'ids.orcid':{'$exists':True}}, projection={'id':1, 'ids':1}):
                        p.update(task, advance=1)
                        if auth.get('ids').get('orcid'):
                            check = await self.motorclient['items_orcid'].find_one({'id':auth['id']}, projection={'id': 1, 'orcid-identifier': 1})
                            if check:
                                if check.get('orcid-identifier'):
                                    continue
                            orcidlist.append({'orcid':auth['ids']['orcid'].replace('https://orcid.org/',''), 'id':auth['id']})
                apilists.add_row('ORCID','authors openalex','orcid', str(len(orcidlist)))



            cons.print(apilists)

            tasks : list[asyncio.Task|None] = []
            async with asyncio.TaskGroup() as tg:
                if 'crossref' in include:
                    crossref = tg.create_task(CrossrefAPI(itemlist=crossreflist).run())
                else:
                    crossref = 'crossref'
                if 'datacite' in include:
                    datacite = tg.create_task(DataCiteAPI(itemlist=datacitelist).run())
                else:
                    datacite = 'datacite'
                if 'openaire' in include:
                    openaire = tg.create_task(OpenAIREAPI(itemlist=openairelist).run())
                else:
                    openaire = 'openaire'
                if 'orcid' in include:
                    orcid = tg.create_task(ORCIDAPI(itemlist=orcidlist).run())
                else:
                    orcid = 'orcid'
                if 'journalbrowser' in include:
                    journalbrowser = tg.create_task(JournalBrowserScraper().run())
                else:
                    journalbrowser = 'journalbrowser'
                if 'peoplepage' in include:
                    peoplepage = tg.create_task(PeoplePageScraper().run())
                else:
                    peoplepage = 'peoplepage'
            tasks.append(crossref)
            tasks.append(datacite)
            tasks.append(openaire)
            tasks.append(orcid)
            tasks.append(journalbrowser)
            tasks.append(peoplepage)
            '''
            for task in tasks:
                if isinstance(task, asyncio.Task):
                    for result in task.result():
                        full_results[result['type']] = result['total']
                else:
                    full_results[task] = 0'''

            stats = Table(title='Retrieved items', title_style='dark_violet', show_header=True)
            stats.add_column('Source', style='cyan')
            stats.add_column('# added/updated', style='orange1')
            for key in full_results:
                stats.add_row(str(key), str(full_results[key]))
            cons.print(stats)

            overview = Table(title='Tasks', show_lines=False, box=box.SIMPLE_HEAD, title_style='bold yellow', show_header=False)
            overview.add_column('')
            overview.add_column('')
            overview.add_row(":white_check_mark:", "1. Get data from OpenAlex & Pure", style='dim')
            overview.add_row(":white_check_mark:","2. Run other APIs and scrapers, e.g. ORCID, OpenAIRE, JournalBrowser, etc", style='dim')
            overview.add_row(":arrow_right:", "3. Cleaning, matching & deduplication of items", style='cyan')
            overview.add_row(":blue_square:", "4. Gather and process data to import into SQL database")
            overview.add_row(":blue_square:", "5. Import data into SQL database & report results")
            cons.print(Panel(overview, title="Progress", style='magenta'))
            cons.print('Implemented functions: matching Pure authors (from CSV import) with OpenAlex authors')

            third_results = await asyncio.gather(AuthorMatcher().run(),
            )
            overview = Table(title='Tasks', show_lines=False, box=box.SIMPLE_HEAD, title_style='bold yellow', show_header=False)
            overview.add_column('')
            overview.add_column('')
            overview.add_row(":white_check_mark:", "1. Get data from OpenAlex & Pure", style='dim')
            overview.add_row(":white_check_mark:","2. Run other APIs and scrapers, e.g. ORCID, OpenAIRE, JournalBrowser, etc", style='dim')
            overview.add_row(":white_question_mark:", "3. Cleaning, matching & deduplication of items", style='dim')
            overview.add_row(":arrow_right:", "4. Gather and process data to import into SQL database", style='red')
            overview.add_row(":x:", "5. Import data into SQL database & report results", style='red')
            cons.print(Panel(overview, title="Progress", style='magenta'))
            cons.print('Now running the CreateSQL class to add data to the database')
            cons.print('Update Manager finished.')

        sql_creator = CreateSQL()
        add_sql_result = await sql_creator.add_all()





def main():
    mngr = UpdateManager()
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    include = {'openalex':True, 'crossref':True, 'pure':True,'pure_csv_authors':True, 'journalbrowser':True,'peoplepage':True}
    asyncio.run(mngr.run(include=include))
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