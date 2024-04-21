
from xclass_refactor.mus_mongo_client import MusMongoClient
from habanero import Crossref
from django.conf import settings
import httpx
import xmltodict
from rich.console import Console
from rich import table, print, progress
import asyncio
import aiometer
import functools
import motor.motor_asyncio
import re

APIEMAIL = getattr(settings, "APIEMAIL", "no@email.com")
console = Console()

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

    MONGOURL = getattr(settings, "MONGOURL")
    motorclient = motor.motor_asyncio.AsyncIOMotorClient(MONGOURL).metadata_unificiation_system
    def __init__(self, collection: str, item_id_type: str):
        '''
        collection: the name of the mongodb collection to store results in
        item_id_type: the type of unique id this item uses (e.g. 'orcid' 'doi' 'pmid')
        '''
        self.itemlist = []
        self.httpxclient = httpx.AsyncClient()
        self.collection = self.motorclient[collection] # the collection to store results in
        self.results = {'ids':[], item_id_type+'s':[], 'total':0}
        self.max_at_once = 1
        self.max_per_second = 1
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
            task1 = p.add_task("getting results", total=len(self.itemlist))
            async with aiometer.amap(functools.partial(self.call_api), self.itemlist, max_at_once=self.max_at_once, max_per_second=self.max_per_second) as responses:
                async for response in responses:
                    apiresponses.append(response)
                    i=i+1
                    p.update(task1, advance=1)
                    if i >= 500 or len(self.apiresponses) == len(self.itemlist):
                        newlist = [x for x in self.apiresponses if x not in insertlist]
                        insertlist.extend(newlist)
                        await self.collection.insert_many(newlist)
                        console.print(f'[bold green]{len(insertlist)}[/bold green] items added to mongodb ([bold cyan]+{len(newlist)}[/bold cyan])')
                        i=0
                
    async def call_api(self, item) -> dict:
        '''
        calls the api for a single item and processes it (if needed) before returning result
        '''
        print('call_api is an abstract function -- overload in subclass')
        result = {}
        return result
class DataCiteAPI():
    def __init__(self, mongoclient):
        self.mongoclient = mongoclient
        self.results = {}

class CrossrefAPI():
    '''
    TODO: import xml data instead of json, see https://www.crossref.org/documentation/retrieve-metadata/xml-api/doi-to-metadata-query/
    '''
    def __init__(self, years: list = [2023, 2024, 2025], mongoclient: MusMongoClient = None, dois: list[str] = None):
        self.mongoclient = mongoclient

        self.collection = mongoclient.items_crossref_xml
        self.results = []
        self.crossref = Crossref(mailto=APIEMAIL)
        self.pagesize=100
        self.dois = dois
        self.years = years
    def get_crossref_results_from_dois(self):
        if not self.dois:
            self.dois = [str(x['doi']).replace('https://doi.org/','') for x in self.mongoclient.works_openalex.find()]
            print(f'found {len(self.dois)} dois')
            i=0
            for doi in self.dois:
                try:
                    article = self.crossref.works(ids=doi)['message']
                except Exception as e:
                    print(f'error querying crossref for doi {doi}: {e}')
                    continue
                try:
                    self.collection.find_one_and_update({"DOI":article['DOI']}, {'$set':article}, upsert=True)
                    i=i+1
                except Exception as e:
                    print(f'error storing crossref result for doi {doi}: {e}')
                    continue
                if i % 100 == 0:
                    print(f'{i} of {len(self.dois)} added (+100)')
        else:
            self.results.append(self.crossref.works(ids=self.dois, cursor = "*", limit = self.pagesize, cursor_max=100000))
            pass

    async def call_api(self, item, client):
        async def addrecord(record, openalexid, doi):
            item = None
            if record:
                if record['crossref'].get('error'):
                    return None
                if record['crossref'].get('journal'):
                    item = record['crossref']['journal']
                elif record['crossref'].get('conference'):
                    item = record['crossref']['conference']
                elif record['crossref'].get('book'):
                    item = record['crossref']['book']
                elif record['crossref'].get('posted_content'):
                    item = record['crossref']['posted_content']
                elif record['crossref'].get('peer_review'):
                    item = record['crossref']['peer_review']
                elif record['crossref'].get('database'):
                    item = record['crossref']['database']['dataset']
                elif record['crossref'].get('dissertation'):
                    item = record['crossref']['dissertation']
                elif record['crossref'].get('report-paper'):
                    item = record['crossref']['report-paper']['report-paper_metadata']
                if not item:
                    print(f'no journal, book, or conference for doi {doi}')
                else:
                    item['id'] = openalexid
                    self.collection.insert_one(item)

        url = f'https://doi.crossref.org/servlet/query?pid={APIEMAIL}&format=unixref&id={item['doi']}'
        try:
            r = await client.get(url)
            data = xmltodict.parse(r.text, attr_prefix='',dict_constructor=dict)
        except Exception as e:
            print(f'error querying crossref for doi {item['doi']}: {e}')
        try:
            if data.get('doi_records'):
                if isinstance(data.get('doi_records'), list):
                    for record in data.get('doi_records'):
                        await addrecord(record, item['id'], item['doi'])
                else:
                    await addrecord(data.get('doi_records').get('doi_record'), item['id'], item['doi'])
        except Exception as e:
            print(f'error storing crossref result for doi {item['doi']}: {e}')
    async def get_xml_crossref_results_from_dois(self):
        shortlist = []
        for x in self.mongoclient.works_openalex.find():
            if not self.collection.find_one({'id':x['id']}):
                item = {'doi':str(x['doi']).replace('https://doi.org/',''), 'id':x['id']}
        print(f'found {len(shortlist)} works in openalex without crossref results')
        tasks = []
        results = []
        async with httpx.AsyncClient() as client:
            for i, item in enumerate(shortlist):
                if not item['doi']:
                    continue
                task = asyncio.ensure_future(self.call_api(item, client))
                tasks.append(task)
                if len(tasks) == 50 or i == len(shortlist)-1:
                    result = await asyncio.gather(*tasks, return_exceptions=True)
                    results.extend(result)
                    print(f'{i} of {len(shortlist)} processed (+50)')
                    tasks = []

    def run(self):
        print('getting crossref results')
        asyncio.get_event_loop().run_until_complete(self.get_xml_crossref_results_from_dois())

