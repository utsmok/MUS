from xclass_refactor.mus_mongo_client import MusMongoClient

class PeoplePageScraper():
    def __init__(self, mongoclient: MusMongoClient):
        self.mongoclient = mongoclient
        self.results = {}
