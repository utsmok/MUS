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

        rowlist = []
        start = datetime.now()
        rowlist.append(('start',str(start),'-'))
        print(f'starttime: {start}')
        try:
            res = await OpenAlexAPI().run()
        except Exception as e:
            ...
        doneoa = datetime.now()
        try:
            total = 0
            for r in res:
                total += len(r['results'])
            rowlist.append(('OpenAlex',str(doneoa),str(doneoa-start),str(total)))
            for r in res:
                rowlist.append((r['type'],'-','-',str(len(r['results']))))
            print(f'time to get openalex data: {(doneoa-start)}')
        except Exception as e:
            ...
        try:
            res = await PureAPI().run()
        except Exception as e:
            ...
        donepure = datetime.now()
        try:
            rowlist.append(('Pure',str(donepure),str(donepure-doneoa),str(res['total'])))
            print(f'time to get pure data: {(donepure-doneoa)}')
        except Exception as e:
            ...
        try:
            res = await DataCiteAPI().run()
        except Exception as e:
            ...
        donecite = datetime.now()
        try:
            rowlist.append(('DataCite',str(donecite),str(donecite-donepure),str(res['total'])))
            print(f'time to get datacite data: {(donecite-donepure)}')
        except Exception as e:
            ...
        try:
            res = await OpenAIREAPI().run()
        except Exception as e:
            ...
        doneopen = datetime.now()
        try:
            rowlist.append(('OpenAIRE',str(doneopen),str(doneopen-donecite),str(res['total'])))
            print(f'time to get openaire data: {(doneopen-donecite)}')
        except Exception as e:
            ...
        try:
            res = await ORCIDAPI().run()
        except Exception as e:
            ...
        doneorcid = datetime.now()
        try:
            rowlist.append(('ORCID',str(doneorcid),str(doneorcid-doneopen),str(res['total'])))
            print(f'time to get orcid data: {(doneorcid-doneopen)}')
        except Exception as e:
            ...
        try:
            res = await AuthorMatcher().run()
        except Exception as e:
            ...
        doneauthor = datetime.now()
        try:
            rowlist.append(('AuthorMatcher',str(doneauthor),str(doneauthor-start),str(res['total'])))
            print(f'time to match authors: {(doneauthor-start)}')
        except Exception as e:
            ...
        
        try:
            res = await JournalBrowserScraper().run()
        except Exception as e:
            ...
        donejournal = datetime.now()
        try:
            rowlist.append(('JournalBrowserScraper',str(donejournal),str(donejournal-doneauthor),str(res['total'])))
            print(f'time to scrape journal deals: {(donejournal-doneauthor)}')
        except Exception as e:
            ...
        try:
            res = await PeoplePageScraper().run()
        except Exception as e:
            ...
        donepeople = datetime.now()
        try:
            rowlist.append(('PeoplePageScraper',str(donepeople),str(donepeople-donejournal),str(res['total'])))
            print(f'time to scrape people pages: {(donepeople-donejournal)}')
        except Exception as e:
            ...
        print(f'total time: {(datetime.now()-start)}')
        rowlist.append(('total','-',str(datetime.now()-start)))

        tbl = Table(title='Time taken to update from apis for all UT works published between 2020-2024', show_lines=False)
        tbl.add_column('func', justify='left', style='cyan')
        tbl.add_column('time when done', justify='center', style='yellow')
        tbl.add_column('dt', justify='right', style='bold yellow')
        tbl.add_column('# items', justify='right', style='magenta')
        for item in rowlist:
            tbl.add_row(*item)
        cons2 = Console(record=True)
        cons2.print(tbl)
        cons2.save_svg(f"time_taken_all_updates_{datetime.now().day}_{datetime.now().month}_{datetime.now().year}_{datetime.now().hour}_{datetime.now().minute}.svg", title="All times", theme=SVG_EXPORT_THEME)



def main():
    mngr = UpdateManager()
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(mngr.run())
    print('yo')
    ...


# NOTE FOR MONGODB find calls:
# force use of index, see https://www.mongodb.com/community/forums/t/how-to-speed-up-find-projection-id-true-on-a-large-collection/124514