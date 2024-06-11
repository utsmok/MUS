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

import asyncio
import motor.motor_asyncio

from mus_wizard.constants import MONGOURL
from mus_wizard.database.create_sql import CreateSQL
from mus_wizard.database.matching import AuthorMatcher, WorkMatcher
from mus_wizard.database.mongo_client import MusMongoClient
from mus_wizard.harvester.crossref import CrossrefAPI
from mus_wizard.harvester.datacite import DataCiteAPI
from mus_wizard.harvester.journal_browser import JournalBrowserScraper
from mus_wizard.harvester.oai_pmh import PureAPI, PureAuthorCSV, OAI_PMH
from mus_wizard.harvester.openaire import OpenAIREAPI
from mus_wizard.harvester.openalex import OpenAlexAPI
from mus_wizard.harvester.orcid import ORCIDAPI
from mus_wizard.utwente.people_pages import PeoplePageScraper


class Wizard:
    def __init__(self, years: list[int] = None, include: dict[str, bool] = None):
        '''
        years: get items published in these years -- used for retrieving works from pure OAI-PMH & openalex for instance

        '''
        if years:
            self.years = years
        else:
            self.years = None
        self.motorclient: motor.motor_asyncio.AsyncIOMotorClient = motor.motor_asyncio.AsyncIOMotorClient(
            MONGOURL).metadata_unification_system

    async def run(self, include: dict[str, bool] = None):
        '''
        runs the queries based on the include dict
        example: include = {'pure':True, 'openalex':True, 'journalbrowser':True, 'orcid':True}
        '''

        '''mapping = await get_mongo_collection_mapping()
        filename = 'mapping_export.json'
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(mapping,f)'''

        from rich import box
        from rich.console import Console
        from rich.table import Table
        from rich.panel import Panel
        from rich.progress import Progress
        # add indexes to all collections before we start
        musmongoclient = MusMongoClient()
        await musmongoclient.add_indexes()

        full_results = {}
        cons = Console(markup=True)
        notes = Table(title="Notes", show_lines=False, box=box.SIMPLE_HEAD, title_style='bold magenta',
                      show_header=False)
        notes.add_column('', style='cyan')
        notes.add_row("this is a temporary update manager that will be replaced with a more robust one in the future")
        notes.add_row("the current update manager is not tested")
        notes.add_row("the result outputs for the run() calls are not yet usable or structured")
        notes.add_row("some of the APIs are not yet implemented")
        notes.add_row("some of the APIs are not yet tested")
        notes.add_row("errors are not all handled properly")
        notes.add_row("matching / combining data not properly implemented")
        notes.add_row("moving data to SQL partly implemented, barely tested")
        notes.add_row(
            "for some data cleanup is needed; e.g. datacite: only 3 columns, one of which holds almost all relevant data as a dict -> move this to top level")
        cons.print(Panel(notes, title="MUS Update Manager", style='magenta'))

        overview = Table(show_lines=False, box=box.SIMPLE_HEAD, show_header=False)
        overview.add_column('')
        overview.add_column('')
        overview.add_row(":arrow_right:", "1. Get data from OpenAlex & Pure", style='cyan')
        overview.add_row(":blue_square:", "2. Run other APIs and scrapers, e.g. ORCID, OpenAIRE, JournalBrowser, etc")
        overview.add_row(":blue_square:", "3. Cleaning, matching & deduplication of items")
        overview.add_row(":blue_square:", "4. Gather and process data to import into SQL database")
        overview.add_row(":blue_square:", "5. Import data into SQL database & report results")
        cons.print(Panel(overview, title="Progress", style='magenta'))
        if 'skip_one' not in include:
            async with asyncio.TaskGroup() as tg:
                if 'openalex' in include or 'all' in include:
                    openalex = tg.create_task(OpenAlexAPI().run())
                else:
                    openalex = None
                if 'pure' in include or 'all' in include:
                    cerif = tg.create_task(OAI_PMH().run())
                
                add_indexes = tg.create_task(musmongoclient.add_indexes())

            if openalex:
                for result in openalex.result():
                    full_results[result['type']] = len(result['results'])
            else:
                full_results['openalex'] = 0
            
            full_results['cerif'] = cerif.result()['total']
            

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
        overview.add_row(":arrow_right:", "2. Run other APIs and scrapers, e.g. ORCID, OpenAIRE, JournalBrowser, etc",
                         style='cyan')
        overview.add_row(":arrow_right:", "3. Cleaning, matching & deduplication of items")
        overview.add_row(":arrow_right:", "4. Gather and process data to import into SQL database")
        overview.add_row(":arrow_right:", "5. Import data into SQL database & report results")
        cons.print(Panel(overview, title="Progress", style='magenta'))
        apilists = Table(title='Number of items per API', show_lines=True, title_style='bold cyan')
        apilists.add_column('API')
        apilists.add_column('item source')
        apilists.add_column('id type')
        apilists.add_column('number of items')
        if 'skip_two' not in include:
            cons.print("APIs included: Crossref, DataCite, OpenAIRE, ORCID, Journal Browser, UT People Page")
            datacitelist = []
            openairelist = []
            crossreflist = []
            orcidlist = []
            if any(['openaire' in include, 'datacite' in include, 'crossref' in include, 'all' in include]):
                with Progress() as p:
                    numpapers = await self.motorclient['works_openalex'].count_documents({})
                    task = p.add_task("Getting list of dois for Datacite/Crossref/OpenAIRE", total=numpapers)

                    async for paper in self.motorclient['works_openalex'].find({}, projection={'id': 1, 'doi': 1},
                                                                               sort=[('id', 1)]):
                        if paper.get('doi'):
                            if not await self.motorclient['items_datacite'].find_one({'id': paper['id']},
                                                                                     projection={'id': 1}):
                                datacitelist.append(
                                    {'doi': paper['doi'].replace('https://doi.org/', ''), 'id': paper['id']})
                            if not await self.motorclient['items_openaire'].find_one({'id': paper['id']},
                                                                                     projection={'id': 1}):
                                openairelist.append(
                                    {'doi': paper['doi'].replace('https://doi.org/', ''), 'id': paper['id']})
                            if not await self.motorclient['items_crossref'].find_one({'id': paper['id']},
                                                                                     projection={'id': 1}):
                                crossreflist.append(
                                    {'doi': paper['doi'].replace('https://doi.org/', ''), 'id': paper['id']})
                        p.update(task, advance=1)
                apilists.add_row('DataCite', 'works openalex', 'doi', str(len(datacitelist)))
                apilists.add_row('OpenAIRE', 'works openalex', 'doi', str(len(openairelist)))
                apilists.add_row('Crossref', 'works openalex', 'doi', str(len(crossreflist)))
            if 'orcid' in include or 'all' in include:
                with Progress() as p:

                    numauths = await self.motorclient['authors_openalex'].count_documents(
                        {'ids.orcid': {'$exists': True}})
                    task = p.add_task("Getting list of orcids ", total=numauths)
                    async for auth in self.motorclient['authors_openalex'].find({'ids.orcid': {'$exists': True}},
                                                                                projection={'id': 1, 'ids': 1}):
                        p.update(task, advance=1)
                        if auth.get('ids').get('orcid'):
                            check = await self.motorclient['items_orcid'].find_one({'id': auth['id']},
                                                                                   projection={'id'              : 1,
                                                                                               'orcid-identifier': 1})
                            if check:
                                if check.get('orcid-identifier'):
                                    continue
                            orcidlist.append(
                                {'orcid': auth['ids']['orcid'].replace('https://orcid.org/', ''), 'id': auth['id']})
                apilists.add_row('ORCID', 'authors openalex', 'orcid', str(len(orcidlist)))

            cons.print(apilists)
            tasks: list[asyncio.Task | None] = []

            async with asyncio.TaskGroup() as tg:
                #if 'crossref' in include or 'all' in include:
                #    crossref = tg.create_task(CrossrefAPI(itemlist=crossreflist).run())
                #else:
                #    crossref = 'crossref'
                #if 'datacite' in include or 'all' in include:
                #    datacite = tg.create_task(DataCiteAPI(itemlist=datacitelist).run())
                #else:
                #    datacite = 'datacite'
                ##if 'openaire' in include or 'all' in include:
                #    #openaire = tg.create_task(OpenAIREAPI(itemlist=openairelist).run())
                ##else:
                #    #openaire = 'openaire'
                #if 'orcid' in include or 'all' in include:
                #    orcid = tg.create_task(ORCIDAPI(itemlist=orcidlist).run())
                #else:
                #    orcid = 'orcid'

                journalbrowser = tg.create_task(JournalBrowserScraper().run())
                authormatcher = tg.create_task(AuthorMatcher().run())
                #workmatcher = tg.create_task(WorkMatcher().run())
                add_indexes = tg.create_task(musmongoclient.add_indexes())

            #tasks.append(crossref)
            #tasks.append(datacite)
            #tasks.append(openaire)
            #tasks.append(orcid)
            tasks.append(journalbrowser)
            tasks.append(authormatcher)
            #tasks.append(workmatcher)
            tasks.append(add_indexes)

            for task in tasks:
                if isinstance(task, asyncio.Task):
                    try:
                        for result in task.result():
                            full_results[result['type']] = result['total']
                    except Exception as e:
                        ...
                else:
                    full_results[task] = 0
            stats = Table(title='Retrieved items', title_style='dark_violet', show_header=True)
            stats.add_column('Source', style='cyan')
            stats.add_column('# added/updated', style='orange1')
            for key in full_results:
                stats.add_row(str(key), str(full_results[key]))
            cons.print(stats)

        overview = Table(title='Tasks', show_lines=False, box=box.SIMPLE_HEAD, title_style='bold yellow',
                         show_header=False)
        overview.add_column('')
        overview.add_column('')
        overview.add_row(":white_check_mark:", "1. Get data from OpenAlex & Pure", style='dim')
        overview.add_row(":white_check_mark:",
                         "2. Run other APIs and scrapers, e.g. ORCID, OpenAIRE, JournalBrowser, etc", style='dim')
        overview.add_row(":white_check_mark:", "3. Cleaning, matching & deduplication of items", style='dim')
        overview.add_row(":arrow_right:", "4. Gather and process data to import into SQL database", style='red')
        overview.add_row(":x:", "5. Import data into SQL database & report results", style='red')
        cons.print(Panel(overview, title="Progress", style='magenta'))
        await CreateSQL().add_all()

        cons.print('Update Manager finished.')


