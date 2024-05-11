
from xclass_refactor.models.models import Funder, Grant, Topic, Organization
from xclass_refactor.models.work import WorkOpenAlexData, WorkPureData, WorkOtherData, Work, Abstract, OAStatus, MUSTypes, CrossrefTypes, OpenAlexTypes, Authorship
from xclass_refactor.models.source import Source, Publisher, Location, DealData
from xclass_refactor.models.author import AuthorOpenAlexData, AuthorPureData, AuthorOtherData, AuthorEmployeeData, Author, Affiliation
from xclass_refactor.constants import MONGOURL, ROR, INSTITUTE_ALT_NAME, INSTITUTE_NAME
import motor.motor_asyncio
from rich.console import Console
import asyncio
from datetime import datetime, timedelta
from collections import defaultdict
'''
Ingest the mongoDB data into DjangoModels.
'''
class InsertManager():
    '''
    Manager that parses data from MongoDB and creates DjangoModels.
    
    '''
    def __init__(self):
        self.motorclient = motor.motor_asyncio.AsyncIOMotorClient(MONGOURL).metadata_unificiation_system
        # datalist holds the created models
        # key = model type
        # value = list of model instances
        self.datalist = defaultdict(list) 

    async def run(self):
        
        '''
        First make all items that do not have relations to other items as fields:
        - Author
            - AuthorEmployeeData
            - AuthorOtherData
            - AuthorPureData
            - AuthorOpenAlexData
        - Funder
        - Topic

        Secondly, Sources/Publishers are a bit messy in terms of linkage, so make them at the same time:
        - Source
        - DealData
        - Organization
        - Publisher (NOTE: has related field to itself, so start with publishers without host_orgs)

        Then add Works & links to other items:
        - Work
            - WorkOpenAlexData
            - WorkPureData
            - WorkOtherData
            - Abstract
        - Authorship
        - Location
        - Grant
        '''

    async def make_topics(self):
        async def create_topic(data):
            try:
                topicdict = {
                    'description':data.get('description'),
                    'name':data.get('display_name'),
                    'domain':data.get('domain').get('display_name'),
                    'field':data.get('field').get('display_name'),
                    'openalex_id':data.get('id'),
                    'works_count':data.get('works_count'),
                    'keywords':data.get('keywords'),
                    'wikipedia':data.get('ids').get('wikipedia') if data.get('ids') else None,
                    'subfield':data.get('subfield').get('display_name')
                }
                
                if not await Topic.objects.filter(openalex_id=topicdict['openalex_id']).aexists():
                    topic = Topic(**topicdict)
                    await topic.asave()
                    self.datalist['Topic'].append(topic)
                    return True
                else:
                    return False
            except Exception as e:
                print(e)
                return False
        
        numcreated = 0
        checked = 0
        async for data in self.motorclient['topics_openalex'].find():
            checked+=1
            i = await create_topic(data)
            if i:
                numcreated+=1

        print(f'Created {numcreated} topics from {checked} mongodb rows')
        
            
    async def make_author(self, search_ids: dict) -> bool:
        '''
        makes an Author() instance including one-to-one relations
        parameters:
        search_id: dict -- search for these ids of type key with value (str) in mongoDB. Options are:
            - openalex_id
            - orcid
            - pure_id
            - scopus_id
            - isni
        returns:
        Author: An Author() instance; already added to the DB with one-to-one relations in place
        '''
        async def add_employee_data(search_ids) -> AuthorEmployeeData:
            author_employee_data = AuthorEmployeeData()
            self.datalist['AuthorEmployeeData'].append(author_employee_data)
            return author_employee_data
        async def add_other_data(search_ids) -> AuthorOtherData:
            author_other_data = AuthorOtherData()
            self.datalist['AuthorOtherData'].append(author_other_data)
            return author_other_data
        async def add_pure_data(search_ids) -> AuthorPureData:
            author_pure_data = AuthorPureData()
            self.datalist['AuthorPureData'].append(author_pure_data)
            return author_pure_data
        async def add_openalex_data(search_ids) -> AuthorOpenAlexData:
            author_openalex_data = AuthorOpenAlexData()
            self.datalist['AuthorOpenAlexData'].append(author_openalex_data)
            return author_openalex_data

        linked_items = await asyncio.gather(add_employee_data(search_ids), add_other_data(search_ids), add_pure_data(search_ids), add_openalex_data(search_ids))
        author_dict = {
            'name': '',
            'title_prefix':'',
            'title_suffix':'',
            'first_name':'',
            'last_name':'',
            'initials':'',
            'alternative_names':'',
            'employee':'',
            'orcid':'',
            'pure_id':'',
            'isni':'',
            'scopus_id':'',
            'openalex_id':'',
        }
        # go through data in linked_items, select best options to add to author_dict
        # don't forget to add one-to-one relations to the linked items
        # then make Author() instance from the dict

        author = Author()
        self.datalist['Author'].append(author)
        await author.asave()
        # if author is created: return True, else: return False
        
    async def make_funder(self):
        ...
    async def make_source(self):
        async def add_deal():
            ...
        ...
    async def make_grant(self):
        ...
    
    async def make_organization(self):
        ...

    async def make_location(self):
        ...
    async def make_publisher(self):
        ...
    async def make_abstract(self):
        ...
    





