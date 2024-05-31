import motor.motor_asyncio
from collections import defaultdict
from xclass_refactor.constants import MONGOURL
import httpx
from rich import print, progress
import aiometer
import functools
from xclass_refactor.models import MusModel
from datetime import datetime, timedelta
from dataclasses import dataclass
from typing import Optional



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
        self.results : dict = {'items_added':[], 'total':0, 'type':collection}
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
    def __init__(self, collection: str, item_id_type: str, itemlist: list) -> None:
        '''
        collection: the name of the mongodb collection to store results in
        item_id_type: the type of unique id this item uses (e.g. 'orcid' 'doi' 'pmid')
        itemlist: optional list of items to process, each item should have the form:
        {'id': str (openalex id), item_id_type: str (e.g. orcid, doi, pmid)}
        '''
        if itemlist:
            self.itemlist: list = itemlist
        else:
            self.itemlist : list = []
        self.NAMESPACES : dict = {}
        self.motorclient : motor.motor_asyncio.AsyncIOMotorClient = motor.motor_asyncio.AsyncIOMotorClient(MONGOURL).metadata_unificiation_system
        self.collection : motor.motor_asyncio.AsyncIOMotorCollection = self.motorclient[collection] # the collection to store results in
        self.collectionname : str = collection
        self.results : dict = {'ids':[], item_id_type+'s':[], 'total':0, 'type':collection}
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
        try:
            if not self.itemlist:
                await self.make_itemlist()
            await self.get_item_results()
        except Exception as e:
            print(f'Error while getting items for {self.collectionname}: {e}')
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
                if i >= 100 or len(apiresponses) == len(self.itemlist):
                    newlist = [x for x in apiresponses if x not in insertlist]
                    insertlist.extend(newlist)
                    for item in newlist:
                        if isinstance(item, list):
                            for subitem in item:
                                await self.collection.find_one_and_update({"id":subitem['id']}, {'$set':subitem}, upsert=True)
                                self.results['ids'].append(subitem['id'])
                                self.results['total'] = self.results['total'] + 1
                        elif isinstance(item, dict):
                            await self.collection.find_one_and_update({"id":item['id']}, {'$set':item}, upsert=True)
                            self.results['ids'].append(item['id'])
                            self.results['total'] = self.results['total'] + 1
                        else:
                            print(f'received unexpected type {type(item)}')
                    print(f'[red]{len(insertlist)}[/red] {self.item_id_type}s added to {self.collectionname} ([cyan]+{len(newlist)}[/cyan])')

                    i=0

    async def call_api(self, item) -> dict:
        '''
        calls the api for a single item and processes it (if needed) before returning result
        '''
        print('call_api is an abstract function and it needs to be overloaded in subclass')
        result = {}
        return result

@dataclass
class FunctionCallsStats:
    '''
    class that stores time-related stats for a function call of a certain method.
    Meant to used as part of a Performance object to get insight into the performance.
    Attributes:
        duration: float
            the duration of the function call in seconds with max 2 decimals
        start: datetime
            date+time when the function was called
        end: datetime
            date+time when the function returned

    '''
    duration: float
    start: datetime
    end: datetime
    method: callable

    def __init__(self, method:callable):
        '''
        Parameters:
        method: callable
            the function that was called
        '''
        self.method = method
        self.start = datetime.now()
        self.end = None
    def set_end(self) -> None:
        '''
        Sets the end time of the function call
        '''
        self.end = datetime.now()
        self.duration = round((self.end - self.start).total_seconds(),2)