class OpenAIREAPI():
    def __init__(self, mongoclient: MusMongoClient):
        self.paperlist = []
        self.mongoclient = mongoclient
        self.collection = mongoclient.items_openaire
        self.results = {'ids':[], 'dois':[], 'total':0}
        self.url = 'https://api.openaire.eu/search/researchProducts'
        self.token = getattr(settings, "OPENAIRETOKEN", "")
        self.refreshurl=f'https://services.openaire.eu/uoa-user-management/api/users/getAccessToken?refreshToken={self.token}'
        self.refresh_headers()
        self.client = httpx.AsyncClient()
    def run(self):
        self.get_paperlist()
        if not self.paperlist:
            print('no papers to query')
            return
        else:
            asyncio.get_event_loop().run_until_complete(self.get_results_from_dois())
    def refresh_headers(self):
        tokendata = httpx.get(self.refreshurl).json()
        token = tokendata.get("access_token")
        self.headers = {
            'Authorization': f'Bearer {token}'
        }

    def get_paperlist(self):
        ptable = table.Table(title="Retrieved openalex works")
        ptable.add_column("# checked", style="green")
        ptable.add_column("# added",style="magenta")
        i=0
        j=0
        numpapers = self.mongoclient.works_openalex.count_documents({})
        with progress.Progress() as p:
            task1 = p.add_task("getting dois to query openaire", total=numpapers)
            for paper in self.mongoclient.works_openalex.find(projection={'id':1, 'doi':1}):
                i+=1
                p.update(task1, advance=1)
                if paper.get('doi'):
                    if self.collection.find_one({'id':paper['id']}, projection={'id': 1}):
                        continue
                    j+=1
                    self.paperlist.append({'doi':paper['doi'].replace('https://doi.org/',''), 'id':paper['id']})
        ptable.add_row(str(i), str(j))
        console.print(ptable)
        

    async def get_results_from_dois(self):
        self.refresh_headers()
        numpapers = len(self.paperlist)
        with progress.Progress() as p:
            task1 = p.add_task("getting openaire results", total=numpapers)
            async with aiometer.amap(functools.partial(self.call_api), self.paperlist, max_at_once=5, max_per_second=2) as results:
                async for result in results:
                    p.update(task1, advance=1)
        console.print(f'added {self.results["total"]} items to openaire')

    async def call_api(self, item):
        async def httpget(client: httpx.AsyncClient, item: dict):
            doi = item.get('doi')
            params = {
                'doi': doi
            }
            print(f'querying openaire with params {params}')
            r = await client.get(self.url, params=params, headers=self.headers)
            print(f'got response {r.status_code}')
            try: 
                parsedxml = xmltodict.parse(r.text, attr_prefix='',dict_constructor=dict,cdata_key='text', process_namespaces=True)
            except Exception as e:
                console.print(f'error querying openaire for doi {item.get("doi")}: {e}')
                if ('token' in str(e)):
                    return 'token'
                else:
                    return 'error'
            
            if not parsedxml.get('response').get('results'):
                print(f'no results for {doi}')
                return False
            elif isinstance(parsedxml.get('response').get('results').get('result'),list):
                if len(parsedxml.get('response').get('results').get('result')) > 1:
                    print('multiple results (?) only returning the first')
                return parsedxml.get('response').get('results').get('result')[0].get('metadata').get('http://namespace.openaire.eu/oaf:entity').get('http://namespace.openaire.eu/oaf:result')
            else:
                return parsedxml.get('response').get('results').get('result').get('metadata').get('http://namespace.openaire.eu/oaf:entity').get('http://namespace.openaire.eu/oaf:result')
        
        metadata = await httpget(self.client,item)
        if metadata == 'token':
            console.print('refreshing openaire token...')
            try:
                self.refresh_headers()
                metadata = await httpget(self.client, item)
            except Exception as e:
                console.print(f'error refreshing openaire token: {e}')
                input('...')
                return False
        if metadata == 'error':
            return False
        id = item.get('id')
        doi = item.get('doi')
        if not metadata:
            metadata = {'id':id, 'doi':doi}
            self.collection.insert_one(metadata)
        else:
            metadata['id']=id
            self.collection.insert_one(metadata)
            self.results['total'] += 1
            self.results['ids'].append(id)
            self.results['dois'].append(doi)
        return True
