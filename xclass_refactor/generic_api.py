import motor.motor_asyncio
from collections import defaultdict
from xclass_refactor.constants import MONGOURL
import httpx
from rich import print, progress, console
import aiometer
import functools

class GenericAPI():
    '''
    Generic API class, with default methods
    Implement the methods as needed

    General usage:
    - init: init motor client, select collection, add results dict, and all api settings like url, headers, tokens, etc
    - run: ease of use class that gets all results for the 'standard' query -- first call get_itemlist, then get_item_results
    - make_itemlist: prepares the query. if no items are passed it generates the 'standard' query
    - get_item_results: calls the api, gathers the results for items in the itemlist and puts them in the mongodb collection
    - call_api: method to call the api for a single item and process it (if needed), returns the item
    '''

    motorclient : motor.motor_asyncio.AsyncIOMotorClient = motor.motor_asyncio.AsyncIOMotorClient(MONGOURL).metadata_unificiation_system
    NAMESPACES : dict = {}
    api_settings : dict = {
        'url':'',
        'headers':defaultdict(str),
        'tokens':defaultdict(str),
        'max_at_once':1,
        'max_per_second':1
    }
    def __init__(self, collection: str, item_id_type: str) -> None:
        '''
        collection: the name of the mongodb collection to store results in
        item_id_type: the type of unique id this item uses (e.g. 'orcid' 'doi' 'pmid')
        '''
        self.itemlist : list = []
        self.httpxclient : httpx.AsyncClient = httpx.AsyncClient()
        self.collection : motor.motor_asyncio.AsyncIOMotorCollection = self.motorclient[collection] # the collection to store results in
        self.results : dict = {'ids':[], item_id_type+'s':[], 'total':0}
        self.item_id_type : str = item_id_type

    def set_api_settings(self, url: str = '', headers: dict = {}, tokens: dict = {}, max_at_once: int = 1, max_per_second: int = 1) -> None:
        self.api_settings['url'] = url
        self.api_settings['headers'] = headers
        self.api_settings['tokens'] = tokens
        self.api_settings['max_at_once'] = max_at_once
        self.api_settings['max_per_second'] = max_per_second

    def run(self) -> dict:
        '''
        convience method that runs the standard query and puts the results in the mongodb collection
        returns the 'self.results' dict
        '''
        self.motorclient.get_io_loop().run_until_complete(self.make_itemlist())
        self.motorclient.get_io_loop().run_until_complete(self.get_item_results())
        return self.results
    async def make_itemlist(self) -> None:
        print('make_itemlist is an abstract function -- overload in subclass')
        item = ...
        self.itemlist.append(item)

    async def get_item_results(self) -> None:
        '''
        uses call_api() to get the result for each item in itemlist and puts them in the mongodb collection
        '''
        insertlist = []
        apiresponses = []
        i=0
        with progress.Progress() as p:
            task1 = p.add_task(f"calling api to get data for {self.item_id_type}s", total=len(self.itemlist))
            async with aiometer.amap(functools.partial(self.call_api), self.itemlist, max_at_once=self.api_settings['max_at_once'], max_per_second=self.api_settings['max_per_second']) as responses:
                async for response in responses:
                    apiresponses.append(response)
                    i=i+1
                    p.update(task1, advance=1)
                    if i >= 500 or len(apiresponses) == len(self.itemlist):
                        newlist = [x for x in apiresponses if x not in insertlist]
                        insertlist.extend(newlist)
                        await self.collection.insert_many(newlist)
                        console.print(f'[bold green]{len(insertlist)}[/bold green] {self.item_id_type}s added to mongodb ([bold cyan]+{len(newlist)}[/bold cyan])')
                        i=0

    async def call_api(self, item) -> dict:
        '''
        calls the api for a single item and processes it (if needed) before returning result
        '''
        print('call_api is an abstract function and it needs to be overloaded in subclass')
        result = {}
        return result