
from xclass_refactor.mus_mongo_client import MusMongoClient
from habanero import Crossref
from django.conf import settings

APIEMAIL = getattr(settings, "APIEMAIL", "no@email.com")

class DataCiteAPI():
    def __init__(self, mongoclient):
        self.mongoclient = mongoclient
        self.results = {}

class CrossrefAPI():
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
    def __init__(self, mongoclient):
        self.mongoclient = mongoclient
        self.results = {}

class ZenodoAPI():
    def __init__(self, mongoclient):
        self.mongoclient = mongoclient
        self.results = {}

class SemanticScholarAPI():
    def __init__(self, mongoclient):
        self.mongoclient = mongoclient
        self.results = {}
