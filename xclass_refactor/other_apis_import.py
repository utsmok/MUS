
from xclass_refactor.mus_mongo_client import MusMongoClient
from habanero import Crossref
from django.conf import settings
import httpx
from datetime import datetime, timedelta
import xmltodict
from rich.console import Console
from rich import table, print, text, progress
import rich
import concurrent.futures
import asyncio
import aiometer
import functools

APIEMAIL = getattr(settings, "APIEMAIL", "no@email.com")
client = httpx.AsyncClient()
console = Console()
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
        self.token = getattr(settings, "OPENAIRETOKEN", "")
        self.refreshurl=f'https://services.openaire.eu/uoa-user-management/api/users/getAccessToken?refreshToken={self.token}'
    def run(self):
        self.get_paperlist()
        if not self.paperlist:
            print('no papers to query')
            return
        else:
            asyncio.get_event_loop().run_until_complete(self.get_results_from_dois())
    def get_token(self):
        tokendata = httpx.get(self.refreshurl).json()
        return tokendata.get("access_token")
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
                if paper.get('doi'):
                    if self.collection.find_one({'id':paper['id']}, projection={'id': 1}):
                        continue
                    j+=1
                    self.paperlist.append({'doi':paper['doi'].replace('https://doi.org/',''), 'id':paper['id']})
                p.update(task1, advance=1)

        ptable.add_row(str(i), str(j))
        console.print(ptable)
        

    async def get_results_from_dois(self):
        time = datetime.now()
        url = 'https://api.openaire.eu/search/researchProducts'
        headers = {
            'Authorization': f'Bearer {self.get_token()}'
        }
        numpapers = len(self.paperlist)
        with progress.Progress() as p:
            task1 = p.add_task("getting openaire results", total=numpapers)
            async with aiometer.amap(functools.partial(self.call_api, url, headers), self.paperlist, max_at_once=5, max_per_second=2) as results:
                if datetime.now()-time > timedelta(minutes=50):
                    try:
                        headers = {
                            'Authorization': f'Bearer {self.get_token()}'
                        }
                        time = datetime.now()
                    except Exception as e:
                        console.print(f'error {e} while refreshing OpenAire token')
                        input('...')
                async for result in results:
                    if result:
                        p.update(task1, advance=1)
        console.print(f'added {self.results["total"]} items to openaire')

    async def call_api(self, url, headers, item):
        doi = item.get('doi')
        id = item.get('id')
        params = {
            'doi': doi
        }
        
        try:
            r = await client.get(url, params=params, headers=headers)
        except Exception as e:
            console.print(f'error querying openaire for doi {doi}: {e}')
            return False
        try:
            if not r.text:
                return False
            metadata = xmltodict.parse(r.text, attr_prefix='',dict_constructor=dict,cdata_key='text', process_namespaces=True).get('response').get('results').get('result').get('metadata').get('http://namespace.openaire.eu/oaf:entity').get('http://namespace.openaire.eu/oaf:result')
        except Exception as e:
            console.print(f'error parsing openaire result for doi {doi}: {e}')
            return False
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