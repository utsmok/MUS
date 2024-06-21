import motor.motor_asyncio
from pymongo import IndexModel

from mus_wizard.constants import MONGOURL


class MusMongoClient:
    '''
    creates connections to mongodb using asyncio motor client
    stores references to the relevant collections as attributes
    wraps search and update functions
    '''

    def __init__(self, database='metadata_unification_system'):
        self.mongoclient: motor.motor_asyncio.AsyncIOMotorClient = motor.motor_asyncio.AsyncIOMotorClient(
            MONGOURL)[database]
        self.works_openalex: motor.motor_asyncio.AsyncIOMotorCollection = self.mongoclient['works_openalex']
        self.authors_openalex: motor.motor_asyncio.AsyncIOMotorCollection = self.mongoclient['authors_openalex']
        self.sources_openalex: motor.motor_asyncio.AsyncIOMotorCollection = self.mongoclient['sources_openalex']
        self.funders_openalex: motor.motor_asyncio.AsyncIOMotorCollection = self.mongoclient['funders_openalex']
        self.topics_openalex: motor.motor_asyncio.AsyncIOMotorCollection = self.mongoclient['topics_openalex']
        self.institutions_openalex: motor.motor_asyncio.AsyncIOMotorCollection = self.mongoclient[
            'institutions_openalex']
        self.publishers_openalex: motor.motor_asyncio.AsyncIOMotorCollection = self.mongoclient['publishers_openalex']
        self.non_instution_authors_openalex: motor.motor_asyncio.AsyncIOMotorCollection = self.mongoclient[
            'non_instution_authors_openalex']

        self.authors_pure: motor.motor_asyncio.AsyncIOMotorCollection = self.mongoclient['authors_pure']
        self.openaire_cris_orgunits: motor.motor_asyncio.AsyncIOMotorCollection = self.mongoclient['openaire_cris_orgunits']
        self.openaire_cris_persons: motor.motor_asyncio.AsyncIOMotorCollection = self.mongoclient[
            'openaire_cris_persons']
        self.openaire_cris_publications: motor.motor_asyncio.AsyncIOMotorCollection = self.mongoclient[
            'openaire_cris_publications']
        self.items_pure_oaipmh: motor.motor_asyncio.AsyncIOMotorCollection = self.mongoclient['items_pure_oaipmh']
        self.items_pure_reports: motor.motor_asyncio.AsyncIOMotorCollection = self.mongoclient['items_pure_reports']
        self.items_datacite: motor.motor_asyncio.AsyncIOMotorCollection = self.mongoclient['items_datacite']
        self.items_crossref: motor.motor_asyncio.AsyncIOMotorCollection = self.mongoclient['items_crossref']
        self.items_openaire: motor.motor_asyncio.AsyncIOMotorCollection = self.mongoclient['items_openaire']
        self.items_zenodo: motor.motor_asyncio.AsyncIOMotorCollection = self.mongoclient['items_zenodo']
        self.items_semantic_scholar: motor.motor_asyncio.AsyncIOMotorCollection = self.mongoclient[
            'items_semantic_scholar']
        self.items_crossref_xml: motor.motor_asyncio.AsyncIOMotorCollection = self.mongoclient['items_crossref_xml']
        self.items_orcid: motor.motor_asyncio.AsyncIOMotorCollection = self.mongoclient['items_orcid']

        self.deals_journalbrowser: motor.motor_asyncio.AsyncIOMotorCollection = self.mongoclient['deals_journalbrowser']
        self.employees_peoplepage: motor.motor_asyncio.AsyncIOMotorCollection = self.mongoclient['employees_peoplepage']


    async def add_indexes(self):
        # works_openalex:
        # id, doi, itemtype, authorships.is_corresponding, authorships.institutions.id, authorships.institutions.ror, authorships.institutions.display_name, authorships.author.id, corresponding_institutions.id, corresponding_institutions.ror, corresponding_institution_ids, grants.funder, ids, locations.source.id, publication_year, type_crossref, updated_date, topics.id, title,
        await self.works_openalex.create_indexes([
            IndexModel('id'),
            IndexModel('doi'),
            IndexModel('itemtype'),
            IndexModel('authorships.is_corresponding'),
            IndexModel('authorships.institutions.id'),
            IndexModel('authorships.institutions.ror'),
            IndexModel('authorships.institutions.display_name'),
            IndexModel('authorships.author.id'),
            IndexModel('corresponding_institutions.id'),
            IndexModel('corresponding_institutions.ror'),
            IndexModel('corresponding_institution_ids'),
            IndexModel('grants.funder'),
            IndexModel('ids'),
            IndexModel('locations.source.id'),
            IndexModel('publication_year'),
            IndexModel('type_crossref'),
            IndexModel('updated_date'),
            IndexModel('topics.id'),
            IndexModel('title'),
        ])
        # authors_openalex:
        # id, name, updated_date, affiliations.institution.id, affiliations.institution.ror, affiliations.institution.display_name, topics.id, ids, orcid,
        await self.authors_openalex.create_indexes([
            IndexModel('id'),
            IndexModel('name'),
            IndexModel('updated_date'),
            IndexModel('affiliations.institution.id'),
            IndexModel('affiliations.institution.ror'),
            IndexModel('affiliations.institution.display_name'),
            IndexModel('topics.id'),
            IndexModel('ids'),
            IndexModel('orcid'),
        ])
        # authors_pure:
        # author_orcid, author_name, author_pureid, id, openalex_match, last_modified, affl_periods
        await self.authors_pure.create_indexes([
            IndexModel('author_orcid'),
            IndexModel('author_name'),
            IndexModel('author_pureid'),
            IndexModel('id'),
            IndexModel('openalex_match'),
            IndexModel('last_modified'),
            IndexModel('affl_periods'),
        ])
        # topics_openalex:
        # id
        await self.topics_openalex.create_indexes([
            IndexModel('id'),
        ])
        # sources_openalex:
        # id, updated_date, host_organization, ids, type
        await self.sources_openalex.create_indexes([
            IndexModel('id'),
            IndexModel('updated_date'),
            IndexModel('host_organization'),
            IndexModel('ids'),
            IndexModel('type'),
        ])
        # publishers_openalex:
        # id, updated_date, parent_publisher, ids, roles
        await self.publishers_openalex.create_indexes([
            IndexModel('id'),
            IndexModel('updated_date'),
            IndexModel('parent_publisher'),
            IndexModel('ids'),
            IndexModel('roles'),
        ])
        # institutions_openalex:
        # id, updated_date, ror, ids, roles, topics.id, type
        await self.institutions_openalex.create_indexes([
            IndexModel('id'),
            IndexModel('updated_date'),
            IndexModel('ror'),
            IndexModel('ids'),
            IndexModel('roles'),
            IndexModel('topics.id'),
            IndexModel('type'),
        ])
        # funders_openalex:
        # id, updated_date, ids, roles
        await self.funders_openalex.create_indexes([
            IndexModel('id'),
            IndexModel('updated_date'),
            IndexModel('ids'),
            IndexModel('roles'),
        ])
        # deals_journalbrowser:
        # id, APCDeal
        await self.deals_journalbrowser.create_indexes([
            IndexModel('id'),
            IndexModel('APCDeal'),
        ])
        # employees_peoplepage:
        # id, searchname, checkname, foundname, grouplist
        await self.employees_peoplepage.create_indexes([
            IndexModel('id'),
            IndexModel('searchname'),
            IndexModel('checkname'),
            IndexModel('foundname'),
            IndexModel('grouplist'),
        ])
        # items_crossref:
        # id, doi_data.doi, isbn, journal_article.doi_data.doi, content_item.doi_data.doi
        await self.items_crossref.create_indexes([
            IndexModel('id'),
            IndexModel('doi_data.doi'),
            IndexModel('isbn'),
            IndexModel('journal_article.doi_data.doi'),
            IndexModel('content_item.doi_data.doi'),
        ])
        # items_pure_oaipmh:
        # pure_identifier, title.value, identifier, identifier.type
        await self.items_pure_oaipmh.create_indexes([
            IndexModel('pure_identifier'),
            IndexModel('title.value'),
            IndexModel('identifier'),
            IndexModel('identifier.type'),
        ])
