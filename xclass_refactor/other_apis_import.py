
from xclass_refactor.mus_mongo_client import MusMongoClient
from habanero import Crossref
from django.conf import settings
import httpx
from datetime import datetime, timedelta
import xmltodict
from rich.console import Console
from rich import table, print, text, progress

APIEMAIL = getattr(settings, "APIEMAIL", "no@email.com")
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
        if not self.mongoclient:
            self.mongoclient = MusMongoClient()
        self.collection = mongoclient.items_crossref
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
    def run(self):
        print('getting crossref results')
        self.get_crossref_results_from_dois()

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
            self.get_results_from_dois()
    def get_token(self):
        tokendata = httpx.get(self.refreshurl).json()
        return tokendata.get("access_token")
    def get_paperlist(self):
        temp = {}
        ptable = table.Table(title="Retrieved openalex works")
        ptable.add_column("# checked", style="green")
        ptable.add_column("# added",style="magenta")
        i=0
        j=0
        numpapers = self.mongoclient.works_openalex.count_documents({})
        with progress.Progress() as p:
            task1 = p.add_task("getting dois to query openaire", total=numpapers)
            for paper in self.mongoclient.works_openalex.find():
                i+=1
                if paper.get('doi'):
                    j+=1
                    temp[paper.get('id')]=paper['doi'].replace('https://doi.org/','')
                p.update(task1, advance=1)

        ptable.add_row(str(i), str(j))
        console.print(ptable)
        with console.status("building paperlist...", spinner="aesthetic"):
            self.paperlist = [{'doi':temp[id], 'id':id} for id in temp.keys()]

        if not isinstance(self.paperlist, list):
            self.paperlist = [self.paperlist]
        for id in temp.keys():
            if self.collection.find_one({'id':id}):
                continue
            else:
                self.paperlist.append({'doi':temp[id], 'id':id})
        print(f'found {len(self.paperlist)} papers to query')
    def get_results_from_dois(self):
        time = datetime.now()
        url = 'https://api.openaire.eu/search/researchProducts'
        headers = {
            'Authorization': f'Bearer {self.get_token()}'
        }
        numpapers = len(self.paperlist)
        with progress.Progress() as p:
            task1 = p.add_task("getting openaire results", total=numpapers)
            for paper in self.paperlist:
                params = {'doi':paper['doi']}
                try:
                    r = httpx.get(url, params=params, headers=headers)
                except Exception as e:
                    print(f'error querying openaire for doi {paper["doi"]}: {e}')
                    continue
                try:
                    metadata = xmltodict.parse(r.text, attr_prefix='',dict_constructor=dict,cdata_key='text', process_namespaces=True).get('response').get('results').get('result').get('metadata').get('http://namespace.openaire.eu/oaf:entity').get('http://namespace.openaire.eu/oaf:result')
                except Exception as e:
                    print(f'error parsing openaire result for doi {paper["doi"]}: {e}')
                    headers = {
                            'Authorization': f'Bearer {self.get_token()}'
                        }
                    time = datetime.now()
                    continue

                metadata['id']=paper['id']
                self.collection.insert_one(metadata)
                self.results['total'] += 1
                self.results['ids'].append(paper['id'])
                self.results['dois'].append(paper['doi'])
                if datetime.now()-time > timedelta(minutes=50):
                    try:
                        headers = {
                            'Authorization': f'Bearer {self.get_token()}'
                        }
                        time = datetime.now()
                    except Exception as e:
                        print(f'error {e} while refreshing OpenAire token')
                        break
                p.update(task1, advance=1)
        print(f'added {self.results["total"]} items to openaire')

class ZenodoAPI():
    def __init__(self, mongoclient):
        self.mongoclient = mongoclient
        self.results = {}

class SemanticScholarAPI():
    def __init__(self, mongoclient):
        self.mongoclient = mongoclient
        self.results = {}