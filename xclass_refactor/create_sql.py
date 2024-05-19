"""
The logic for creating the SQL entries from the MongoDB data will be put here
"""
from rich import print
from xclass_refactor.models import (
    MusModel,
    MongoData,
    Tag,
    Organization,
    Source,
    SourceTopic,
    DealData,
    Author,
    Funder,
    Group,
    Topic,
    Location,
    Abstract,
    Authorship,
    Affiliation,
    Grant,
    Publisher,
    Work,
    RepositoryData,
    OpenAireData,
    CrossrefData,
    DataCiteData
)
from xclass_refactor.constants import (
    get_flat_groups,
    UTRESEARCHGROUPS_FLAT,
    UTRESEARCHGROUPS_HIERARCHY,
    INSTITUTE_NAME,
    INSTITUTE_ALT_NAME,
    FACULTYNAMES,
    TAGLIST,
    LICENSESOA,
    OTHERLICENSES,
    MONGOURL,
    ROR,
    OPENALEX_INSTITUTE_ID,
)

from xclass_refactor.utils import parse_reversed_abstract
import motor.motor_asyncio
import asyncio
from datetime import datetime
import pytz


class CreateSQL:
    def __init__(self):
        self.INSTITUTE_GROUPS: dict[str, str] = get_flat_groups()
        self.motorclient = motor.motor_asyncio.AsyncIOMotorClient(MONGOURL).metadata_unificiation_system
        self.timezone = pytz.utc
    async def add_all(self): 
        '''
        Adds all data from mongodb to the database
        
        Starts with topics, funders, sources, publishers, organizations (and dealdata as part of sources)
        then adds the links between them
        then we add authors and affiliations
        we finish with works, grants, authorships, locations, and abstracts
        '''
        print('deleting all items...')
        async with asyncio.TaskGroup() as tg:
            tg.create_task(Topic.objects.all().adelete())
            tg.create_task(SourceTopic.objects.all().adelete())
            tg.create_task(Funder.objects.all().adelete())
            tg.create_task(Organization.objects.all().adelete())
            tg.create_task(DealData.objects.all().adelete())
        print('done deleting items!')
        print('adding topics')
        time = datetime.now()
        async with asyncio.TaskGroup() as tg:
            
            topics = tg.create_task(self.add_all_itemtype(self.motorclient.topics_openalex, self.add_topic))
        
        time_taken = round((datetime.now() - time).total_seconds(),2)
        print(f'added {len(topics.result())} topics in {time_taken} seconds ({len(topics.result())/time_taken} items/sec | {time_taken/len(topics.result())} sec/item)')

        print('adding topic siblings, funders, sources, and dealdata')
        time = datetime.now()
        async with asyncio.TaskGroup() as tg:
            topics_siblings = tg.create_task(self.add_topic_siblings())
            funders = tg.create_task(self.add_all_itemtype(self.motorclient.funders_openalex, self.add_funder))
            sources = tg.create_task(self.add_all_itemtype(self.motorclient.sources_openalex, self.add_source))
            #publishers = tg.create_task(self.add_all_itemtype(self.motorclient.publishers_openalex, self.add_publisher))
            #organizations = tg.create_task(self.add_all_itemtype(self.motorclient.organizations_openalex, self.add_organization))
        
        print(f'added {len(funders.result())} funders')
        print(f'added {len(sources.result())} sources')
        print(f'added {len(topics_siblings.result())} topic siblings')
        print(f'total items: {len(funders.result()) + len(sources.result()) + len(topics_siblings.result())}')
        print(f'total time: {round((datetime.now() - time).total_seconds(),2)} seconds')
        print(f'avg time per item: {round((datetime.now() - time).total_seconds()/len(funders.result() + sources.result() + topics_siblings.result()),2)} seconds')
        print(f'avg items per second: {round(len(funders.result() + sources.result() + topics_siblings.result())/(datetime.now() - time).total_seconds(),2)}')
        
        print('done for now...')
        if False:
            async with asyncio.TaskGroup() as tg:
                linked = tg.create_task(self.add_org_links())
            async with asyncio.TaskGroup() as tg:
                authors = tg.create_task(self.add_all_itemtype(self.motorclient.authors_openalex, self.add_author))
            async with asyncio.TaskGroup() as tg:
                works = tg.create_task(self.add_all_itemtype(self.motorclient.works_openalex, self.add_work))

    async def add_all_itemtype(self, collection: motor.motor_asyncio.AsyncIOMotorCollection, add_function: callable) -> None:
        """
        Add all items from a mongodb collection to the database
        """
        results = []
        async for item in collection.find():
            results.append(await add_function(item))
        return results


    async def add_topic(self, topic_raw:dict) -> Topic:
        if not await Topic.objects.filter(openalex_id=topic_raw.get('id')).aexists():
            field_type = None
            domain_type = None
            for field in Topic.FieldTypes.values:
                if field.lower() == topic_raw.get('field').get('display_name').lower():
                    field_type = field
                    break
            for domain in Topic.DomainTypes.values:
                if domain.lower() == topic_raw.get('domain').get('display_name').lower():
                    domain_type = domain
                    break
            if not field_type:
                print(f'field type not found for {topic_raw.get("field").get("display_name")}')
            if not domain_type:
                print(f'domain type not found for {topic_raw.get("domain").get("display_name")}')

            topic_dict = {
                'description':topic_raw.get('description'),
                'name':topic_raw.get('display_name'),
                'domain':domain_type,
                'field':field_type,
                'openalex_id':topic_raw.get('id'),
                'works_count':topic_raw.get('works_count'),
                'keywords':topic_raw.get('keywords'),
                'wikipedia':topic_raw.get('ids').get('wikipedia'),
                'subfield':topic_raw.get('subfield').get('display_name'),
                'subfield_id':topic_raw.get('subfield').get('id').strip('https://openalex.org/subfields/'),
            }
            
            topic = Topic(**topic_dict)
            await topic.asave()
            #await topic.raw_data.acreate(data=topic_raw, source_collection='topics_openalex')
            return topic
        else:
            return await Topic.objects.aget(openalex_id=topic_raw.get('id'))

    async def add_topic_siblings(self) -> list[str]:
        full_siblist = []
        async for topic in Topic.objects.all():
            siblings = await self.motorclient.topics_openalex.find_one({'id':topic.openalex_id}, projection={'_id':0, 'id':1, 'siblings':1})
            siblist = []
            full_siblist.extend([sibling.get('id') for sibling in siblings.get('siblings')])
            for sibling in siblings.get('siblings'):
                sib_topic = await Topic.objects.filter(openalex_id=sibling.get('id')).afirst()
                if not sib_topic:
                    continue
                siblist.append(sib_topic)
            if siblist:
                await topic.siblings.aset(siblist)
        return full_siblist

    async def add_funder(self, raw_funder:dict) -> Funder:
        funder_dict = {
            'openalex_id':raw_funder.get('id'),
            'name':raw_funder.get('display_name'),
            'alternate_names':raw_funder.get('alternate_titles'),
            'country_code':raw_funder.get('country_code'),
            'counts_by_year':raw_funder.get('counts_by_year'),
            'openalex_created_date':datetime.strptime(raw_funder.get('created_date'),'%Y-%m-%d'),
            'openalex_updated_date':self.timezone.localize(datetime.strptime(raw_funder.get('updated_date'),'%Y-%m-%dT%H:%M:%S.%f')),
            'grants_count':raw_funder.get('grants_count'),
            'description':raw_funder.get('description'),
            'homepage_url':raw_funder.get('homepage_url'),
            'ror':raw_funder.get('ids').get('ror'),
            'wikidata':raw_funder.get('ids').get('wikidata'),
            'crossref':raw_funder.get('ids').get('crossref'),
            'doi':raw_funder.get('ids').get('doi'),
            'image_thumbnail_url':raw_funder.get('image_thumbnail_url'),
            'image_url':raw_funder.get('image_url'),
            'impact_factor':raw_funder.get('summary_stats').get('2yr_mean_citedness'),
            'h_index':raw_funder.get('summary_stats').get('h_index'),
            'i10_index':raw_funder.get('summary_stats').get('i10_index'),
            'works_count':raw_funder.get('works_count'),
            'cited_by_count':raw_funder.get('cited_by_count'),
        }
        funder = Funder(**funder_dict)
        await funder.asave()
        #await funder.raw_data.acreate(data=raw_funder, source_collection='funders_openalex')

        return funder

    async def add_dealdata(self, source:Source) -> DealData:
        dealdata_raw = await self.motorclient.deals_journalbrowser.find_one({'id':source.openalex_id})
        if dealdata_raw:
            related_source = source
            dealtype_raw = dealdata_raw.get('oa_type')
            match dealtype_raw:
                case '100% APC discount for UT authors':
                    dealtype = DealData.DealType.FULL
                case '20% APC discount for UT authors':
                    dealtype = DealData.DealType.TWENTY
                case '15% APC discount for UT authors':
                    dealtype = DealData.DealType.FIFTEEN
                case '10% APC discount for UT authors':
                    dealtype = DealData.DealType.TEN
                case 'Probably no APC costs':
                    dealtype = DealData.DealType.PROBABLY_NONE
                case 'No APC discount':
                    dealtype = DealData.DealType.NONE
                case 'Full APC costs for UT authors (no discount)':
                    dealtype = DealData.DealType.NONE
                case 'APC costs unknown':
                    dealtype = DealData.DealType.UNKNOWN
                case _:
                    dealtype = DealData.DealType.UNKNOWN

            
            dealdata_update_dict = {
                'dealtype':dealtype,
                'issns':dealdata_raw.get('issns'),
                'keywords':dealdata_raw.get('keywords'),
                'journal_title':dealdata_raw.get('title'),
                'publisher_name':dealdata_raw.get('publisher'),
                'openalex_display_name':dealdata_raw.get('oa_display_name'),
                'openalex_issn_l':dealdata_raw.get('oa_issn_l'),
                'openalex_type':dealdata_raw.get('oa_type'),
                'jb_url':dealdata_raw.get('journal_browser_url'),
                'openalex_issn':dealdata_raw.get('oa_issn'),

            }
            dealdata_unique_dict = {
                'openalex_id':dealdata_raw.get('id'),                
            }
            dealdata, created = await DealData.objects.aget_or_create(**dealdata_unique_dict)
            if created:
                for key, value in dealdata_update_dict.items():
                    if key in dealdata.__dict__:
                        setattr(dealdata, key, value)
                await dealdata.asave()
            if related_source not in [source async for source in dealdata.related_sources.all()]:
                await dealdata.related_sources.aadd(related_source)
            
            #await dealdata.raw_data.acreate(data=dealdata_raw, source_collection='deals_journalbrowser')
            return dealdata
        
    async def add_source(self, source_raw:dict) -> Source:
        raw_type = source_raw.get('type')
        match raw_type:
            case 'journal':
                source_type = Source.SourceType.JOURNAL
            case 'book_series':
                source_type = Source.SourceType.BOOK_SERIES
            case 'repository':
                source_type = Source.SourceType.REPOSITORY
            case 'ebook_platform':
                source_type = Source.SourceType.EBOOK_PLATFORM
            case 'conference':
                source_type = Source.SourceType.CONFERENCE
            case 'metadata':
                source_type = Source.SourceType.METADATA
            case _:
                source_type = Source.SourceType.UNKNOWN
            
        source_dict = {
            'openalex_id':source_raw.get('id'),
            'openalex_created_date':datetime.strptime(source_raw.get('created_date'),'%Y-%m-%d'),
            'openalex_updated_date':self.timezone.localize(datetime.strptime(source_raw.get('updated_date'),'%Y-%m-%dT%H:%M:%S.%f')),
            'is_in_doaj':source_raw.get('is_in_doaj'),
            'is_oa':source_raw.get('is_oa'),
            'country_code':source_raw.get('country_code'),
            'source_type':source_type,
            'title':source_raw.get('display_name'),
            'alternate_titles':source_raw.get('alternate_titles'),
            'abbreviated_title':source_raw.get('abbreviated_title'),
            'homepage_url':source_raw.get('homepage_url'),
            'host_org_name':source_raw.get('host_organization_name'),
            'issn_l':source_raw.get('issn_l'),
            'issn':source_raw.get('issn'),
            'wikidata':source_raw.get('ids').get('wikidata') if source_raw.get('ids') else None,
            'fatcat':source_raw.get('ids').get('fatcat') if source_raw.get('ids') else None,
            'mag':source_raw.get('ids').get('mag') if source_raw.get('ids') else None,
            'cited_by_count':source_raw.get('cited_by_count'),
            'counts_by_year':source_raw.get('counts_by_year'),
            'works_api_url':source_raw.get('works_api_url'),
            'works_count':source_raw.get('works_count'),
            'impact_factor':source_raw.get('summary_stats').get('2yr_mean_citedness'),
            'h_index':source_raw.get('summary_stats').get('h_index'),
            'i10_index':source_raw.get('summary_stats').get('i10_index'),
            'apc_prices':source_raw.get('apc_prices'),
            'apc_usd':source_raw.get('apc_usd'),
        }
        source = Source(**source_dict)
        await source.asave()

        if source_raw.get('topics'):
            for topic_raw in source_raw.get('topics'):
                topic = await Topic.objects.filter(openalex_id=topic_raw.get('id')).afirst()
                if not topic:
                    continue
                source_topic = SourceTopic(source=source, topic=topic, count=topic_raw.get('count'))
                await source_topic.asave()

        await self.add_dealdata(source)
        #await source.raw_data.acreate(data=source_raw, source_collection='sources_openalex')
        
        return source

    async def add_publisher(self, publisher_raw:dict) -> Publisher:
        publisher_dict = {}
        publisher = Publisher(**publisher_dict)
        await publisher.asave()
        #await publisher.raw_data.acreate(data=publisher_raw, source_collection='publishers_openalex')
        
        return publisher

    async def add_organization(self, organization_raw:dict) -> Organization:
        organization_dict = {}
        organization = Organization(**organization_dict)
        await organization.asave()
        #await organization.raw_data.acreate(data=organization_raw, source_collection='institutions_openalex')
        
        return organization
    
    async def add_org_links(self) -> list[MusModel]:
        # for Publisher, Organization, Funder, Source: add links between them (most many-to-many fields)
        changed_itemlist = []
        for publisher in Publisher.objects.all():
            ...
        for organization in Organization.objects.all():
            ...
        for funder in Funder.objects.all():
            ...
        for source in Source.objects.all():
            ...
        return changed_itemlist
    
    async def add_author(self, author_raw:dict) -> Author:
        # calls add_affiliation during author creation
        author_dict = {}
        author = Author(**author_dict)
        await author.asave()
        #await author.raw_data.acreate(data=author_raw, source_collection='authors_openalex')
        
        for affiliation in author_raw.get('affiliations'):
            await self.add_affiliation(affiliation, author)
        return author
        

    async def add_affiliation(self, affiliation_raw:dict, author:Author) -> Affiliation:
        async def add_group(group) -> Group:
            pass
        affiliation_dict = {}
        affiliation = Affiliation(**affiliation_dict)
        await affiliation.asave()
        #await affiliation.raw_data.acreate(data=affiliation_raw, source_collection='authors_openalex')\
        
        return affiliation
        


    async def add_work(self, work_raw:dict) -> Work:
        # calls add_location, add_abstract, add_authorship, add_grants during work creation
        
        
        work_dict = {}
        
        # add raw data from other data sources
        datacite_raw = await self.motorclient.works_datacite.find_one({'id':work_raw.get('id')})
        if datacite_raw:
            datacite = DataCiteData(data=datacite_raw, source_collection='works_datacite')
            await datacite.asave()
            work_dict['datacite_data'] = datacite
        openaire_raw = await self.motorclient.works_openaire.find_one({'id':work_raw.get('id')})
        if openaire_raw:
            openaire = OpenAireData(data=openaire_raw, source_collection='works_openaire')
            await openaire.asave()
            work_dict['openaire_data'] = openaire
        crossref_raw = await self.motorclient.works_crossref.find_one({'id':work_raw.get('id')})
        if crossref_raw:
            crossref = CrossrefData(data=crossref_raw, source_collection='works_crossref')
            await crossref.asave()
            work_dict['crossref_data'] = crossref   
        repository_raw = await self.motorclient.works_repository.find_one({'id':work_raw.get('id')})
        if repository_raw:
            repository = RepositoryData(data=repository_raw, source_collection='works_repository')
            await repository.asave()
            work_dict['repo_data'] = repository

        work = Work(**work_dict)
        await work.asave()

        if work_raw.get('abstract'):
            work = await self.add_abstract(work_raw.get('abstract'), work)
        for authorship in work_raw.get('authorships'):
            author = await Author.objects.aget(openalex_id=authorship.get('author').get('id'))
            work = await self.add_authorship(authorship, work, author)
        best_oa_location = work_raw.get('best_oa_location')
        primary_location = work_raw.get('primary_location')
        for location in work_raw.get('locations'):
            source = await Source.objects.aget(openalex_id=location.get('source').get('id'))
            work = await self.add_location(location, work, source, best_oa_location, primary_location)
        for grant in work_raw.get('grants'):
            work = await self.add_grant(grant, work)
        #await work.raw_data.acreate(data=work_raw, source_collection='works_openalex')
        
        return work

    async def add_location(self, location_raw:dict, work:Work, source:Source, best_oa_location:dict, primary_location:dict) -> Work:
        location_dict = {}
        location = Location(**location_dict)
        await location.asave()
        await work.locations.aadd(location)
        return work
        

    async def add_abstract(self, abstract_raw:dict, work:Work) -> Work:
        abstract_text = await parse_reversed_abstract(abstract_raw)
        abstract = Abstract(text=abstract_text)
        await abstract.asave()
        work.abstract = abstract
        await work.asave()
        return work

    async def add_authorship(self, authorship_raw:dict, work:Work, author:Author) -> Work:

        return work
        

    async def add_grant(self, grant_raw:dict, work:Work) -> Work:
        return work

    # these are not used standalone but as part of all other models
    async def add_tag(self, tag_raw:dict, model:MusModel) -> Tag:
        pass

    async def add_mongodata(self, mongodata:dict, source_collection:str) -> MongoData:
        pass
