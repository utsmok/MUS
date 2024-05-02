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
        cons: Console = Console(style='yellow')
        cons.print(f'starttime: {start}')
        await OpenAlexAPI().run()
        doneoa = datetime.now()
        rowlist.append(('OpenAlex',str(doneoa),str(doneoa-start)))
        cons.print(f'time to get openalex data: {(doneoa-start)}')
        await PureAPI().run()
        donepure = datetime.now()
        rowlist.append(('Pure',str(donepure),str(donepure-doneoa)))
        cons.print(f'time to get pure data: {(donepure-doneoa)}')
        await DataCiteAPI().run()
        donecite = datetime.now()
        rowlist.append(('DataCite',str(donecite),str(donecite-donepure)))
        cons.print(f'time to get datacite data: {(donecite-donepure)}')
        await OpenAIREAPI().run()
        doneopen = datetime.now()
        rowlist.append(('OpenAIRE',str(doneopen),str(doneopen-donecite)))
        cons.print(f'time to get openaire data: {(doneopen-donecite)}')
        await ORCIDAPI().run()
        doneorcid = datetime.now()
        rowlist.append(('ORCID',str(doneorcid),str(doneorcid-doneopen)))
        cons.print(f'time to get orcid data: {(doneorcid-doneopen)}')
        await AuthorMatcher().run()
        doneauthor = datetime.now()
        rowlist.append(('AuthorMatcher',str(doneauthor),str(doneauthor-doneorcid)))
        cons.print(f'time to match authors: {(doneauthor-doneorcid)}')
        await JournalBrowserScraper().run()
        donejournal = datetime.now()
        rowlist.append(('JournalBrowserScraper',str(donejournal),str(donejournal-doneauthor)))
        cons.print(f'time to scrape journal deals: {(donejournal-doneauthor)}')
        await PeoplePageScraper().run()
        donepeople = datetime.now()
        rowlist.append(('PeoplePageScraper',str(donepeople),str(donepeople-donejournal)))
        cons.print(f'time to scrape people pages: {(donepeople-donejournal)}')
        cons.print(f'total time: {(donepeople-start)}')
        rowlist.append('total','-',str(donepeople-start))

        tbl = Table(title='Time taken to update from all apis for 2022-2024 ', show_lines=False)
        tbl.add_column('func', justify='left', style='cyan')
        tbl.add_column('time when done', justify='center', style='yellow')
        tbl.add_column('dt', justify='right', style='yellow')
        for item in rowlist:
            tbl.add_row(*item)
        cons2 = Console(record=True)
        cons2.print(tbl)
        cons2.save_svg("time_taken_all_updates.svg", title="All times", theme=SVG_EXPORT_THEME)



def main():
    mngr = UpdateManager()
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(mngr.run())
    print('yo')
    ...
