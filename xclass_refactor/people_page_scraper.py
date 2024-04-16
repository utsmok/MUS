class PeoplePageScraper():
    def __init__(self, mongoclient):
        self.mongoclient = mongoclient
        self.results = {}