def main():
    include = {'all': True}
    
    #asyncio.run(Wizard().run(include))

    #results = asyncio.run(AuthorMatcher().run())
    #print(results)
    # asyncio.run(OAI_PMH().run())

    results = asyncio.run(CreateSQL().add_all())
    print(results)


# ! MongoDB find calls:
# force use of index, see https://www.mongodb.com/community/forums/t/how-to-speed-up-find-projection-id-true-on-a-large-collection/124514

# ! When implementing the new update manager into current MUS code:
# collections need to be renamed in mus_backend and PureOpenAlex.
#
# 'rough' Mapping (from old to new) listed below.
# however: take care to check actual usage of the collections in the backend -- e.g. the fields could have different names or structures etc etc.

mongo_mapping = {
    'api_responses_works_openalex'           : 'works_openalex',
    'api_responses_pure'                     : 'items_pure_oaipmh',
    'api_responses_datacite'                 : 'items_datacite',
    'api_responses_crossref'                 : 'items_crossref',
    'api_responses_openaire'                 : 'items_openaire',
    'api_responses_authors_openalex'         : 'authors_openalex',
    'api_responses_UT_authors_openalex'      : 'None',  # unknown? check implementation
    'api_responses_openalex'                 : 'works_openalex',
    'api_responses_journals_openalex'        : 'sources_openalex',
    'api_responses_UT_authors_peoplepage'    : 'employees_peoplepage',
    'api_responses_journals_dealdata_scraped': 'deals_journalbrowser',
    'pure_report_start_tcs'                  : 'items_pure_reports',
    'pure_report_ee'                         : 'items_pure_reports',
    'pure_xmls'                              : 'None',
}
