
from xclass_refactor.difficult_models.models import Funder, Grant, Topic, Organization
from xclass_refactor.difficult_models.work import WorkOpenAlexData, WorkPureData, WorkOtherData, Work, Abstract, OAStatus, MUSTypes, CrossrefTypes, OpenAlexTypes, Authorship
from xclass_refactor.difficult_models.source import Source, Publisher, Location, DealData
from xclass_refactor.difficult_models.author import AuthorOpenAlexData, AuthorPureData, AuthorOtherData, AuthorEmployeeData, Author, Affiliation
from xclass_refactor.constants import MONGOURL, ROR, INSTITUTE_ALT_NAME, INSTITUTE_NAME
import motor.motor_asyncio
from rich.console import Console
import asyncio
from datetime import datetime, timedelta
from collections import defaultdict
from nameparser import HumanName
from rich import print
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

        #await self.make_topics()
        await self.make_author({'openalex_id':'https://openalex.org/A5070064397'})

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
        async def add_openalex_data(search_ids) -> AuthorOpenAlexData:
            if 'openalex_id' in search_ids:
                data = await self.motorclient['authors_openalex'].find_one({'id':search_ids['openalex_id']})
                if data:
                    author_openalex_dict = {
                        'name':data.get('display_name'),
                        'name_alternatives':data.get('display_name_alternatives'),
                        'openalex_id':data.get('id'),
                        'openalex_created_date':data.get('created_date'),
                        'openalex_updated_date':data.get('updated_date'),
                        'orcid':data.get('orcid'),
                        'scopus':data.get('ids').get('scopus') if data.get('ids') else None,
                        'twitter':data.get('ids').get('twitter') if data.get('ids') else None,
                        'wikipedia':data.get('ids').get('wikipedia') if data.get('ids') else None,
                        'impact_factor':data.get('summary_stats').get('2yr_mean_citedness'),
                        'h_index':data.get('summary_stats').get('h_index'),
                        'i10_index':data.get('summary_stats').get('i10_index'),
                        'works_api_url':data.get('works_api_url'),
                        'works_count':data.get('works_count'),
                        'cited_by_count':data.get('cited_by_count'),
                        'counts_by_year':data.get('counts_by_year'),
                    }
                    print('author_openalex_dict')
                    print(author_openalex_dict)
                    author_openalex_data : AuthorOpenAlexData = AuthorOpenAlexData(**author_openalex_dict)
                    await author_openalex_data.asave()
                    affiliations_list: list[dict] = []
                    for affl in data.get('affiliations'):
                        if not await Organization.objects.filter(openalex_id=affl.get('institution').get('id')).aexists():
                            org = await self.make_organization(affl.get('institution').get('id'))
                        else:
                            org = await Organization.objects.filter(openalex_id=affl.get('institution').get('id')).first()
                        affil = {
                            'years':affl.get('years'),
                            'organization':org,
                            #'author':author that will be made in this function
                        }
                        affiliations_list.append(affil)
                    self.datalist['AuthorOpenAlexData'].append(author_openalex_data)
                    return {'author_openalex_data':author_openalex_data, 'affiliations_list':affiliations_list}
            return {}
        async def add_employee_data(search_ids) -> AuthorEmployeeData:
            if 'openalex_id' in search_ids:
                data = await self.motorclient['employees_peoplepage'].find_one({'id':search_ids['openalex_id']})
                if data:
                    author_employee_dict = {
                        'employment_type':data.get('affiliation') if isinstance(data.get('affiliation'), str) else data.get('affiliation')[0],
                        'position':data.get('position'),
                        'profile_url':data.get('profile_url'),
                        'research_url':data.get('research_url') if data.get('research_url') else None,
                        'avatar_url':data.get('avatar_url'),
                        'email':data.get('email'),
                        'first_name':data.get('first_name'),
                        'fullname':data.get('fullname'),
                        'name':data.get('name'),
                        'name_alternatives':data.get('name_alternatives'),
                        'grouplist':data.get('grouplist'),
                        'name_searched_for':data.get('searchname'),
                        'name_found':data.get('foundname'),
                        'similarity':data.get('similarity'),
                    }
                    print('author_employee_dict')
                    print(author_employee_dict)
                    author_employee_data : AuthorEmployeeData = AuthorEmployeeData(**author_employee_dict)
                    await author_employee_data.asave()
                    self.datalist['AuthorEmployeeData'].append(author_employee_data)
                    return {'author_employee_data':author_employee_data}
            return {}
        async def add_other_data(search_ids) -> AuthorOtherData:
            ...
            #author_other_data = AuthorOtherData()
            #self.datalist['AuthorOtherData'].append(author_other_data)
            return {}
        async def add_pure_data(search_ids) -> AuthorPureData:
            data = None
            if 'pureid' in search_ids:
                data = await self.motorclient['authors_pure'].find_one({'author_pureid':search_ids['pureid']})
            if not data and 'openalex_id' in search_ids:
                data = await self.motorclient['authors_pure'].find_one({'id':search_ids['openalex_id']})
            if not data and 'orcid' in search_ids:
                data = await self.motorclient['authors_pure'].find_one({'author_orcid':search_ids['orcid']})
            if not data and 'scopus_id' in search_ids:
                data = await self.motorclient['authors_pure'].find_one({'author_scopus_id':search_ids['scopus_id']})
            if not data and 'isni' in search_ids:
                data = await self.motorclient['authors_pure'].find_one({'author_isni':search_ids['isni']})
            if data:
                author_pure_dict = {
                    'name':data.get('author_name'),
                    'last_name':data.get('author_last_name'),
                    'first_names':data.get('author_first_names'),
                    'pureid':data.get('author_pureid'),
                    'orcid':data.get('author_orcid'),
                    'isni':data.get('author_isni'),
                    'scopus_id':data.get('author_scopus_id'),
                    'links':data.get('author_links'),
                    'default_publishing_name':data.get('author_default_publishing_name'),
                    'known_as_name':data.get('author_known_as_name'),
                    'uuid':data.get('author_uuid'),
                    'last_modified':data.get('last_modified')[0],
                    'affl_periods':data.get('affl_periods'),
                    'org_names':data.get('org_names'),
                    'org_uuids':data.get('org_uuids'),
                    'org_pureids':data.get('org_pureids'),
                    'faculty_name':data.get('faculty_name'),
                    'faculty_pureid':data.get('faculty_pureid'),
                    'affl_start_date':data.get('affl_start_date'),
                    'affl_end_date':data.get('affl_end_date'),
                }
                print('author_pure_dict')
                print(author_pure_dict)
                author_pure_data : AuthorPureData = AuthorPureData(**author_pure_dict)
                await author_pure_data.asave()
                self.datalist['AuthorPureData'].append(author_pure_data)
                return {'author_pure_data':author_pure_data}
            return {}


        linked_data = await asyncio.gather(add_employee_data(search_ids), add_pure_data(search_ids), add_openalex_data(search_ids))
        employeedata = linked_data[0]
        puredata = linked_data[1]
        openalexdata = linked_data[2]

        # go through data in linked_items, select best options to add to author_dict

        if openalexdata.get('author_openalex_data'):
            oa = openalexdata['author_openalex_data']
        else:
            oa = {'orcid':None,'scopus':None,'openalex_id':None,'name':None,'name_alternatives':None}
        if puredata.get('author_pure_data'):
            pure = puredata['author_pure_data']
        else:
            pure = {'orcid':None,'scopus_id':None,'name':None,'name_alternatives':None, 'pureid':None, 'isni':None}
        if employeedata.get('author_employee_data'):
            empl = employeedata['author_employee_data']
        else:
            empl = {'profile_url':None}
        
        humanname = HumanName(oa.name)

        author_dict = {
            'name': oa.name,
            'title_prefix':humanname.title,
            'title_suffix':humanname.suffix,
            'first_name':humanname.first,
            'last_name':humanname.last,
            'initials':humanname.initials(),
            'alternative_names':oa.name_alternatives,
            'employee':True if empl.profile_url else False,
            'orcid':oa.orcid if oa.orcid else pure.orcid if pure.orcid else None,
            'pure_id':pure.pureid if pure.pureid else None,
            'isni':pure.isni if pure.isni else None,
            'scopus_id':oa.scopus if oa.scopus else pure.scopus_id if pure.scopus_id else None,
            'openalex_id':oa.openalex_id,
        }

        author = Author(author_dict)
        await author.asave()
        if employeedata.get('author_employee_data'):
            author.employee_data = empl
        if puredata.get('author_pure_data'):
            author.pure_data = pure
        if openalexdata.get('author_openalex_data'):
            author.openalex_data = oa
        if openalexdata.get('affiliations_list') and False:
            # make affiliations and add to author
            for affl_data in openalexdata['affiliations_list']:
                affl = {
                    'organization':affl_data['organization'],
                    'years':affl_data['years'],
                    'author':author
                }
                affiliation = Affiliation(**affl)
                await affiliation.asave()
                await author.affiliations.aadd(affiliation)
        await author.asave()
        self.datalist['Author'].append(author)
        print('done making author.')
        print(self.datalist)
        return author
    
    async def make_funder(self):
        ...
    async def make_source(self):
        async def add_deal():
            ...
        ...
    async def make_grant(self):
        ...
    
    async def make_organization(self, openalex_id:str ) -> Organization:
        # add openalex org/institute to db if it doesn't exist
        # else return existing org
        return None
    async def make_location(self):
        ...
    async def make_publisher(self):
        ...
    async def make_abstract(self):
        ...
    