class ZenodoAPI():
    def __init__(self, mongoclient):
        self.mongoclient = mongoclient
        self.results = {}

class SemanticScholarAPI():
    def __init__(self, mongoclient):
        self.mongoclient = mongoclient
        self.results = {}

class OpenCitationsAPI():
    def __init__(self, mongoclient):
        self.mongoclient = mongoclient
        self.results = {}

class ScopusAPI():
    def __init__(self, mongoclient):
        self.mongoclient = mongoclient
        self.results = {}

class ORCIDAPI():
    def __init__(self, mongoclient: MusMongoClient):
        self.mongoclient = mongoclient
        self.collection = self.mongoclient.items_orcid

        MONGOURL = getattr(settings, "MONGOURL")

        self.motorclient = motor.motor_asyncio.AsyncIOMotorClient(MONGOURL).metadata_unificiation_system
        self.motorcollection = self.motorclient['items_orcid']

        self.client = httpx.AsyncClient()
        self.results = {'ids':[], 'orcids':[], 'total':0}
        self.apiresponses = []
        self.access_token = getattr(settings, "ORCID_TOKEN", "")
        if not self.access_token:
            self.refresh_access_token()
        self.headers = {
            'Accept': 'application/orcid+xml',
            'Authorization': f'Bearer {self.access_token}'
        }
        self.namespaces = {
            'http://www.orcid.org/ns/internal':'internal',
            'http://www.orcid.org/ns/education':'education',
            'http://www.orcid.org/ns/distinction':'distinction',
            'http://www.orcid.org/ns/deprecated':'deprecated',
            'http://www.orcid.org/ns/other-name':'other-name',
            'http://www.orcid.org/ns/membership':'membership',
            'http://www.orcid.org/ns/error':'error',
            'http://www.orcid.org/ns/common':'common',
            'http://www.orcid.org/ns/record':'record',
            'http://www.orcid.org/ns/personal-details':'personal-details',
            'http://www.orcid.org/ns/keyword':'keyword',
            'http://www.orcid.org/ns/email':'email',
            'http://www.orcid.org/ns/external-identifier':'external-identifier',
            'http://www.orcid.org/ns/funding':'funding',
            'http://www.orcid.org/ns/preferences':'preferences',
            'http://www.orcid.org/ns/address':'address',
            'http://www.orcid.org/ns/invited-position':'invited-position',
            'http://www.orcid.org/ns/work':'work',
            'http://www.orcid.org/ns/history':'history',
            'http://www.orcid.org/ns/employment':'employment',
            'http://www.orcid.org/ns/qualification':'qualification',
            'http://www.orcid.org/ns/service':'service',
            'http://www.orcid.org/ns/person':'person',
            'http://www.orcid.org/ns/activities':'activities',
            'http://www.orcid.org/ns/researcher-url':'researcher-url',
            'http://www.orcid.org/ns/peer-review':'peer-review',
            'http://www.orcid.org/ns/bulk':'bulk',
            'http://www.orcid.org/ns/research-resource':'research-resource'
        }
    def refresh_access_token(self):
        url = 'https://orcid.org/oauth/token'
        header = {'Accept': 'application/json'}
        data = {
            'client_id':getattr(settings, "ORCID_CLIENT_ID", ""),
            'client_secret':getattr(settings, "ORCID_CLIENT_SECRET", ""),
            'grant_type':'client_credentials',
            'scope':'/read-public'
        }
        r = httpx.post(url, headers=header, data=data)
        self.access_token = r.json().get('access_token')
        self.refresh_token= r.json().get('refresh_token')
        self.headers = {
            'Accept': 'application/json',
            'Authorization': f'Bearer {r.json().get("access_token")}'
        }
        self.orcids = []

    async def get_orcidlist(self):
        ptable = table.Table(title="Retrieved ORCID iDs")
        ptable.add_column("authors checked", style="cyan")
        ptable.add_column("orcids added to list",style="magenta")
        checked=0

        numauths = await self.motorclient.authors_openalex.count_documents({'ids.orcid':{'$exists':True}})
        with progress.Progress() as p:
            task1 = p.add_task("getting orcid ids to query orcid api", total=numauths)
            async for auth in self.motorclient.authors_openalex.find({'ids.orcid':{'$exists':True}}, projection={'id':1, 'ids':1}):
                checked+=1
                p.update(task1, advance=1)
                if auth.get('ids').get('orcid'):
                    check = await self.motorcollection.find_one({'id':auth['id']}, projection={'id': 1, 'orcid-identifier': 1})
                    if check:
                        if check.get('orcid-identifier'):
                            continue
                    self.orcids.append({'orcid':auth['ids']['orcid'].replace('https://orcid.org/',''), 'id':auth['id']})
        ptable.add_row(str(checked), str(len(self.orcids)))
        console.print(ptable)
        
    def run(self):
        self.motorclient.get_io_loop().run_until_complete(self.get_orcidlist())
        self.motorclient.get_io_loop().run_until_complete(self.get_results_from_orcids())

    async def get_results_from_orcids(self):
        insertlist = []
        i=0
        with progress.Progress() as p:
            task1 = p.add_task("getting orcid results", total=len(self.orcids))
            async with aiometer.amap(functools.partial(self.call_api), self.orcids, max_at_once=10, max_per_second=10) as responses:
                async for response in responses:
                    self.apiresponses.append(response)
                    i=i+1
                    p.update(task1, advance=1)
                    if i >= 500 or len(self.apiresponses) == len(self.orcids):
                        newlist = [x for x in self.apiresponses if x not in insertlist]
                        insertlist.extend(newlist)
                        await self.motorcollection.update_many({'id':{'$in':[x['id'] for x in insertlist]}}, {'$set':x for x in insertlist}, upsert=True)
                        console.print(f'[bold green]{len(insertlist)}[/bold green] items added to mongodb ([bold cyan]+{len(newlist)}[/bold cyan])')
                        i=0
        
    async def call_api(self, item: dict):
        async def httpget(client: httpx.AsyncClient, orcid: str):
            def remove_colon_from_keys(item):
                if isinstance(item, dict):
                    newitem = {}
                    for key, value in item.items():
                        if ':' in key:
                            key=key.split(':')[-1]
                        newitem[key]=remove_colon_from_keys(value)
                    return newitem
                if isinstance(item, list):
                    return [remove_colon_from_keys(x) for x in item]
                else:
                    return item
            try:    
                url = f'https://pub.orcid.org/v3.0/{orcid}/record'
                r = None
                r = await client.get(url, headers=self.headers) 
                parsedxml = xmltodict.parse(r.text, process_namespaces=True, namespaces=self.namespaces, attr_prefix='')
                if r.status_code == 301 or parsedxml.get('error:error') or '' in 'error xmlns="http://www.orcid.org/ns/error"' in r.text:
                    if parsedxml.get('error:developer-message'):
                        if 'Moved Permanently' in parsedxml.get('error:developer-message'):
                            msg = parsedxml.get('error:developer-message')
                            foundorcids = re.findall(r'(\w{4}-){3}\w{4}', msg)
                            neworcid = foundorcids[0] # first found orcid should be  the new one
                            console.print(f'[bold red]ORCID {orcid}[/bold red] moved permanently to [bold cyan]{neworcid}[/bold cyan] - retrying')
                            return await httpget(client, neworcid)
                record = parsedxml.get('record:record')
                del record['xmlns']
                del record['path']
                return remove_colon_from_keys(record)
            except Exception as e:
                console.print(f'error querying ORCID for {orcid}: {e}')
                if r:
                    console.print(f'[magenta]r.text contents: \n {r.text}[/magenta]')
                else:
                    console.print('[red] no r.text received [/red]')
                return None
        result = await httpget(self.client,item['orcid'])
        if not result:
            print(f'no result for {item['orcid']}.')
            result = {'id':item['id']}
        else:
            result['id']=item['id']
            self.results['total'] += 1
            self.results['ids'].append(item['id'])
            self.results['orcids'].append(item['orcid'])
        return result
class COREAPI():
    def __init__(self, mongoclient):
        self.mongoclient = mongoclient
        self.results = {}

class BASEAPI():
    def __init__(self, mongoclient):
        self.mongoclient = mongoclient
        self.results = {}

class OCLCAPI():
    def __init__(self, mongoclient):
        self.mongoclient = mongoclient
        self.results = {}
