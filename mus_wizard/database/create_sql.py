"""
The logic for creating the SQL entries from the MongoDB data will be put here
"""
from collections import defaultdict
from datetime import datetime

import asyncio
import motor.motor_asyncio
import pytz
from nameparser import HumanName
from rich import print

from mus_wizard.constants import (FACULTYNAMES, MONGOURL, OPENALEX_INSTITUTE_ID, get_flat_groups)
from mus_wizard.harvester.base_classes import GenericSQLImport
from mus_wizard.models import (Abstract, Affiliation, Author, Authorship, CrossrefData, DataCiteData, DealData, Funder,
                               Grant, Group, Location, MongoData, MusModel, OpenAireData, Organization,
                               OrganizationTopic, Publisher, RepositoryData, Source, SourceTopic, Tag, Topic, Work)
from mus_wizard.utils import parse_reversed_abstract

timezone = pytz.utc
motorclient: motor.motor_asyncio.AsyncIOMotorClient = motor.motor_asyncio.AsyncIOMotorClient(MONGOURL).metadata_unification_system

# TODO
# do something with missing items
# implement links to cerif data and others

class CreateSQL:
    def __init__(self, detailed_topics=False):
        self.INSTITUTE_GROUPS: dict[str, str] = get_flat_groups()
        self.motorclient: motor.motor_asyncio.AsyncIOMotorClient = motor.motor_asyncio.AsyncIOMotorClient(
            MONGOURL).metadata_unification_system
        self.topics_dict: dict[str:Topic] = None
        self.all_topics: list[Topic] = []
        self.missing_orgs: list[str] = []
        self.missing_funders: list[str] = []
        self.missing_authors: list[str] = []
        self.missing_sources: list[str] = []
        self.detailed_topics = detailed_topics

    async def load_topics(self):
        self.all_topics: list[Topic] = [topic async for topic in Topic.objects.all()]
        self.topics_dict: dict[str:Topic] = {topic.openalex_id: topic for topic in self.all_topics}

    async def add_all(self):
        '''
        Adds all data from mongodb to the database

        Starts with topics, funders, sources, publishers, organizations (and dealdata as part of sources)
        then adds the links between them
        then we add authors and affiliations
        we finish with works, grants, authorships, locations, and abstracts
        '''

        print('adding topics')
        topics = self.ImportTopic(self.motorclient.topics_openalex)
        topic_results = await topics.import_all()
        print(topic_results)
        await self.load_topics()
        topic_siblings_results = await topics.add_siblings(self.all_topics, self.topics_dict)
        print(topic_siblings_results)
        print('adding groups')
        groups = self.ImportGroup(self.motorclient.openaire_cris_orgs)
        group_results = await groups.import_all()
        print(group_results)
        group_part_of_results = await groups.add_part_of()
        print(group_part_of_results)
        print('adding funders')
        funders = self.ImportFunder(self.motorclient.funders_openalex)
        funder_results = await funders.import_all()
        print(funder_results)
        print('adding sources')
        sources = self.ImportSource(self.motorclient.sources_openalex, detailed_topics=False, topics_dict=self.topics_dict)
        source_results = await sources.import_all()
        print(source_results)
        print('adding publishers')
        publishers = self.ImportPublisher(self.motorclient.publishers_openalex)
        publisher_results = await publishers.import_all()
        print(publisher_results)
        print('adding organizations')
        organizations = self.ImportOrganization(self.motorclient.institutions_openalex, detailed_topics=False, topics_dict=self.topics_dict)
        organization_results = await organizations.import_all()
        print(organization_results)
        print('adding authors')
        more_author_data = {
            'repo_data':{
                'collection': self.motorclient.openaire_cris_persons,
                'unique_id_field': 'id',
                'unique_id_value': 'id',
                'projection': {}
            },
            'pure_data':{
                'collection': self.motorclient.authors_pure,
                'unique_id_field': 'id',
                'unique_id_value': 'id',
                'projection': {}
            }
        }
        authors = self.ImportAuthor(self.motorclient.authors_openalex, topics_dict=self.topics_dict, more_data=more_author_data)
        author_results = await authors.import_all()
        print(author_results)
        #print('adding works')
        #works = self.ImportWork(self.motorclient.works_openalex, topics_dict=self.topics_dict)
        #work_results = await works.import_all()
        #print(work_results)


    class ImportTopic(GenericSQLImport):
        def __init__(self, collection: motor.motor_asyncio.AsyncIOMotorCollection) -> None:
            super().__init__(collection, Topic)

        async def add_item(self, raw_item: dict) -> None:
            if await Topic.objects.filter(openalex_id=raw_item.get('id')).aexists():
                return await Topic.objects.aget(openalex_id=raw_item.get('id'))
            field_type = None
            domain_type = None
            for field in Topic.FieldTypes.values:
                if field.lower() == raw_item.get('field').get('display_name').lower():
                    field_type = field
                    break
            for domain in Topic.DomainTypes.values:
                if domain.lower() == raw_item.get('domain').get('display_name').lower():
                    domain_type = domain
                    break

            topic_dict = {
                'description': raw_item.get('description'),
                'name'       : raw_item.get('display_name'),
                'domain'     : domain_type,
                'field'      : field_type,
                'openalex_id': raw_item.get('id'),
                'works_count': raw_item.get('works_count'),
                'keywords'   : raw_item.get('keywords'),
                'wikipedia'  : raw_item.get('ids').get('wikipedia'),
                'subfield'   : raw_item.get('subfield').get('display_name'),
                'subfield_id': raw_item.get('subfield').get('id').strip('https://openalex.org/subfields/'),
            }

            topic = Topic(**topic_dict)
            self.raw_items.append(topic)

        async def add_siblings(self, all_topics: list[Topic], topics_dict: dict[str:Topic]) -> None:
            full_siblist = []
            self.performance.start_call(self.add_siblings)
            for topic in all_topics:
                if not topic.siblings:
                    siblings = await self.collection.find_one({'id': topic.openalex_id},
                                                            projection={'_id': 0, 'id': 1, 'siblings': 1})
                    siblist = []
                    full_siblist.extend([sibling.get('id') for sibling in siblings.get('siblings')])
                    for sibling in siblings.get('siblings'):
                        if sibling.get('id') in topics_dict:
                            siblist.append(topics_dict[sibling.get('id')])
                            self.results['m2m_items'] += 1
                    if siblist:
                        await topic.siblings.aset(siblist)
            self.performance.end_call()
            self.results['elapsed_time_m2m'] = self.performance.elapsed_time()
            self.results['average_time_per_call_m2m'] = self.performance.time_per_call(self.add_siblings)
            self.results['total_measured_duration_m2m'] = self.performance.total_measured_duration(self.add_siblings)
            return self.results

    class ImportGroup(GenericSQLImport):
        def __init__(self, collection: motor.motor_asyncio.AsyncIOMotorCollection) -> None:
            super().__init__(collection, Group, 'internal_repository_id')

        async def add_item(self, raw_item: dict) -> None:
            if await Group.objects.filter(internal_repository_id=raw_item.get('internal_repository_id')).aexists():
                return True

            faculty = None
            if raw_item.get('part_of'):
                if raw_item.get('part_of').get('name') in FACULTYNAMES:
                    faculty = raw_item.get('part_of').get('name')

            group_dict = {
                'name'                  : raw_item.get('name'),
                'faculty'               : faculty,
                'internal_repository_id': raw_item.get('internal_repository_id'),
                'org_type'              : raw_item.get('type'),
                'scopus_affiliation_ids': raw_item.get('identifiers').get('Scopus affiliation ID') if raw_item.get(
                    'identifiers') else None,
                'acronym'               : raw_item.get('acronym'),
            }

            group = Group(**group_dict)
            self.raw_items.append(group)

        async def add_part_of(self) -> None:
            self.performance.start_call(self.add_part_of)
            all_groups = {g.internal_repository_id: g async for g in Group.objects.all()}
            for group in all_groups.values():
                raw_group = await self.collection.find_one({'internal_repository_id': group.internal_repository_id})
                if raw_group:
                    if raw_group.get('part_of'):
                        part_of_id = raw_group.get('part_of').get('internal_repository_id')
                        if part_of_id in all_groups:
                            await group.part_of.aadd(all_groups[part_of_id])
                            self.results['m2m_items'] += 1
            self.performance.end_call()
            self.results['elapsed_time_m2m'] = self.performance.elapsed_time()
            self.results['average_time_per_call_m2m'] = self.performance.time_per_call(self.add_part_of)
            self.results['total_measured_duration_m2m'] = self.performance.total_measured_duration(self.add_part_of)
            return self.results

    class ImportFunder(GenericSQLImport):

        def __init__(self, collection: motor.motor_asyncio.AsyncIOMotorCollection) -> None:
            super().__init__(collection, Funder)
        
        async def add_item(self, raw_item: dict) -> None:
            if await Funder.objects.filter(internal_repository_id=raw_item.get('openalex_id')).aexists():
                return True

            if await Funder.objects.filter(openalex_id=raw_item.get('id')).aexists():
                return await Funder.objects.aget(openalex_id=raw_item.get('id'))
            funder_dict = {
                'openalex_id'          : raw_item.get('id'),
                'name'                 : raw_item.get('display_name'),
                'alternate_names'      : raw_item.get('alternate_titles'),
                'country_code'         : raw_item.get('country_code'),
                'counts_by_year'       : raw_item.get('counts_by_year'),
                'openalex_created_date': datetime.strptime(raw_item.get('created_date'), '%Y-%m-%d'),
                'openalex_updated_date': timezone.localize(datetime.strptime(raw_item.get('updated_date'), '%Y-%m-%dT%H:%M:%S.%f')),
                'grants_count'         : raw_item.get('grants_count'),
                'description'          : raw_item.get('description'),
                'homepage_url'         : raw_item.get('homepage_url'),
                'ror'                  : raw_item.get('ids').get('ror'),
                'wikidata'             : raw_item.get('ids').get('wikidata'),
                'crossref'             : raw_item.get('ids').get('crossref'),
                'doi'                  : raw_item.get('ids').get('doi'),
                'image_thumbnail_url'  : raw_item.get('image_thumbnail_url'),
                'image_url'            : raw_item.get('image_url'),
                'impact_factor'        : raw_item.get('summary_stats').get('2yr_mean_citedness'),
                'h_index'              : raw_item.get('summary_stats').get('h_index'),
                'i10_index'            : raw_item.get('summary_stats').get('i10_index'),
                'works_count'          : raw_item.get('works_count'),
                'cited_by_count'       : raw_item.get('cited_by_count'),
            }
            funder = Funder(**funder_dict)
            self.raw_items.append(funder)

        async def add_m2m_relations(self) -> None:
            print('Funder m2m relation as_other_funders not implemented yet.')
        
    class ImportSource(GenericSQLImport):
        def __init__(self, collection: motor.motor_asyncio.AsyncIOMotorCollection, detailed_topics: bool = False, topics_dict: dict[str:Topic] = None) -> None:
            super().__init__(collection, Source)
            self.detailed_topics = detailed_topics
            self.topics_dict: dict[str:Topic] = topics_dict

        async def add_dealdata(self, source: Source) -> DealData:
            dealdata_raw = await motorclient.deals_journalbrowser.find_one({'id': source.openalex_id})
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
                    'dealtype'             : dealtype,
                    'issns'                : dealdata_raw.get('issns'),
                    'keywords'             : dealdata_raw.get('keywords'),
                    'journal_title'        : dealdata_raw.get('title'),
                    'publisher_name'       : dealdata_raw.get('publisher'),
                    'openalex_display_name': dealdata_raw.get('oa_display_name'),
                    'openalex_issn_l'      : dealdata_raw.get('oa_issn_l'),
                    'openalex_type'        : dealdata_raw.get('oa_type'),
                    'jb_url'               : dealdata_raw.get('journal_browser_url'),
                    'openalex_issn'        : dealdata_raw.get('oa_issn'),

                }
                dealdata_unique_dict = {
                    'openalex_id': dealdata_raw.get('id'),
                }
                dealdata, created = await DealData.objects.aget_or_create(**dealdata_unique_dict)
                if created:
                    for key, value in dealdata_update_dict.items():
                        if key in dealdata.__dict__:
                            setattr(dealdata, key, value)
                    await dealdata.asave()
                if related_source not in [source async for source in dealdata.related_sources.all()]:
                    await dealdata.related_sources.aadd(related_source)
                return dealdata

        async def add_item(self, raw_item: dict) -> None:
            if await Source.objects.filter(openalex_id=raw_item.get('id')).aexists():
                return await Source.objects.aget(openalex_id=raw_item.get('id'))

            raw_type = raw_item.get('type')
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
                'openalex_id'          : raw_item.get('id'),
                'openalex_created_date': datetime.strptime(raw_item.get('created_date'), '%Y-%m-%d'),
                'openalex_updated_date': timezone.localize(datetime.strptime(raw_item.get('updated_date'), '%Y-%m-%dT%H:%M:%S.%f')),
                'is_in_doaj'           : raw_item.get('is_in_doaj'),
                'is_oa'                : raw_item.get('is_oa'),
                'country_code'         : raw_item.get('country_code'),
                'source_type'          : source_type,
                'title'                : raw_item.get('display_name'),
                'alternate_titles'     : raw_item.get('alternate_titles'),
                'abbreviated_title'    : raw_item.get('abbreviated_title'),
                'homepage_url'         : raw_item.get('homepage_url'),
                'host_org_name'        : raw_item.get('host_organization_name'),
                'issn_l'               : raw_item.get('issn_l'),
                'issn'                 : raw_item.get('issn'),
                'wikidata'             : raw_item.get('ids').get('wikidata') if raw_item.get('ids') else None,
                'fatcat'               : raw_item.get('ids').get('fatcat') if raw_item.get('ids') else None,
                'mag'                  : raw_item.get('ids').get('mag') if raw_item.get('ids') else None,
                'cited_by_count'       : raw_item.get('cited_by_count'),
                'counts_by_year'       : raw_item.get('counts_by_year'),
                'works_api_url'        : raw_item.get('works_api_url'),
                'works_count'          : raw_item.get('works_count'),
                'impact_factor'        : raw_item.get('summary_stats').get('2yr_mean_citedness'),
                'h_index'              : raw_item.get('summary_stats').get('h_index'),
                'i10_index'            : raw_item.get('summary_stats').get('i10_index'),
                'apc_prices'           : raw_item.get('apc_prices'),
                'apc_usd'              : raw_item.get('apc_usd'),
            }
            source = Source(**source_dict)
            self.raw_items.append(source)
            return source


        async def add_m2m_relations(self) -> None:
            print('Note: Lineage relation for source not implemented yet.')
            for source in self.new_items:
                try:
                    self.performance.start_call(self.add_m2m_relations)
                    if self.detailed_topics:
                        source_raw = self.collection.find_one({'id': source.openalex_id})
                        if source_raw.get('topics'):
                            for topic_raw in source_raw.get('topics'):
                                topic = self.topics_dict.get(topic_raw.get('id'))
                                if not topic:
                                    continue
                                source_topic = SourceTopic(source=source, topic=topic, count=topic_raw.get('count'))
                                self.results['added_m2m_relations'] += 1
                                await source_topic.asave()
                    await self.add_dealdata(source)
                    self.results['added_m2m_relations'] += 1
                    self.performance.end_call()

                except Exception as e:
                    self.results['errors'] += 1
                    print(f'error {e} while adding m2m relations for {self.model.__name__}')
                    self.performance.end_call()
                    continue

    class ImportPublisher(GenericSQLImport):
        def __init__(self, collection: motor.motor_asyncio.AsyncIOMotorCollection) -> None:
            super().__init__(collection, Publisher)

        async def add_item(self, raw_item: dict) -> None:
            if await Publisher.objects.filter(openalex_id=raw_item.get('id')).aexists():
                return await Publisher.objects.aget(openalex_id=raw_item.get('id'))
            publisher_dict = {
                'openalex_id'          : raw_item.get('id'),
                'openalex_created_date': datetime.strptime(raw_item.get('created_date'), '%Y-%m-%d'),
                'openalex_updated_date': timezone.localize(
                    datetime.strptime(raw_item.get('updated_date'), '%Y-%m-%dT%H:%M:%S.%f')),
                'name'                 : raw_item.get('display_name'),
                'alternate_names'      : raw_item.get('alternate_titles'),
                'country_code'         : raw_item.get('country_code'),
                'counts_by_year'       : raw_item.get('counts_by_year'),
                'hierarchy_level'      : raw_item.get('hierarchy_level'),
                'ror'                  : raw_item.get('ids').get('ror'),
                'wikidata'             : raw_item.get('ids').get('wikidata'),
                'image_url'            : raw_item.get('image_url'),
                'image_thumbnail_url'  : raw_item.get('image_thumbnail_url'),
                'sources_api_url'      : raw_item.get('sources_api_url'),
                'impact_factor'        : raw_item.get('2yr_mean_citedness'),
                'h_index'              : raw_item.get('h_index'),
                'i10_index'            : raw_item.get('i10_index'),
                'works_count'          : raw_item.get('works_count'),
            }

            publisher = Publisher(**publisher_dict)
            self.raw_items.append(publisher)
            
        async def add_m2m_relations(self) -> None:
            print('lineage, as_funder, as_institution m2m relations for publisher not implemented yet.')

    class ImportOrganization(GenericSQLImport):
        def __init__(self, collection: motor.motor_asyncio.AsyncIOMotorCollection, detailed_topics: bool = False, topics_dict: dict[str:Topic] = None) -> None:
            super().__init__(collection, Organization)
            self.detailed_topics = detailed_topics
            self.topics_dict: dict[str:Topic] = topics_dict

        async def add_item(self, raw_item: dict) -> None:
            if await Organization.objects.filter(openalex_id=raw_item.get('id')).aexists():
                return await Organization.objects.aget(openalex_id=raw_item.get('id'))
            organization_dict = {
                'name'                 : raw_item.get('display_name'),
                'name_acronyms'        : raw_item.get('display_name_acronyms'),
                'name_alternatives'    : raw_item.get('display_name_alternatives'),
                'ror'                  : raw_item.get('ids').get('ror'),
                'openalex_id'          : raw_item.get('id'),
                'wikipedia'            : raw_item.get('ids').get('wikipedia'),
                'wikidata'             : raw_item.get('ids').get('wikidata'),
                'openalex_created_date': datetime.strptime(raw_item.get('created_date'), '%Y-%m-%d'),
                'openalex_updated_date': timezone.localize(
                    datetime.strptime(raw_item.get('updated_date'), '%Y-%m-%dT%H:%M:%S.%f')),
                'country_code'         : raw_item.get('country_code'),
                'works_count'          : raw_item.get('works_count'),
                'cited_by_count'       : raw_item.get('cited_by_count'),
                'impact_factor'        : raw_item.get('2yr_mean_citedness'),
                'h_index'              : raw_item.get('h_index'),
                'i10_index'            : raw_item.get('i10_index'),
                'image_thumbnail_url'  : raw_item.get('image_thumbnail_url'),
                'image_url'            : raw_item.get('image_url'),
            }
            organization = Organization(**organization_dict)
            self.raw_items.append(organization)

        async def add_m2m_relations(self) -> None:
            for organization in self.new_items:
                try:
                    self.performance.start_call(self.add_m2m_relations)
                    organization_raw = self.collection.find({'id': organization.openalex_id}, projection={'_id': 0, 'id': 1, 'topics': 1})
                    if self.detailed_topics:
                        if organization_raw.get('topics'):
                            for topic_raw in organization_raw.get('topics'):
                                topic = self.topics_dict.get(topic_raw.get('id'))
                                if not topic:
                                    continue
                                organization_topic = OrganizationTopic(organization=organization, topic=topic,
                                                                    count=topic_raw.get('count'))
                                await organization_topic.asave()
                                self.results['added_m2m_relations'] += 1

                    if organization_raw.get('roles'):
                        for role in organization_raw.get('roles'):
                            if role.get('role'):
                                tag = await Tag.objects.acreate(tag_type=Tag.TagTypes.ORG_TYPE, notes=role.get('role'),
                                                                content_object=organization)
                                self.results['added_m2m_relations'] += 1
                    self.performance.end_call()
                except Exception as e:
                    self.results['errors'] += 1
                    print(f'error {e} while adding m2m relations for {self.model.__name__}')
                    self.performance.end_call()
                    continue

        async def add_org_links(self) -> list[MusModel]:
            # for Publisher, Organization, Funder, Source: add links between them (most many-to-many fields)
            changed_itemlist = []
            print('m2m relations for orgs not implemented at the moment')
            for publisher in Publisher.objects.all():
                ...
                # lineage = models.ManyToManyField('Publisher', related_name="publ_children")
                # as_funder = models.ManyToManyField('Funder', related_name="as_publisher")
                # as_institution = models.ManyToManyField('Organization', related_name="as_publisher")

            for organization in Organization.objects.all():
                ...
                # repositories = models.ManyToManyField('Source', related_name="repositories")
                # lineage = models.ManyToManyField('Organization', related_name="org_children")

            for funder in Funder.objects.all():
                # as_other_funders = models.ManyToManyField('Funder', related_name="other_funders_entries")
                ...
            for source in Source.objects.all():
                ...
                # lineage = models.ManyToManyField('Publisher', related_name="children")

            return changed_itemlist

    class ImportAuthor(GenericSQLImport):
        def __init__(self, collection: motor.motor_asyncio.AsyncIOMotorCollection, topics_dict: dict[str:Topic] = None, more_data: dict[str:dict] = None) -> None:
            super().__init__(collection=collection, model=Author, more_data=more_data)
            self.topics_dict: dict[str:Topic] = topics_dict


        async def add_item(self, raw_item: dict) -> None:
            def get_names() -> tuple[HumanName, list[str]]:
                # from openalex
                namelist = raw_item.get('display_name_alternatives') if raw_item.get(
                    'display_name_alternatives') else []
                namelist.append(raw_item.get('display_name'))
                # from pure/institute repo
                if raw_item.get('author_name'):
                    namelist.append(raw_item.get('author_name'))
                    namelist.append(raw_item.get('author_default_publishing_name'))
                    namelist.append(raw_item.get('author_known_as_name'))
                # from employee page
                if raw_item.get('foundname'):
                    namelist.append(raw_item.get('foundname'))
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
                'standardized_name': standardized_name.full_name,
                'first_names'      : standardized_name.first,
                'last_name'        : standardized_name.last,
                'middle_names'     : standardized_name.middle,
                'initials'         : standardized_name.initials(),
                'prefixes'         : standardized_name.title,
                'suffixes'         : standardized_name.suffix,
                # also possible to add nickname; not included at the moment
                'alternative_names': namelist,
                'orcid'            : raw_item.get('ids').get('orcid') if raw_item.get('ids') else raw_item.get(
                    'author_orcid'),
                'scopus'           : raw_item.get('ids').get('scopus') if raw_item.get('ids') else raw_item.get(
                    'author_scopus_id'),
                'isni'             : raw_item.get('ids').get('isni') if raw_item.get('ids') else raw_item.get(
                    'author_isni'),
            }
            # 2nd dict: openalex data
            openalex_dict = {
                'name'                 : raw_item.get('display_name'),
                'openalex_id'          : raw_item.get('id'),
                'openalex_created_date': datetime.strptime(raw_item.get('created_date'), '%Y-%m-%d'),
                'openalex_updated_date': timezone.localize(datetime.strptime(raw_item.get('updated_date'), '%Y-%m-%dT%H:%M:%S.%f')),
                'works_api_url'        : raw_item.get('works_api_url'),
                'works_count'          : raw_item.get('works_count'),
                'cited_by_count'       : raw_item.get('cited_by_count'),
                'counts_by_year'       : raw_item.get('counts_by_year'),
                'impact_factor'        : raw_item.get('2yr_mean_citedness'),
                'h_index'              : raw_item.get('h_index'),
                'i10_index'            : raw_item.get('i10_index'),
            }
            # 3rd dict: pure/institute repo data
            pure_dict = {
                'pure_uuid'         : raw_item.get('author_uuid'),
                'pure_id'           : raw_item.get('author_pureid'),
                'pure_last_modified': raw_item.get('last_modified')[0] if isinstance(raw_item.get('last_modified'),list) else raw_item.get('last_modified'),
                'author_links'      : raw_item.get('author_links'),
            }
            # 4th dict: institute people page data
            people_page_dict = {
                'avatar_url'  : raw_item.get('avatar_url'),
                'profile_url' : raw_item.get('profile_url'),
                'research_url': raw_item.get('research_url'),
                'email'       : raw_item.get('email'),
            }
            # 5th dict: name-match info
            match_info_dict = {
                'searched_name'   : raw_item.get('searchname'),
                'found_name'      : raw_item.get('foundname'),
                'match_similarity': raw_item.get('similarity'),
            }
            # step 3: combine the dicts and store as Author
            author = Author(**author_dict, **openalex_dict, **pure_dict, **people_page_dict, **match_info_dict)
            self.raw_items.append(author)

            
        async def add_m2m_relations(self) -> None:
            for author in self.new_items:
                try:
                    self.performance.start_call(self.add_m2m_relations)
                    author_raw = self.collection.find({'id': author.openalex_id})
                    if author_raw.get('topics'):
                        topiclist = []
                        for topic_raw in author_raw.get('topics'):
                            topic = self.topics_dict.get(topic_raw.get('id'))
                            if not topic:
                                continue
                            topiclist.append(topic)
                            self.results['added_m2m_relations'] += 1
                        await author.topics.aset(topiclist)

                    for affiliation in author_raw.get('affiliations'):
                        await self.add_affiliation(affiliation, author, author_raw)


                    self.performance.end_call()
                except Exception as e:
                    self.results['errors'] += 1
                    print(f'error {e} while adding m2m relations for {self.model.__name__}')
                    self.performance.end_call()
                    continue

            return author

        async def add_affiliation(self, affiliation_raw: dict, author: Author, author_raw: dict) -> Affiliation:
            # openalex data
            organization = await Organization.objects.filter(
                openalex_id=affiliation_raw.get('institution').get('id')).afirst()
            if not organization:
                return None
            affiliation_dict = {
                'years'       : affiliation_raw.get('years'),
                'author'      : author,
                'organization': organization,
            }
            # institutional data
            groups = []
            if author_raw.get('affiliations'):
                if organization.openalex_id == OPENALEX_INSTITUTE_ID:
                    for item in author_raw.get('affiliations'):
                        try:
                            if item.get('internal_repository_id'):
                                group = await Group.objects.filter(internal_repository_id=item.get('internal_repository_id')).afirst()
                                if not group:
                                    print(f'group {item} not found in sql db.')
                                else:
                                    groups.append(group)
                        except Exception as e:
                            print(f'error while adding groups to affiliation: {e}')
                            continue
                    

            if author_raw.get('grouplist') and len(
                author_raw.get('grouplist')) > 0 and organization.openalex_id == OPENALEX_INSTITUTE_ID:
                for item in author_raw.get('grouplist'):
                    try:
                        if not item.get('section'):
                            continue
                        if item.get('department') in FACULTYNAMES:
                            faculty = item.get('department')
                        else:
                            faculty = 'Other'
                        group, created = await Group.objects.aget_or_create(name=item.get('section'), faculty=faculty)
                        if group not in groups:
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
            if groups:
                await affiliation.groups.aset(groups)
            return affiliation

    class ImportWork(GenericSQLImport):
        def __init__(self, collection: motor.motor_asyncio.AsyncIOMotorCollection, topics_dict: dict[str:Topic] = None) -> None:
            super().__init__(collection, Work)
            self.topics_dict: dict[str:Topic] = topics_dict

        async def add_item(self, raw_item: dict) -> None:
            # TODO: itemtype classification
            # NOTE: Openalex: 'We added four new work types, reclassifying existing works: “preprint” (5.7M), “libguides” (1.8M), “review” (820k), and “supplementary-materials” (50k).'

            work_dict = {

                'openalex_id'             : raw_item.get('id'),
                'openalex_created_date'   : datetime.strptime(raw_item.get('created_date'), '%Y-%m-%d'),
                'openalex_updated_date'   : timezone.localize(datetime.strptime(raw_item.get('updated_date'), '%Y-%m-%dT%H:%M:%S.%f')),
                'ngrams_url'              : raw_item.get('ngrams_url'),
                'cited_by_api_url'        : raw_item.get('cited_by_api_url'),
                'cited_by_count'          : raw_item.get('cited_by_count'),
                'cited_by_percentile_year': raw_item.get('cited_by_percentile_year'),
                'referenced_works_count'  : raw_item.get('referenced_works_count'),
                'doi'                     : raw_item.get('doi'),
                'title'                   : raw_item.get('title'),
                'publication_year'        : raw_item.get('publication_year'),
                'publication_date'        : raw_item.get('publication_date'),
                'pmid'                    : raw_item.get('ids').get('pmid') if raw_item.get('ids') else None,
                'pmcid'                   : raw_item.get('ids').get('pmcid') if raw_item.get('ids') else None,
                'isbn'                    : raw_item.get('ids').get('isbn') if raw_item.get('ids') else None,
                'mag'                     : raw_item.get('ids').get('mag') if raw_item.get('ids') else None,
                'language'                : raw_item.get('language'),
                'mesh_terms'              : raw_item.get('mesh'),
                'type_crossref'           : raw_item.get('type_crossref'),
                'volume'                  : raw_item.get('biblio').get('volume') if raw_item.get('biblio') else None,
                'issue'                   : raw_item.get('biblio').get('issue') if raw_item.get('biblio') else None,
                'first_page'              : raw_item.get('biblio').get('first_page') if raw_item.get(
                    'biblio') else None,
                'last_page'               : raw_item.get('biblio').get('last_page') if raw_item.get('biblio') else None,
                'pages'                   : None,
                'article_number'          : None,
                'locations_count'         : raw_item.get('locations_count'),
                'is_oa'                   : raw_item.get('open_access').get('is_oa') if raw_item.get(
                    'open_access') else None,
                'oa_status'               : raw_item.get('open_access').get('oa_status') if raw_item.get(
                    'open_access') else None,
                'oa_url'                  : raw_item.get('open_access').get('oa_url') if raw_item.get(
                    'open_access') else None,
                'is_also_green'           : raw_item.get('open_access').get(
                    'any_repository_has_fulltext') if raw_item.get('open_access') else None,
                'itemtype'                : raw_item.get('type'),
                'apc_listed'              : raw_item.get('apc_list').get('value_usd') if raw_item.get(
                    'apc_list') else None,
                'apc_paid'                : raw_item.get('apc_paid').get('value_usd') if raw_item.get(
                    'apc_paid') else None,
                'has_fulltext'            : raw_item.get('has_fulltext'),
                'is_paratext'             : raw_item.get('is_paratext'),
                'is_retracted'            : raw_item.get('is_retracted'),
                'indexed_in'              : raw_item.get('indexed_in'),
                'keywords'                : raw_item.get('keywords'),
                'sdgs'                    : raw_item.get('sustainable_development_goals'),
                'versions'                : raw_item.get('versions'),
            }
            '''
            # add raw data from other data sources
            datacite_raw = await self.motorclient.items_datacite.find_one({'id': raw_item.get('id')},
                                                                          projection={'_id': 0})
            if datacite_raw:
                datacite = DataCiteData(data=datacite_raw)
                await datacite.asave()
                work_dict['datacite_data'] = datacite
                work_dict['found_in_datacite'] = True
            openaire_raw = await self.motorclient.items_openaire.find_one({'id': raw_item.get('id')},
                                                                          projection={'_id': 0})
            if openaire_raw:
                openaire = OpenAireData(data=openaire_raw)
                await openaire.asave()
                work_dict['openaire_data'] = openaire
                work_dict['found_in_openaire'] = True
            crossref_raw = await self.motorclient.items_crossref.find_one({'id': raw_item.get('id')},
                                                                          projection={'_id': 0})
            if crossref_raw:
                crossref = CrossrefData(data=crossref_raw)
                await crossref.asave()
                work_dict['crossref_data'] = crossref
                work_dict['found_in_crossref'] = True
            repository_raw = await self.motorclient['items_pure_oaipmh'].find_one({'id': raw_item.get('id')},
                                                                                  projection={'_id': 0})
            if repository_raw:
                repository = RepositoryData(data=repository_raw)
                await repository.asave()
                work_dict['repo_data'] = repository
                work_dict['found_in_institute_repo'] = True
            '''
            work = Work(**work_dict)
            self.raw_items.append(work)

        async def add_m2m_relations(self) -> None:
            for work in self.new_items:
                self.performance.start_call(self.add_m2m_relations)
                raw_item = self.collection.find({'id': work.openalex_id})

        

            if raw_item.get('abstract_inverted_index'):
                abstract = await self.add_abstract(raw_item.get('abstract'))
                if abstract:
                    work.abstract = abstract
                    self.results['added_m2m_relations'] += 1
                    await work.asave()

            if raw_item.get('topics'):
                topiclist = []
                for topic_raw in raw_item.get('topics'):
                    topic = self.topics_dict.get(topic_raw.get('id'))
                    if not topic:
                        continue
                    topiclist.append(topic)
                    self.results['added_m2m_relations'] += 1

                await work.topics.aset(topiclist)

            if raw_item.get('primary_topic'):
                topic = self.topics_dict.get(raw_item.get('primary_topic').get('id'))
                if topic:
                    work.primary_topic = topic
                    self.results['added_m2m_relations'] += 1
                    await work.asave()

            await self.add_authorships(raw_item.get('authorships'), work)

            if raw_item.get('grants'):
                await self.add_grants(raw_item.get('grants'), work)
            if raw_item.get('locations'):
                best_oa_location = raw_item.get('best_oa_location')
                primary_location = raw_item.get('primary_location')
                work = await self.add_locations(raw_item.get('locations'), work, best_oa_location, primary_location)

            self.performance.end_call()


        async def add_locations(self, locations_raw: dict, work: Work, best_oa_location: dict | None,
                                primary_location: dict | None) -> Work:
            async def make_location(location_raw: dict):
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
                    'source'          : source,
                    'source_type'     : source_type,
                    'is_oa'           : location_raw.get('is_oa') if isinstance(location_raw.get('is_oa'),bool) else False,
                    'landing_page_url': location_raw.get('landing_page_url'),
                    'pdf_url'         : location_raw.get('pdf_url'),
                    'license'         : location_raw.get('license'),
                    'license_id'      : location_raw.get('license_id'),
                    'version'         : location_raw.get('version'),
                    'is_accepted'     : location_raw.get('is_accepted') if isinstance(location_raw.get('is_accepted'),bool) else False,
                    'is_published'    : location_raw.get('is_published') if isinstance(location_raw.get('is_published'),bool) else False,
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

            location_tasks: list[asyncio.Task] = []
            async with asyncio.TaskGroup() as tg:
                for location in locations_raw:
                    location_tasks.append(tg.create_task(make_location(location)))

            locations: list[Location] = []
            for task in location_tasks:
                locations.append(task.result())
            if locations:
                await work.locations.aset(locations)
            return work

        async def add_abstract(self, abstract_raw: dict) -> Abstract:
            abstract_text = await parse_reversed_abstract(abstract_raw)
            abstract = Abstract(text=abstract_text)
            await abstract.asave()
            return abstract

        async def add_authorships(self, authorships_raw: list[dict], work: Work) -> list[Authorship]:
            authorships = []
            for authorship_raw in authorships_raw:
                try:
                    author = await Author.objects.filter(openalex_id=authorship_raw.get('author').get('id')).afirst()
                except Exception as e:
                    print(
                        f'{e} while retrieving author {authorship_raw.get("author")} for authorship {authorship_raw.get("id")}')
                    continue
                if not author:
                    self.missing_authors.append(authorship_raw.get('author').get('id'))
                    continue

                authorship_dict = {
                    'author'          : author,
                    'work'            : work,
                    'is_corresponding': authorship_raw.get('is_corresponding'),
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

        async def add_grants(self, grants_raw: list[dict], work: Work) -> Work:
            grants = []
            # work is a fk to the work object, so we can add grants to it directly

            for grant_raw in grants_raw:
                funder = await Funder.objects.filter(openalex_id=grant_raw.get('funder')).afirst()
                if not funder:
                    self.missing_funders.append(grant_raw.get('funder'))
                    continue
                grant_dict = {
                    'funder'     : funder,
                    'award_id'   : grant_raw.get('award_id'),
                    'funder_name': grant_raw.get('funder_name'),
                    'work'       : work,
                }
                grant = Grant(**grant_dict)
                await grant.asave()
                grants.append(grant)

            return grants
