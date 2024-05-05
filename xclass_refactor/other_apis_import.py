
from xclass_refactor.mus_mongo_client import MusMongoClient
from habanero import Crossref
from xclass_refactor.constants import ROR, MONGOURL, APIEMAIL, OPENAIRETOKEN, ORCID_CLIENT_ID, ORCID_CLIENT_SECRET, ORCID_ACCESS_TOKEN
import httpx
import xmltodict
from rich.console import Console
from rich import table, print, progress
import asyncio
from xclass_refactor.generics import GenericAPI
import re
from datetime import datetime, timedelta
import motor.motor_asyncio
console = Console()

'''
---------------- Not implemented yet ----------------
'''

class SemanticScholarAPI(GenericAPI):
    def __init__(self):
        ...

class OCLCAPI(GenericAPI):
    def __init__(self):
        ...

class OpenCitationsAPI(GenericAPI):
    def __init__(self):
        ...

class ZenodoAPI(GenericAPI):
    def __init__(self):
        ...

class ScopusAPI(GenericAPI):
    def __init__(self):
        ...

class COREAPI(GenericAPI):
    def __init__(self):
        ...

class BASEAPI(GenericAPI):
    def __init__(self):
        ...

'''
---------------------- Needs updates ---------------------------
'''
class CrossrefAPI():
    '''
    TODO: subclass from GenericAPI
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
'''
---------------------------- Done ------------------------------
'''
class DataCiteAPI(GenericAPI):
    def __init__(self):
        super().__init__('items_datacite', 'doi')
        self.set_api_settings(headers = {"accept": "application/vnd.api+json"},
                            max_per_second=5,
                            max_at_once=5,
                            )

    async def get_ut_items(self) -> None:
        ut_results = []
        url = f"https://api.datacite.org/dois?affiliation=true&query=creators.affiliation.affiliationIdentifier:%22{ROR}%22&page[size]=1000&affiliation=true&detail=true&publisher=true"
        try:
            response = await self.httpxclient.get(url, headers=self.api_settings['headers'])
            if response.status_code != 200:
                raise Exception(f"DataCite API response code {response.status_code}")
            response_json = response.json()
        except Exception as e:
            print(f'Error while retrieving all UT datacite items: {e}')
        for item in response_json["data"]:
            tmp={}
            attrs=item['attributes']
            for key, value in attrs.items():
                if value is not None:
                    if isinstance(value, list):
                        if value!=[]:
                            tmp[key]=value
                    elif isinstance(value, dict):
                        if value!={}:
                            tmp[key]=value
                    elif isinstance(value, str):
                        if value != "":
                            tmp[key]=value
            tmp['id']=item['id']
            tmp['type']=item['type']
            tmp['relationships']=item['relationships']
            ut_results.append(tmp)

        return ut_results
    async def make_itemlist(self) -> None:
        ptable = table.Table(title=f"{self.item_id_type}s from OpenAlex works")
        ptable.add_column("# checked", style="green")
        ptable.add_column("# added",style="magenta")
        i=0

        numpapers = await self.motorclient['works_openalex'].count_documents({})
        with progress.Progress() as p:
            task1 = p.add_task(f"getting {self.item_id_type}s to query DataCite", total=numpapers)
            async for paper in self.motorclient['works_openalex'].find(projection={'id':1, 'doi':1}):
                i+=1
                p.update(task1, advance=1)
                if paper.get('doi'):
                    if await self.collection.find_one({'id':paper['id']}, projection={'id': 1}):
                        continue
                    self.itemlist.append({self.item_id_type:paper['doi'].replace('https://doi.org/',''), 'id':paper['id']})
        ptable.add_row(str(i), str(len(self.itemlist)))
        console.print(ptable)

    async def call_api(self, item) -> dict:
        async def httpget(doi: str):
            try:
                url = f'https://api.datacite.org/dois?query=relatedIdentifiers.relatedIdentifier:{doi}&affiliation=true&publisher=true&detail=true'
                r = await self.httpxclient.get(url)
                return r.json()
            except Exception as e:
                print(f'error querying datacite for doi {doi}: {e}')
                return None
        doi = item.get('doi')
        id = item.get('id')
        result = await httpget(doi)
        if not result:
            return {'id': id, 'doi': doi}
        else:
            result['id']=id
            return result
class OpenAIREAPI(GenericAPI):
    def __init__(self):
        '''
        Creates a new OpenAIREAPI instance
        call OpenAIREAPI().run() to execute standard queries & update mongodb -- no parameters needed.
        see docs for advanced usage.
        '''
        super().__init__('items_openaire', 'doi')
        self.motorclient = motor.motor_asyncio.AsyncIOMotorClient(MONGOURL).metadata_unificiation_system
        self.collection = self.motorclient['items_openaire']
        self.refreshtime = datetime.now() - timedelta(hours=3)
        self.api_settings['tokens'] = {'refresh_token':OPENAIRETOKEN}
        self.set_api_settings(
                            url='https://api.openaire.eu/search/researchProducts',
                            headers={'Authorization': f'Bearer {self.update_access_token()}'},
                            tokens={'refresh_token': OPENAIRETOKEN,
                                    'access_token':''
                            },
                            max_at_once=5,
                            max_per_second=2
                        )

    def update_access_token(self) -> str:
        if not self.refreshtime or datetime.now() - self.refreshtime > timedelta(minutes=55):
            try:
                self.refreshtime = datetime.now()
                tokendata = httpx.get(f'https://services.openaire.eu/uoa-user-management/api/users/getAccessToken?refreshToken={self.api_settings['tokens']['refresh_token']}').json()
                self.api_settings['tokens']['access_token'] = tokendata.get("access_token")
            except Exception as e:
                print(f'error refreshing OpenAIRE access token: {e}')
                raise LookupError('Cannot refresh OpenAIRE access token')
        return self.api_settings['tokens']['access_token']

    async def make_itemlist(self):
        ptable = table.Table(title=f"{self.item_id_type}s from OpenAlex works")
        ptable.add_column("# checked", style="green")
        ptable.add_column("# added",style="magenta")
        i=0

        numpapers = await self.motorclient['works_openalex'].count_documents({})
        with progress.Progress() as p:
            task1 = p.add_task(f"getting {self.item_id_type}s to query openaire", total=numpapers)
            async for paper in self.motorclient['works_openalex'].find({}, projection={'id':1, 'doi':1}, sort=[('id', 1)]):
                i+=1
                p.update(task1, advance=1)
                if paper.get('doi'):
                    if await self.collection.find_one({'id':paper['id']}, projection={'id': 1}):
                        continue
                    self.itemlist.append({self.item_id_type:paper['doi'].replace('https://doi.org/',''), 'id':paper['id']})
        ptable.add_row(str(i), str(len(self.itemlist)))
        console.print(ptable)

    async def call_api(self, item):
        async def httpget(item: dict):
            doi = item.get('doi')
            params = {
                'doi': doi
            }
            r = await self.httpxclient.get(self.api_settings['url'], params=params, headers=self.api_settings['headers'])
            try:
                parsedxml = xmltodict.parse(r.text, attr_prefix='',dict_constructor=dict,cdata_key='text', process_namespaces=True)
            except Exception as e:
                console.print(f'error querying openaire for doi {item.get("doi")}: {e}')
                if ('token' in str(e)):
                    self.update_access_token()
                    return await httpget(item)
                else:
                    return False
            if not parsedxml.get('response').get('results'):
                print(f'no results for {doi}')
                return False
            elif isinstance(parsedxml.get('response').get('results').get('result'),list):
                if len(parsedxml.get('response').get('results').get('result')) > 1:
                    print('multiple results (?) only returning the first')
                return parsedxml.get('response').get('results').get('result')[0].get('metadata').get('http://namespace.openaire.eu/oaf:entity').get('http://namespace.openaire.eu/oaf:result')
            else:
                return parsedxml.get('response').get('results').get('result').get('metadata').get('http://namespace.openaire.eu/oaf:entity').get('http://namespace.openaire.eu/oaf:result')
        self.update_access_token()
        id = item.get('id')
        doi = item.get('doi')
        result = await httpget(item)
        if result:
            result['id']=id
            self.results['total'] += 1
            self.results['ids'].append(id)
            self.results['dois'].append(doi)
        else:
            result = {'id':id, 'doi':doi}
        return result
    

class ORCIDAPI(GenericAPI):
    NAMESPACES = {
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
    def __init__(self) -> None:
        super().__init__('items_orcid', 'orcid')
        self.api_settings['tokens']['access_token'] = ORCID_ACCESS_TOKEN
        self.refresh_access_token()
        self.set_api_settings(headers={'Accept': 'application/orcid+xml', 'Authorization': f'Bearer {self.api_settings['tokens']['access_token']}'}, max_at_once=10, max_per_second=10)

    def refresh_access_token(self) -> None:
        if not self.api_settings['tokens']['access_token']:
            url = 'https://orcid.org/oauth/token'
            header = {'Accept': 'application/json'}
            data = {
                'client_id':ORCID_CLIENT_ID,
                'client_secret':ORCID_CLIENT_SECRET,
                'grant_type':'client_credentials',
                'scope':'/read-public'
            }
            r = httpx.post(url, headers=header, data=data)
            self.api_settings['tokens']['access_token'] = r.json().get('access_token')
            self.api_settings['tokens']['refresh_token'] = r.json().get('refresh_token')

    async def make_itemlist(self) -> None:
        ptable = table.Table(title="Retrieved ORCID iDs")
        ptable.add_column("authors checked", style="cyan")
        ptable.add_column("orcids added to list",style="magenta")
        checked=0
        numauths = await self.motorclient['authors_openalex'].count_documents({'ids.orcid':{'$exists':True}})
        with progress.Progress() as p:
            task1 = p.add_task(f"getting {self.item_id_type}s", total=numauths)
            async for auth in self.motorclient['authors_openalex'].find({'ids.orcid':{'$exists':True}}, projection={'id':1, 'ids':1}):
                checked+=1
                p.update(task1, advance=1)
                if auth.get('ids').get('orcid'):
                    check = await self.collection.find_one({'id':auth['id']}, projection={'id': 1, 'orcid-identifier': 1})
                    if check:
                        if check.get('orcid-identifier'):
                            continue
                    self.itemlist.append({self.item_id_type:auth['ids']['orcid'].replace('https://orcid.org/',''), 'id':auth['id']})
        ptable.add_row(str(checked), str(len(self.itemlist)))
        console.print(ptable)

    async def call_api(self, item: dict) -> dict:
        async def httpget(item_id: str):
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
                url = f'https://pub.orcid.org/v3.0/{item_id}/record'
                r = None
                r = await self.httpxclient.get(url, headers=self.api_settings['headers'])
                parsedxml = xmltodict.parse(r.text, process_namespaces=True, namespaces=self.NAMESPACES, attr_prefix='')
                if r.status_code == 301 or parsedxml.get('error:error') or '' in 'error xmlns="http://www.orcid.org/ns/error"' in r.text:
                    if parsedxml.get('error:developer-message'):
                        if 'Moved Permanently' in parsedxml.get('error:developer-message'):
                            msg = parsedxml.get('error:developer-message')
                            foundorcids = re.findall(r'(\w{4}-){3}\w{4}', msg)
                            neworcid = foundorcids[0] # first found orcid should be  the new one
                            console.print(f'[bold red]ORCID {item_id}[/bold red] moved permanently to [bold cyan]{neworcid}[/bold cyan] - retrying')
                            return await httpget(neworcid)
                record = parsedxml.get('record:record')
                del record['xmlns']
                del record['path']
                return remove_colon_from_keys(record)
            except Exception as e:
                console.print(f'error querying for ORCID {item_id}: {e}')
                
                return None

        result = await httpget(item[self.item_id_type])
        if isinstance(result, dict):
            result['id'] = item['id']
        if not result:
            return {'id': item['id']}
        return result