from django.conf import settings
from pymongo import MongoClient


class MusMongoClient:
    '''
    creates connections to mongodb
    stores references to the relevant collections as attributes
    wraps search and update functions
    '''
    def __init__(self):
        MONGOURL = getattr(settings, "MONGOURL")
        self.mongoclient = MongoClient(MONGOURL)['metadata_unificiation_system']

        self.works_openalex = self.mongoclient['works_openalex']
        self.authors_openalex = self.mongoclient['authors_openalex']
        self.sources_openalex = self.mongoclient['sources_openalex']
        self.funders_openalex = self.mongoclient['funders_openalex']
        self.topics_openalex = self.mongoclient['topics_openalex']
        self.institutions_openalex = self.mongoclient['institutions_openalex']

        self.authors_pure = self.mongoclient['authors_pure']

        self.items_pure_oaipmh = self.mongoclient['items_pure_oaipmh']
        self.items_pure_reports = self.mongoclient['items_pure_reports']
        self.items_datacite = self.mongoclient['items_datacite']
        self.items_crossref = self.mongoclient['items_crossref']
        self.items_openaire = self.mongoclient['items_openaire']
        self.items_zenodo = self.mongoclient['items_zenodo']
        self.items_semantic_scholar = self.mongoclient['items_semantic_scholar']
        self.items_crossref_xml = self.mongoclient['items_crossref_xml']

        self.deals_journalbrowser = self.mongoclient['deals_journalbrowser']
        self.employees_peoplepage = self.mongoclient['employees_peoplepage']

