import motor.motor_asyncio
from collections import defaultdict
from xclass_refactor.constants import MONGOURL
import httpx
from rich import print, progress
import aiometer
import functools
class GenericScraper():
    '''
    Generic Scraper class, with default methods
    Implement the methods as needed

    General usage:
    - init: init motor client, select collection, scraper client, add results dict, and all base scraper settings like url, headers, tokens, etc
    - run: ease of use class that gets all results for the 'standard' query -- first call make_itemlist, then get_item_results
    - make_itemlist: builds a list of scrapes to run -- uses 'standard' list if no items are passed, otherwise builds from parameters
    - get_item_results: calls the scraper, gathers the results for items in the itemlist and puts them in the mongodb collection
    - scrape_items: this is the method that actually scrapes the url for each item in the itemlist
    '''

    motorclient : motor.motor_asyncio.AsyncIOMotorClient = motor.motor_asyncio.AsyncIOMotorClient(MONGOURL).metadata_unificiation_system
    scraperclient : httpx.AsyncClient = httpx.AsyncClient(timeout=30)


    def __init__(self, collection: str) -> None:
        self.collection: motor.motor_asyncio.AsyncIOMotorCollection = self.motorclient[collection] # the collection to store results in
        self.results : dict = {'items_added':[], 'total':0}
        self.itemlist : list = []
        self.scraper_settings : dict = {
        'url':'',
        'headers':'',
        'tokens':'',
        'max_at_once':1,
        'max_per_second':1
    }

    def set_scraper_settings(self, **kwargs) -> None:
        '''
        url: str - url to scrape
        headers: opt. dict[str] - headers to send with the request
        tokens: opt. dict[str] - tokens to send with the request
        max_at_once: int - max number of requests to send at once
        max_per_second: int - max number of requests to send per second
        '''
        for key, value in kwargs.items():
            self.scraper_settings[key] = value

    async def run(self) -> dict:
        await self.make_itemlist()
        await self.get_item_results()
        return self.results

    async def make_itemlist(self) -> None:
        print('make_itemlist is an abstract function -- overload in subclass')
        item = ...
        self.itemlist.append(item)

    async def get_item_results(self) -> None:
        '''
        uses call_api() to get the result for each item in itemlist and puts them in the mongodb collection
        '''

        async with aiometer.amap(functools.partial(self.call_api), self.itemlist, max_at_once=self.scraper_settings['max_at_once'], max_per_second=self.scraper_settings['max_per_second']) as responses:
            async for response in responses:
                ...

    async def call_api(self, item) -> dict:
        '''
        calls the api for a single item and processes it (if needed) before returning result
        '''
        print('call_api is an abstract function and it needs to be overloaded in subclass')
        result = {}
        return result
class GenericAPI():
    '''
    Generic API class, with default methods
    Implement the methods as needed

    General usage:
    - init: init motor client, select collection, add results dict, and all api settings like url, headers, tokens, etc
    - run: ease of use class that gets all results for the 'standard' query -- first call make_itemlist, then get_item_results
    - make_itemlist: prepares the query. if no items are passed it generates the 'standard' query
    - get_item_results: calls the api, gathers the results for items in the itemlist and puts them in the mongodb collection
    - call_api: method to call the api for a single item and process it (if needed), returns the item
    '''



    httpxclient : httpx.AsyncClient = httpx.AsyncClient()
    def __init__(self, collection: str, item_id_type: str) -> None:
        '''
        collection: the name of the mongodb collection to store results in
        item_id_type: the type of unique id this item uses (e.g. 'orcid' 'doi' 'pmid')
        '''
        self.NAMESPACES : dict = {}
        self.motorclient : motor.motor_asyncio.AsyncIOMotorClient = motor.motor_asyncio.AsyncIOMotorClient(MONGOURL).metadata_unificiation_system
        self.itemlist : list = []
        self.collection : motor.motor_asyncio.AsyncIOMotorCollection = self.motorclient[collection] # the collection to store results in
        self.results : dict = {'ids':[], item_id_type+'s':[], 'total':0}
        self.item_id_type : str = item_id_type
        self.api_settings : dict = {
            'url':'',
            'headers':{},
            'tokens':{},
            'max_at_once':1,
            'max_per_second':1
        }
    def set_api_settings(self, url: str = None, headers: dict = None, tokens: dict = None, max_at_once: int = None, max_per_second: int = None) -> None:
        if url:
            self.api_settings['url'] = url
        if headers:
            self.api_settings['headers'] = headers
        if tokens:
            self.api_settings['tokens'] = tokens
        if max_at_once:
            self.api_settings['max_at_once'] = max_at_once
        if max_per_second:
            self.api_settings['max_per_second'] = max_per_second

    async def run(self) -> dict:
        '''
        convience method that runs the standard query and puts the results in the mongodb collection
        returns the 'self.results' dict
        '''
        await self.make_itemlist()
        await self.get_item_results()
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
        async with aiometer.amap(functools.partial(self.call_api), self.itemlist, max_at_once=self.api_settings['max_at_once'], max_per_second=self.api_settings['max_per_second']) as responses:
            async for response in responses:
                apiresponses.append(response)
                i=i+1
                if i >= 500 or len(apiresponses) == len(self.itemlist):
                    newlist = [x for x in apiresponses if x not in insertlist]
                    insertlist.extend(newlist)
                    for item in newlist:
                        await self.collection.find_one_and_update({"id":item['id']}, {'$set':item}, upsert=True)
                        self.results['ids'].append(item['id'])
                        self.results['total'] = self.results['total'] + 1
                    print(f'[bold green]{len(insertlist)}[/bold green] {self.item_id_type}s added to mongodb ([bold cyan]+{len(newlist)}[/bold cyan])')
                    i=0

    async def call_api(self, item) -> dict:
        '''
        calls the api for a single item and processes it (if needed) before returning result
        '''
        print('call_api is an abstract function and it needs to be overloaded in subclass')
        result = {}
        return result