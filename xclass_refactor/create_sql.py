"""
The logic for creating the SQL entries from the MongoDB data will be put here
"""
from rich import print
from xclass_refactor.models import (
    MusModel,
    MongoData,
    Tag,
    Organization,
    OrganizationTopic,
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
from nameparser import HumanName
from collections import defaultdict

class CreateSQL:
    def __init__(self, detailed_topics=False):
        self.INSTITUTE_GROUPS: dict[str, str] = get_flat_groups()
        self.motorclient : motor.motor_asyncio.AsyncIOMotorClient = motor.motor_asyncio.AsyncIOMotorClient(MONGOURL).metadata_unificiation_system
        self.timezone = pytz.utc
        self.topics_dict: dict[str:Topic] = None
        self.all_topics: list[Topic] = []
        self.missing_orgs: list[str] = []
        self.missing_funders: list[str] = []
        self.missing_authors: list[str] = []
        self.missing_sources: list[str] = []
        self.detailed_topics = detailed_topics

    async def load_topics(self):
        self.all_topics : list[Topic] = [topic async for topic in Topic.objects.all()]
        self.topics_dict : dict[str:Topic] = {topic.openalex_id:topic for topic in self.all_topics}

    async def add_all(self):
        '''
        Adds all data from mongodb to the database

        Starts with topics, funders, sources, publishers, organizations (and dealdata as part of sources)
        then adds the links between them
        then we add authors and affiliations
        we finish with works, grants, authorships, locations, and abstracts
        '''
        print('adding topics')
        time = datetime.now()
        async with asyncio.TaskGroup() as tg:
            topics = tg.create_task(self.add_all_itemtype(self.motorclient.topics_openalex, self.add_topic, Topic))

        time_taken = round((datetime.now() - time).total_seconds(),2)
        print(f'added {len(topics.result())} topics in {time_taken} seconds ({len(topics.result())/time_taken} items/sec) ')
        await self.load_topics()
        print('adding funders, sources, dealdata, publishers, organizations')
        time = datetime.now()
        async with asyncio.TaskGroup() as tg:
            if self.detailed_topics:
                topics_siblings = tg.create_task(self.add_topic_siblings())
            funders = tg.create_task(self.add_all_itemtype(self.motorclient.funders_openalex, self.add_funder, Funder))
            sources = tg.create_task(self.add_all_itemtype(self.motorclient.sources_openalex, self.add_source, Source))
            publishers = tg.create_task(self.add_all_itemtype(self.motorclient.publishers_openalex, self.add_publisher, Publisher))
            organizations = tg.create_task(self.add_all_itemtype(self.motorclient.institutions_openalex, self.add_organization, Organization))

        time_taken = round((datetime.now() - time).total_seconds(),2)
        if self.detailed_topics:
            print(f'added {len(topics_siblings.result())} topic siblings in {time_taken} seconds')
            await self.load_topics()
        print(f'added {len(funders.result())} funders')
        print(f'added {len(sources.result())} sources')
        print(f'added {len(publishers.result())} publishers')
        print(f'added {len(organizations.result())} organizations')
        print(f'total items: {len(  funders.result()) + len(sources.result()) + len(publishers.result()) + len(organizations.result())}')
        print(f'total time: {round((datetime.now() - time).total_seconds(),2)} seconds')
        print(f'avg items per second: {round(len(funders.result() + sources.result() + publishers.result() + organizations.result())/(datetime.now() - time).total_seconds(),2)}')



        print('adding authors')
        async with asyncio.TaskGroup() as tg:
            #linked = tg.create_task(self.add_org_links())
            authors = tg.create_task(self.add_all_authors())

        #print(f'added m2m relations to {len(linked.result())} items (organizations, funders, sources, publishers)')
        print(f'added {len(authors.result())} authors')
        if len(self.missing_orgs) > 0:
            print(f'retrieved {len(self.missing_orgs)} organizations that were not found')
            from xclass_refactor.openalex_import import OpenAlexAPI
            openalexresult = await OpenAlexAPI(openalex_requests={'institutions_openalex':self.missing_orgs}).run()
            print('done adding missing organizations to mongodb, now adding to sql db')
            more_orgs = await self.add_all_itemtype(self.motorclient.institutions_openalex, self.add_organization, Organization)
            print(f'added {len(more_orgs)} orgs to sql db')

        print('adding works')
        async with asyncio.TaskGroup() as tg:
            works = tg.create_task(self.add_all_itemtype(self.motorclient.works_openalex, self.add_work, Work))
        print(f' Done with CreateSQL.run(). Methods not implemented yet: add_org_links')
        print(f' currently also mainly processing data from openalex. Missing data from openaire, crossref, orcid, datacite, and repository')

    async def add_all_itemtype(self, collection: motor.motor_asyncio.AsyncIOMotorCollection, add_function: callable, model: MusModel)-> list:
        """
        Add all items from a mongodb collection to the database
        """
        results = []
        models_in_db = model.objects.all().values_list('openalex_id', flat=True)
        models_in_db = {model async for model in models_in_db}
        async for item in collection.find():
                if item.get('id') not in models_in_db:
                    results.append(await add_function(item))
        return results

    async def add_all_authors(self) -> list:
        results = []
        # get all openalex authors
        # get all pure/institute authors
        # check matches, combine dicts if found
        # send data to add_author
        # also include topics

        # get all authors from collection authors_pure that have a non-null 'id' field
        pure_matches = self.motorclient.authors_pure.find({'id':{'$exists':True}})
        pure_match_dict = {match['id']:match async for match in pure_matches}
        # get all authors from collection employees
        employee_data = self.motorclient.employees_peoplepage.find({})
        employee_match_dict = {match['id']:match async for match in employee_data}
        authoridlist = {author.openalex_id:'' async for author in Author.objects.all()}
        async for openalex_author in self.motorclient.authors_openalex.find({}):
            if openalex_author['id'] in authoridlist:
                continue
            final_dict = openalex_author
            if openalex_author['id'] in pure_match_dict:
                pure_match = pure_match_dict[openalex_author['id']]
                final_dict = pure_match | final_dict
            if openalex_author['id'] in employee_match_dict:
                employee_match = employee_match_dict[openalex_author['id']]
                final_dict = employee_match | final_dict

            results.append(await self.add_author(final_dict))

        return results
    async def add_topic(self, topic_raw:dict) -> Topic:
        if await Topic.objects.filter(openalex_id=topic_raw.get('id')).aexists():
            return await Topic.objects.aget(openalex_id=topic_raw.get('id'))
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

    async def add_topic_siblings(self) -> list[str]:
        full_siblist = []
        for topic in self.all_topics:
            siblings = await self.motorclient.topics_openalex.find_one({'id':topic.openalex_id}, projection={'_id':0, 'id':1, 'siblings':1})
            siblist = []
            full_siblist.extend([sibling.get('id') for sibling in siblings.get('siblings')])
            for sibling in siblings.get('siblings'):
                if sibling.get('id') in self.topics_dict:
                    siblist.append(self.topics_dict[sibling.get('id')])
            if siblist:
                await topic.siblings.aset(siblist)
        return full_siblist

    async def add_funder(self, raw_funder:dict) -> Funder:
        if await Funder.objects.filter(openalex_id=raw_funder.get('id')).aexists():
            return await Funder.objects.aget(openalex_id=raw_funder.get('id'))
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
            if await DealData.objects.filter(openalex_id=dealdata_raw.get('id')).aexists():
                return await DealData.objects.aget(openalex_id=dealdata_raw.get('id'))

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
        if await Source.objects.filter(openalex_id=source_raw.get('id')).aexists():
            return await Source.objects.aget(openalex_id=source_raw.get('id'))

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

        if self.detailed_topics:
            if source_raw.get('topics'):
                for topic_raw in source_raw.get('topics'):
                    topic = self.topics_dict.get(topic_raw.get('id'))
                    if not topic:
                        continue
                    source_topic = SourceTopic(source=source, topic=topic, count=topic_raw.get('count'))
                    await source_topic.asave()

        await self.add_dealdata(source)
        #await source.raw_data.acreate(data=source_raw, source_collection='sources_openalex')

        return source

    async def add_publisher(self, publisher_raw:dict) -> Publisher:
        if await Publisher.objects.filter(openalex_id=publisher_raw.get('id')).aexists():
            return await Publisher.objects.aget(openalex_id=publisher_raw.get('id'))
        publisher_dict = {
            'openalex_id':publisher_raw.get('id'),
            'openalex_created_date':datetime.strptime(publisher_raw.get('created_date'),'%Y-%m-%d'),
            'openalex_updated_date':self.timezone.localize(datetime.strptime(publisher_raw.get('updated_date'),'%Y-%m-%dT%H:%M:%S.%f')),
            'name':publisher_raw.get('display_name'),
            'alternate_names':publisher_raw.get('alternate_titles'),
            'country_code':publisher_raw.get('country_code'),
            'counts_by_year':publisher_raw.get('counts_by_year'),
            'hierarchy_level':publisher_raw.get('hierarchy_level'),
            'ror':publisher_raw.get('ids').get('ror'),
            'wikidata':publisher_raw.get('ids').get('wikidata'),
            'image_url':publisher_raw.get('image_url'),
            'image_thumbnail_url':publisher_raw.get('image_thumbnail_url'),
            'sources_api_url':publisher_raw.get('sources_api_url'),
            'impact_factor':publisher_raw.get('2yr_mean_citedness'),
            'h_index':publisher_raw.get('h_index'),
            'i10_index':publisher_raw.get('i10_index'),
            'works_count':publisher_raw.get('works_count'),
        }

        publisher = Publisher(**publisher_dict)
        await publisher.asave()
        #await publisher.raw_data.acreate(data=publisher_raw, source_collection='publishers_openalex')
        return publisher

    async def add_organization(self, organization_raw:dict) -> Organization:
        if await Organization.objects.filter(openalex_id=organization_raw.get('id')).aexists():
            return await Organization.objects.aget(openalex_id=organization_raw.get('id'))
        organization_dict = {
            'name':organization_raw.get('display_name'),
            'name_acronyms':organization_raw.get('display_name_acronyms'),
            'name_alternatives':organization_raw.get('display_name_alternatives'),
            'ror':organization_raw.get('ids').get('ror'),
            'openalex_id':organization_raw.get('id'),
            'wikipedia':organization_raw.get('ids').get('wikipedia'),
            'wikidata':organization_raw.get('ids').get('wikidata'),
            'openalex_created_date':datetime.strptime(organization_raw.get('created_date'),'%Y-%m-%d'),
            'openalex_updated_date':self.timezone.localize(datetime.strptime(organization_raw.get('updated_date'),'%Y-%m-%dT%H:%M:%S.%f')),
            'country_code':organization_raw.get('country_code'),
            'works_count':organization_raw.get('works_count'),
            'cited_by_count':organization_raw.get('cited_by_count'),
            'impact_factor':organization_raw.get('2yr_mean_citedness'),
            'h_index':organization_raw.get('h_index'),
            'i10_index':organization_raw.get('i10_index'),
            'image_thumbnail_url':organization_raw.get('image_thumbnail_url'),
            'image_url':organization_raw.get('image_url'),
        }
        organization = Organization(**organization_dict)
        await organization.asave()

        if self.detailed_topics:
            if organization_raw.get('topics'):
                for topic_raw in organization_raw.get('topics'):
                    topic = self.topics_dict.get(topic_raw.get('id'))
                    if not topic:
                        continue
                    organization_topic = OrganizationTopic(organization=organization, topic=topic, count=topic_raw.get('count'))
                    await organization_topic.asave()

        if organization_raw.get('roles'):
            for role in organization_raw.get('roles'):
                if role.get('role'):
                    tag = await Tag.objects.acreate(tag_type=Tag.TagTypes.ORG_TYPE, notes=role.get('role'), content_object=organization)

        #await organization.raw_data.acreate(data=organization_raw, source_collection='institutions_openalex')

        return organization

    async def add_org_links(self) -> list[MusModel]:
        # for Publisher, Organization, Funder, Source: add links between them (most many-to-many fields)
        changed_itemlist = []
        print('m2m relations for orgs not implemented at the moment')
        for publisher in Publisher.objects.all():
            ...
            #lineage = models.ManyToManyField('Publisher', related_name="publ_children")
            #as_funder = models.ManyToManyField('Funder', related_name="as_publisher")
            #as_institution = models.ManyToManyField('Organization', related_name="as_publisher")

        for organization in Organization.objects.all():
            ...
            #repositories = models.ManyToManyField('Source', related_name="repositories")
            #lineage = models.ManyToManyField('Organization', related_name="org_children")

        for funder in Funder.objects.all():
            #as_other_funders = models.ManyToManyField('Funder', related_name="other_funders_entries")
            ...
        for source in Source.objects.all():
            ...
            #lineage = models.ManyToManyField('Publisher', related_name="children")

        return changed_itemlist

    async def add_author(self, author_raw:dict) -> Author:
        def get_names() -> tuple[HumanName, list[str]]:
            # from openalex
            namelist = author_raw.get('display_name_alternatives') if author_raw.get('display_name_alternatives') else []
            namelist.append(author_raw.get('display_name'))

            # from pure/institute repo
            if author_raw.get('author_name'):
                namelist.append(author_raw.get('author_name'))
                namelist.append(author_raw.get('author_default_publishing_name'))
                namelist.append(author_raw.get('author_known_as_name'))

            # from employee page
            if author_raw.get('foundname'):
                namelist.append(author_raw.get('foundname'))

            # make HumanName from each included name
            # make sets for each name part
            tmp_list = [HumanName(name) for name in namelist if name]
            namedict = defaultdict(set)
            for name in tmp_list:
                namedict['prefixes'].add(name.title)
                namedict['first'].add(name.first)
                namedict['middle'].add(name.middle)
                namedict['last'].add(name.last)
                namedict['suffixes'].add(name.suffix)

            # TODO: think of heuristic for the standardized name; for now select the longest value for each part (bad approach)
            final_name = " ".join([max(namedict[key], key=len) for key in namedict])
            standardized_name = HumanName(final_name)
            return standardized_name, namelist


        # step 1: process all names for this author and return a name in standardized form + list of all found related names
        standardized_name, namelist = get_names()

        # step 2: build the dicts for all info to create the author sql model
        # 1st dict: PIDs + name
        author_dict = {
            'standardized_name':standardized_name.full_name,
            'first_names':standardized_name.first,
            'last_name':standardized_name.last,
            'middle_names':standardized_name.middle,
            'initials':standardized_name.initials(),
            'prefixes':standardized_name.title,
            'suffixes':standardized_name.suffix,
            # also possible to add nickname; not included at the moment
            'alternative_names':namelist,
            'orcid':author_raw.get('ids').get('orcid') if author_raw.get('ids') else author_raw.get('author_orcid'),
            'scopus':author_raw.get('ids').get('scopus') if author_raw.get('ids') else author_raw.get('author_scopus_id'),
            'isni':author_raw.get('ids').get('isni') if author_raw.get('ids') else author_raw.get('author_isni'),
        }
        # 2nd dict: openalex data
        openalex_dict = {
            'name':author_raw.get('display_name'),
            'openalex_id':author_raw.get('id'),
            'openalex_created_date':datetime.strptime(author_raw.get('created_date'),'%Y-%m-%d'),
            'openalex_updated_date':self.timezone.localize(datetime.strptime(author_raw.get('updated_date'),'%Y-%m-%dT%H:%M:%S.%f')),
            'works_api_url':author_raw.get('works_api_url'),
            'works_count':author_raw.get('works_count'),
            'cited_by_count':author_raw.get('cited_by_count'),
            'counts_by_year':author_raw.get('counts_by_year'),
            'impact_factor':author_raw.get('2yr_mean_citedness'),
            'h_index':author_raw.get('h_index'),
            'i10_index':author_raw.get('i10_index'),
        }
        # 3rd dict: pure/institute repo data
        pure_dict = {
            'pure_uuid':author_raw.get('author_uuid'),
            'pure_id':author_raw.get('author_pureid'),
            'pure_last_modified':author_raw.get('last_modified')[0] if isinstance(author_raw.get('last_modified'), list) else author_raw.get('last_modified'),
            'author_links':author_raw.get('author_links'),
        }
        # 4th dict: institute people page data
        people_page_dict = {
            'avatar_url':author_raw.get('avatar_url'),
            'profile_url':author_raw.get('profile_url'),
            'research_url':author_raw.get('research_url'),
            'email':author_raw.get('email'),
        }
        # 5th dict: name-match info
        match_info_dict ={
            'searched_name':author_raw.get('searchname'),
            'found_name':author_raw.get('foundname'),
            'match_similarity':author_raw.get('similarity'),
        }

        # step 3: combine the dicts and store as Author
        author = Author(**author_dict, **openalex_dict, **pure_dict, **people_page_dict, **match_info_dict)
        await author.asave()
        #await author.raw_data.acreate(data=author_raw, source_collection='authors_openalex')

        # step 4: add many-to-many relations: affiliations and topics

        for affiliation in author_raw.get('affiliations'):
            await self.add_affiliation(affiliation, author, author_raw)
        if author_raw.get('topics'):
            topiclist = []
            for topic_raw in author_raw.get('topics'):
                topic = self.topics_dict.get(topic_raw.get('id'))
                if not topic:
                    continue
                topiclist.append(topic)
            await author.topics.aset(topiclist)
        # done!
        return author



    async def add_affiliation(self, affiliation_raw:dict, author:Author, author_raw:dict) -> Affiliation:
        
        # openalex data
        organization = await Organization.objects.filter(openalex_id=affiliation_raw.get('institution').get('id')).afirst()
        if not organization:
            self.missing_orgs.append(affiliation_raw.get("institution").get('id'))
            return None
        affiliation_dict = {
            'years':affiliation_raw.get('years'),
            'author': author,
            'organization': organization,
        }

        # institutional data

        groups = []
        if author_raw.get('grouplist') and len(author_raw.get('grouplist')) > 0 and organization.openalex_id == OPENALEX_INSTITUTE_ID:
            for item in author_raw.get('grouplist'):
                try:
                    if not item.get('section'):
                        continue
                    if item.get('department') in FACULTYNAMES:
                        faculty = item.get('department')
                    else:
                        faculty = Group.Faculties.OTHER
                    group, created = await Group.objects.aget_or_create(name=item.get('section'), faculty=faculty)
                    groups.append(group)    
                except Exception as e:
                    print(f'error while adding groups to affiliation: {e}')
                    continue
            if author_raw.get('affiliation'):
                if len(author_raw['affiliation']) == 1:
                    affiliation_dict['position'] = author_raw.get('affiliation')[0]
                elif 'professor' in author_raw['affiliation']:
                    affiliation_dict['position'] = 'professor'
                else:
                    affiliation_dict['position'] = author_raw.get('affiliation')[0]
                
        affiliation = Affiliation(**affiliation_dict)

        await affiliation.asave()
        await affiliation.groups.aset(groups)

        #await affiliation.raw_data.acreate(data=affiliation_raw, source_collection='authors_openalex')\

        return affiliation



    async def add_work(self, work_raw:dict) -> Work:
        # calls add_location, add_abstract, add_authorship, add_grants during work creation
        if await Work.objects.filter(openalex_id=work_raw.get('id')).aexists():
            return await Work.objects.aget(openalex_id=work_raw.get('id'))
        work_dict = {
            
            'openalex_id':work_raw.get('id'),
            'openalex_created_date':datetime.strptime(work_raw.get('created_date'),'%Y-%m-%d'),
            'openalex_updated_date':self.timezone.localize(datetime.strptime(work_raw.get('updated_date'),'%Y-%m-%dT%H:%M:%S.%f')),
            'ngrams_url':work_raw.get('ngrams_url'),
            'cited_by_api_url':work_raw.get('cited_by_api_url'),
            'cited_by_count':work_raw.get('cited_by_count'),
            'cited_by_percentile_year':work_raw.get('cited_by_percentile_year'),
            'referenced_works_count':work_raw.get('referenced_works_count'),
            'doi':work_raw.get('doi'),
            'title':work_raw.get('title'),
            'publication_year':work_raw.get('publication_year'),
            'publication_date':work_raw.get('publication_date'),
            'pmid':work_raw.get('ids').get('pmid') if work_raw.get('ids') else None,
            'pmcid':work_raw.get('ids').get('pmcid') if work_raw.get('ids') else None,
            'isbn':work_raw.get('ids').get('isbn') if work_raw.get('ids') else None,
            'mag':work_raw.get('ids').get('mag') if work_raw.get('ids') else None,
            'language':work_raw.get('language'),
            'mesh_terms':work_raw.get('mesh'),
            'type_crossref':work_raw.get('type_crossref'),
            'volume':work_raw.get('biblio').get('volume') if work_raw.get('biblio') else None,
            'issue':work_raw.get('biblio').get('issue') if work_raw.get('biblio') else None,
            'first_page':work_raw.get('biblio').get('first_page') if work_raw.get('biblio') else None,
            'last_page':work_raw.get('biblio').get('last_page') if work_raw.get('biblio') else None,
            'pages': None,
            'article_number':None,
            'locations_count':work_raw.get('locations_count'),
            'is_oa':work_raw.get('open_access').get('is_oa') if work_raw.get('open_access') else None,
            'oa_status':work_raw.get('open_access').get('oa_status') if work_raw.get('open_access') else None,
            'oa_url':work_raw.get('open_access').get('oa_url') if work_raw.get('open_access') else None,
            'is_also_green':work_raw.get('open_access').get('any_repository_has_fulltext') if work_raw.get('open_access') else None,
            'itemtype':work_raw.get('type'),
            'apc_listed':work_raw.get('apc_list').get('value_usd') if work_raw.get('apc_list') else None,
            'apc_paid':work_raw.get('apc_paid').get('value_usd') if work_raw.get('apc_paid') else None,
            'has_fulltext':work_raw.get('has_fulltext'),
            'is_paratext':work_raw.get('is_paratext'),
            'is_retracted':work_raw.get('is_retracted'),
            'indexed_in':work_raw.get('indexed_in'),
            'keywords':work_raw.get('keywords'),
            'sdgs':work_raw.get('sustainable_development_goals'),
            'versions':work_raw.get('versions'),
        }

        # add raw data from other data sources
        datacite_raw = await self.motorclient.items_datacite.find_one({'id':work_raw.get('id')}, projection={'_id':0})
        if datacite_raw:
            datacite = DataCiteData(data=datacite_raw)
            await datacite.asave()
            work_dict['datacite_data'] = datacite
        openaire_raw = await self.motorclient.items_openaire.find_one({'id':work_raw.get('id')}, projection={'_id':0})
        if openaire_raw:
            openaire = OpenAireData(data=openaire_raw)
            await openaire.asave()
            work_dict['openaire_data'] = openaire
        crossref_raw = await self.motorclient.items_crossref.find_one({'id':work_raw.get('id')}, projection={'_id':0})
        if crossref_raw:
            crossref = CrossrefData(data=crossref_raw)
            await crossref.asave()
            work_dict['crossref_data'] = crossref
        repository_raw = await self.motorclient['items_pure_oaipmh'].find_one({'id':work_raw.get('id')}, projection={'_id':0})
        if repository_raw:
            repository = RepositoryData(data=repository_raw)
            await repository.asave()
            work_dict['repo_data'] = repository
            work_dict['found_in_institute_repo'] = True


        work = Work(**work_dict)
        try:
            await work.asave()
        except Exception as e:
            print(f'error while saving work {work.openalex_id}: {e}')
            return None

        # authorships are directly made as Authorship objects, including the work as fk, no need to add them to work later
        
        

        if work_raw.get('abstract'):
            abstract = await self.add_abstract(work_raw.get('abstract'))
            work.abstract = abstract
            await work.asave()

        if work_raw.get('topics'):
            topiclist = []
            for topic_raw in work_raw.get('topics'):
                topic = self.topics_dict.get(topic_raw.get('id'))
                if not topic:
                    continue
                topiclist.append(topic)
            await work.topics.aset(topiclist)
        if work_raw.get('primary_topic'):
            topic = self.topics_dict.get(work_raw.get('primary_topic').get('id'))
            if topic:
                work.primary_topic = topic
                await work.asave()
    
        await self.add_authorships(work_raw.get('authorships'), work)

        if work_raw.get('grants'):
            await self.add_grants(work_raw.get('grants'), work)
        if work_raw.get('locations'):
            best_oa_location = work_raw.get('best_oa_location')
            primary_location = work_raw.get('primary_location')
            work = await self.add_locations(work_raw.get('locations'), work, best_oa_location, primary_location)


        #await work.raw_data.acreate(data=work_raw, source_collection='works_openalex')

        return work

    async def add_locations(self, locations_raw:dict, work:Work, best_oa_location:dict|None, primary_location:dict|None) -> Work:
        async def make_location(location_raw:dict):
            try:
                source = await Source.objects.aget(openalex_id=location_raw.get('source').get('id'))
                source_type = source.source_type
            except Exception as e:
                source = None
                source_type = None

            if not source:
                source = None
                source_type = Source.SourceType.UNKNOWN

            location_dict = {
                'source':source,
                'source_type':source_type,
                'is_oa':location_raw.get('is_oa') if isinstance(location_raw.get('is_oa'), bool) else False,
                'landing_page_url':location_raw.get('landing_page_url'),
                'pdf_url':location_raw.get('pdf_url'),
                'license':location_raw.get('license'),
                'license_id':location_raw.get('license_id'),
                'version':location_raw.get('version'),
                'is_accepted':location_raw.get('is_accepted') if isinstance(location_raw.get('is_accepted'), bool) else False,
                'is_published':location_raw.get('is_published') if isinstance(location_raw.get('is_published'), bool) else False,
            }

            if best_oa_location:
                if best_oa_location.get('landing_page_url') == location_raw.get('landing_page_url'):
                    location_dict['is_best_oa'] = True
            if primary_location:
                if primary_location.get('landing_page_url') == location_raw.get('landing_page_url'):
                    location_dict['is_primary'] = True

            location = Location(**location_dict)
            await location.asave()
            return location
        
        location_tasks : list[asyncio.Task] = []
        async with asyncio.TaskGroup() as tg:
            for location in locations_raw:
                location_tasks.append(tg.create_task(make_location(location)))
        
        locations : list[Location] = []
        for task in location_tasks:
            locations.append(task.result())
        if locations:
            await work.locations.aset(locations)
        return work


    async def add_abstract(self, abstract_raw:dict) -> Abstract:
        abstract_text = await parse_reversed_abstract(abstract_raw)
        abstract = Abstract(text=abstract_text)
        await abstract.asave()
        return abstract

    async def add_authorships(self, authorships_raw:list[dict], work:Work) -> list[Authorship]:
        authorships = []
        for authorship_raw in authorships_raw:
            try:    
                author = await Author.objects.filter(openalex_id=authorship_raw.get('author').get('id')).afirst()
            except Exception as e:
                print(f'{e} while retrieving author {authorship_raw.get("author")} for authorship {authorship_raw.get("id")}')
                continue
            if not author:
                self.missing_authors.append(authorship_raw.get('author').get('id'))
                continue

            authorship_dict = {
                'author':author,
                'work':work,
                'is_corresponding':authorship_raw.get('is_corresponding'),
            }
            match authorship_raw.get('author_position'):
                case 'first':
                    authorship_dict['position'] = Authorship.PositionTypes.FIRST
                case 'middle':
                    authorship_dict['position'] = Authorship.PositionTypes.MIDDLE
                case 'last':
                    authorship_dict['position'] = Authorship.PositionTypes.LAST
                case _:
                    authorship_dict['position'] = Authorship.PositionTypes.UNKNOWN
            authorship = Authorship(**authorship_dict)
            await authorship.asave()

            if authorship_raw.get('institutions'):
                for inst in authorship_raw.get('institutions'):
                    institution = await Organization.objects.filter(openalex_id=inst.get('id')).afirst()
                    if institution:
                        await authorship.affiliations.aadd(institution)

            authorships.append(authorship)
        return authorships


    async def add_grants(self, grants_raw:list[dict], work:Work) -> Work:
        grants = []
        # work is a fk to the work object, so we can add grants to it directly
        
        for grant_raw in grants_raw:
            funder = await Funder.objects.filter(openalex_id=grant_raw.get('funder')).afirst()
            if not funder:
                self.missing_funders.append(grant_raw.get('funder'))
                continue
            grant_dict = {
                'funder':funder,
                'award_id':grant_raw.get('award_id'),
                'funder_name':grant_raw.get('funder_name'),
                'work':work,
            }
            grant = Grant(**grant_dict)
            await grant.asave()
            grants.append(grant)

        return grants

    # these are not used standalone but as part of all other models
    async def add_tag(self, tag_raw:dict, model:MusModel) -> Tag:
        pass

    async def add_mongodata(self, mongodata:dict, source_collection:str) -> MongoData:
        pass