@dataclass
class Performance:
    '''
    class that stores the results of all function class of a certain method.
    Meant to be used for a continuous series of function calls in order to get insight into the performance
    Advice: use a separate instance for each batch of sql additions, e.g. work_performance, source_performance, etc

    Usage:
    - Init a Performance object for each batch of method calls
        perf = Performance()
    - Call start_call(method) for each inidividual method call
        perf.start_call(add_items)
    - end_call() once the method ends
        perf.end_call()

    Then view results using:
        perf.total_counted_duration()
        perf.elapsed_time()
        perf.time_per_call()
    
    '''

    calls: list[FunctionCallsStats]

    def __init__(self) -> None:
        self.calls = []
    def __str__(self) -> str:
        return f'{len(self.calls)} calls in {self.total_measured_duration()} s - {self.time_per_call()} s/call'
    def start_call(self, method:callable) -> None:
        '''
        Records the start time of a new function call of method
        '''
        self.calls.append(FunctionCallsStats(method))
    def end_call(self) -> None:
        '''
        Records the end time of the function call
        '''
        self.calls[-1].set_end()
    def total_measured_duration(self, method:Optional[callable]=None) -> int:
        '''
        Returns the sum of all function call durations in seconds (int)
        if method is passed, only the duration of instances of that method is returned
        '''
        if not self.calls:
            return 0
        if method:
            return sum([funcstat.duration for funcstat in self.calls if funcstat.method == method])
        else:
            return sum([funcstat.duration for funcstat in self.calls])
    def elapsed_time(self) -> int:
        '''
        Returns the time between the first start and last end of all calls in the list in seconds (int)
        '''
        if not self.calls:
            return 0
        self.calls.sort(key=lambda funcstat: funcstat.start)
        first = self.calls[0].start
        self.calls.sort(key=lambda funcstat: funcstat.end)
        last = self.calls[-1].end
        return int((last - first).total_seconds())
    def time_per_call(self, method:Optional[callable]=None) -> float:
        '''
        Returns the average time per item in seconds (with max 2 decimals)
        '''
        if not self.calls:
            return 0
        if not method:
            return round((self.total_measured_duration()/len(self.calls)),2)
        else:
            calls = [funcstat for funcstat in self.calls if funcstat.method == method]
            return round((self.total_measured_duration()/len(calls)),2)

class GenericSQLImport():
    '''
    Class that abstracts out common operations and enforces standard for importing data from a mongodb collection to sql db
    '''

    def __init__(self, collection: motor.motor_asyncio.AsyncIOMotorCollection, model: MusModel, unique_id_field:str='openalex_id') -> None:
        self.performance : Performance = Performance()
        self.collection: motor.motor_asyncio.AsyncIOMotorCollection = collection
        self.model: MusModel = model
        self.results : dict = {
            'type':model.__name__,
            'items': [],
            'added_to_sql':0,
            'raw_items':0,
            'already_in_sql':0,
            'errors':0,
            'm2m_items':0,
        }
        self.unique_id_field : str = unique_id_field
        self.items : list = []
        self.raw_items : list = []
        self.batch_size : int = 50

    async def import_all(self) -> dict:
        models_in_db = self.model.objects.all().values_list(self.unique_id_field, flat=True)
        models_in_db = {model async for model in models_in_db}
        async for item in self.collection.find({}):
                self.results['raw_items'] += 1
                if item.get('id') not in models_in_db:
                    self.performance.start_call(self.add_item)
                    try:
                        await self.add_item(item)
                    except Exception:
                        self.results['errors'] += 1
                        self.performance.end_call()
                        continue
                    self.performance.end_call()
                    self.results['added_to_sql'] += 1
                else:
                    self.results['already_in_sql'] += 1
                if len(self.raw_items) >= self.batch_size:
                    new_items = await self.model.objects.abulk_create(self.raw_items)
                    self.raw_items = []

        self.results['elapsed_time'] = self.performance.elapsed_time()
        self.results['average_time_per_call'] = self.performance.time_per_call()
        self.results['total_measured_duration'] = self.performance.total_measured_duration()
        return self.results
    async def add_item(self, raw_item:dict):
        print('add_item is an abstract function and it needs to be overloaded in subclass')
        print('this method should make an instance of type self.model and add it to self.raw_items.')
        print('do not yet add m2m relations to this instance, that will be done in add_m2m_relations')
        print('example barebone implementation below:')

        item_dict = {
            'field':raw_item.get('field'),
        }
        item = self.model(**item_dict)
        self.raw_items.append(item)
    


