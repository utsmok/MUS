import httpx

from mus_wizard.database.mongo_client import MusMongoClient
from mus_wizard.harvester.openalex import OpenAlexAPI, OpenAlexQuery
from mus_wizard.harvester.oai_pmh import OAI_PMH
from mus_wizard.constants import  ROR, APIEMAIL
from dataclasses import dataclass, field
from enum import Enum
from rich.console import Console
from rich.table import Table
from mus_wizard.utils import normalize_doi
from itertools import count
import pandas as pd
from pyalex import Works
import pyalex
from itertools import chain
from bson import SON
import os
import aiometer
import functools
from pymongo import UpdateMany
# import module to create excel files
from itertools import batched
pyalex.config.email = APIEMAIL
pyalex.config.max_retries = 5
pyalex.config.retry_backoff_factor = 0.2
pyalex.config.retry_http_codes = [429, 500, 503]

co = Console()
facultymapping = {
    'Faculty of Behavioural, Management and Social Sciences': 'BMS',
    'Faculty of Science and Technology': 'TNW',
    'Faculty of Engineering Technology': 'ET',
    'Faculty of Geo-Information Science and Earth Observation': 'ITC',
    'Faculty of Electrical Engineering, Mathematics and Computer Science': 'EEMCS',
    'University of Twente': 'UT',
}

class DataSource(Enum):
    OPENALEX = 1
    OPENAIRE = 2
    CROSSREF = 3
    PURE = 4
    ORCID = 5

@dataclass
class Faculty:
    name: str
    pure_id: str
    id: int = field(default_factory=count().__next__)

@dataclass
class Group:
    id: int = field(default_factory=count().__next__)
    name: str | None = None
    faculty: Faculty | None = None
    pure_id: str | None = None
    acronym: str | None = None

@dataclass
class Author:
    datasources: list[DataSource]
    openalex_id: str | None = None
    pure_id: str | None = None
    orcid: str | None = None
    scopus: str | None = None
    groups: list[Group] = field(default_factory=list)
    ids: dict[str, str] = field(default_factory=dict)
    name: str | None = None
    id: int = field(default_factory=count().__next__)

    def facultyset(self) -> set[str]:
        faculties = set()
        for group in self.groups:
            if group:
                if group.faculty:
                    faculties.add(facultymapping[group.faculty.name])
        return faculties
    def groupset(self) -> set[str]:
        groups = set()
        for group in self.groups:
            if group:
                if group.name:
                    groups.add(group.name)
        return groups
@dataclass
class Publisher:
    id: int = field(default_factory=count().__next__)
    name: str | None = None
    openalex_id: str | None = None

@dataclass
class Journal:
    id: int = field(default_factory=count().__next__)
    name: str | None = None
    openalex_id: str | None = None
    publisher: Publisher | None = None
    issns: list[str] | None = None
    issn_l: list[str] | None = None


class WorkType(Enum):
    JOURNAL_ARTICLE = 1
    CONFERENCE_PROCEEDING = 2
    BOOK = 3
    BOOK_CHAPTER = 4
    OTHER = 5

@dataclass
class Work:
    data_sources: list[DataSource]
    openalex_id: str | None = None
    pure_id: str | None = None
    openaire_id: str | None = None
    authors: list[Author] = field(default_factory=list)

    publishers: list[Publisher] = field(default_factory=list)
    journals: list[Journal] = field(default_factory=list)
    doi: str | None = None
    title: str | None = None
    year: int | None = None
    type: int | None = None
    id: int = field(default_factory=count().__next__)

    def has_group_data(self):
        for author in self.authors:
            if len(author.groups) > 0:
                return True
    def get_faculties(self) -> set[str]:
        faculties = set()
        for author in self.authors:
            if author:
                faculties.update(author.facultyset())
        return list(faculties)
    def get_groups(self) -> set[str]:
        groups = set()
        for author in self.authors:
            if author:
                groups.update(author.groupset())
        return list(groups)
    def get_authors(self) -> set[str]:
        val = []
        for author in self.authors:
            if author:
                val.append(author.name)
        return val
    def get_journals(self) -> set[str]:
        journals = []
        for journal in self.journals:
            if journal:
                journals.append(journal.name)
        return journals
    def get_publishers(self) -> set[str]:
        publishers = []
        for publisher in self.publishers:
            if publisher:
                publishers.append(publisher.name)
        return publishers

    def get_non_lists(self) -> dict[str, str]:
        non_lists = {}
        if self.openalex_id:
            non_lists['openalex_id'] = self.openalex_id
        if self.pure_id:
            non_lists['pure_id'] = self.pure_id
        if self.openaire_id:
            non_lists['openaire_id'] = self.openaire_id
        if self.doi:
            non_lists['doi'] = self.doi
        if self.title:
            non_lists['title'] = self.title
        if self.year:
            non_lists['year'] = self.year
        if self.type:
            if self.type == WorkType.JOURNAL_ARTICLE:
                non_lists['type'] = 'journal-article'
            elif self.type == WorkType.CONFERENCE_PROCEEDING:
                non_lists['type'] = 'conference-proceedings'
            elif self.type == WorkType.BOOK_CHAPTER:
                non_lists['type'] = 'book-chapter'
            elif self.type == WorkType.BOOK:
                non_lists['type'] = 'book'
            elif self.type == WorkType.OTHER:
                non_lists['type'] = 'other'
        return non_lists



@dataclass
class HarvestData:

    authors: dict[str, Author] = field(default_factory=dict)
    flat_authors: list[Author] = field(default_factory=list)
    works: dict[str, Work] = field(default_factory=dict)
    flat_works: list[Work] = field(default_factory=list)
    groups: dict[str, Group] = field(default_factory=dict)
    faculties: dict[str, Faculty] = field(default_factory=dict)
    period: list[int] = field(default_factory=list)
    mongoclient = MusMongoClient(database='library_overview')
    missing_authors: list = field(default_factory=list)
    journals: dict[str, Journal] = field(default_factory=dict)
    journals_flat: list[Journal] = field(default_factory=list)
    publishers: dict[str, Publisher] = field(default_factory=dict)
    publishers_flat: list[Publisher] = field(default_factory=list)
    missing_issns: list = field(default_factory=list)
    reference_data: dict[str, dict] = field(default_factory=dict)
    
    async def run(self, period = None, key=None, secret=None):
        if period:
            self.period = period
        else:
            self.period = [2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024]

        ut = Faculty(name='University of Twente', pure_id='491145c6-1c9b-4338-aedd-98315c166d7e')
        self.faculties[ut.pure_id] = ut
        self.key: str = key if key else os.environ.get('WORLDCAT_KEY')
        self.secret: str = secret if secret else os.environ.get('WORLDCAT_SECRET')
        
        #await self.check_is_in_collection()
        await self.check_doaj()
        #await self.get_work_data()
        #async with asyncio.TaskGroup() as tg:
            #indexes = tg.create_task(self.mongoclient.add_indexes())
            #pure_harvest = tg.create_task(self.harvest_pure())
            #all_openalex = tg.create_task(self.get_ut_works_openalex())
        #await self.make_groups()
        #await self.make_authorlist()
        #await self.make_worklist()
        #await self.make_dataframe()
        #await self.group_data()
        #await self.clean_publisher_names()
        #grouplist = await self.get_grouplist()
        #for group in grouplist:
            #await self.export_csvs(group)

        #await self.add_issn_data()
        #await self.update_published_works()
        #await self.get_publisher_lineage()
        #await self.add_oclc_data()
    async def harvest_pure(self):
        harvester = OAI_PMH(motorclient=self.mongoclient)
        await harvester.get_item_results()

    async def get_ut_works_openalex(self):
        # gets all ut-affiliated works from openalex
        # also retrieves all ut-affiliated authors for those works
        await OpenAlexAPI(years=self.period, openalex_requests={'works_openalex':None, 'authors_openalex':None}, mongoclient=self.mongoclient).run()

    async def make_groups(self):
        self.mongoclient.openaire_cris_orgunits.create_index([('part_of', 1), ('type', 1)])
        self.mongoclient.openaire_cris_orgunits.create_index([('part_of', 1)])
        self.mongoclient.openaire_cris_orgunits.create_index([('type', 1)])
        self.mongoclient.openaire_cris_orgunits.create_index([('internal_repository_id', 1)])
        self.mongoclient.openaire_cris_orgunits.create_index([('acronym', 1)])
        self.mongoclient.openaire_cris_orgunits.create_index([('faculty', 1)])

        async for fac in self.mongoclient.openaire_cris_orgunits.find({'part_of':{'$exists':True}, 'type':{'$in':['faculty']}}):
            if fac.get('part_of'):
                if fac.get('part_of').get('name') == 'University of Twente':
                    faculty = Faculty(name=fac.get('name'), pure_id=fac.get('internal_repository_id'))
                    self.faculties[faculty.pure_id] = faculty
                    group_obj = Group(name=fac.get('name'), pure_id=fac.get('internal_repository_id'), faculty=faculty, acronym=fac.get('acronym'))
                    self.groups[group_obj.pure_id] = group_obj
        async for group in self.mongoclient.openaire_cris_orgunits.find({'part_of':{'$exists':True}, 'type':{'$in':['department', 'institute']}}):
            faculty = self.faculties.get(group.get('part_of').get('internal_repository_id'), None)
            if not faculty:
                co.print(group)
            group_obj = Group(name=group.get('name'), pure_id=group.get('internal_repository_id'), faculty=faculty, acronym=group.get('acronym'))
            self.groups[group_obj.pure_id] = group_obj

        co.print(f'{len(self.faculties)=}')
        co.print(f'{len(self.groups)=}')
    async def make_authorlist(self):
        self.mongoclient.authors_openalex.create_index([('id', 1)])
        self.mongoclient.authors_openalex.create_index([('affiliations', 1)])
        self.mongoclient.authors_openalex.create_index([('display_name', 1)])
        self.mongoclient.authors_openalex.create_index([('ids', 1)])
        self.mongoclient.authors_openalex.create_index([('orcid', 1)])

        async for entry in self.mongoclient.authors_openalex.find({},projection={'id':1, 'affiliations':1, 'display_name':1, 'ids':1, 'orcid':1}):
            if entry['id'] in self.authors:
                continue
            if entry.get('affiliations'):
                for aff in entry['affiliations']:
                    if aff.get('institution'):
                        if aff.get('institution').get('ror') == ROR:
                            await self.new_openalex_author(entry)
                            break
        orcid_searchlist = {}
        scopus_searchlist = {}
        self.mongoclient.openaire_cris_persons.create_index([('internal_repository_id', 1)])
        self.mongoclient.openaire_cris_persons.create_index([('first_names', 1)])
        self.mongoclient.openaire_cris_persons.create_index([('family_names', 1)])
        self.mongoclient.openaire_cris_persons.create_index([('scopus_id', 1)])
        self.mongoclient.openaire_cris_persons.create_index([('orcid', 1)])
        self.mongoclient.openaire_cris_persons.create_index([('affiliations', 1)])
        async for entry in self.mongoclient.openaire_cris_persons.find({},projection={'internal_repository_id':1, 'first_names':1, 'family_names':1, 'scopus_id':1, 'orcid':1,'affiliations':1}):
            if entry.get('orcid'):
                if entry.get('orcid') in self.authors:
                    await self.update_author_with_pure_data(self.authors[entry.get('orcid')], entry)
                else:
                    orcid_searchlist[entry.get('orcid')] = entry
            if entry.get('scopus_id'):
                if entry.get('scopus_id') in self.authors:
                    await self.update_author_with_pure_data(self.authors[entry.get('scopus_id')], entry)
                else:
                    scopus_searchlist[entry.get('scopus_id')] = entry

        co.print(f'Now retrieving Openalex data for {len(orcid_searchlist)} ORCIDs and {len(scopus_searchlist)} Scopus IDs')
        orcids = [o.replace('\'','') for o in orcid_searchlist.keys()]
        queryc = OpenAlexQuery(self.mongoclient, self.mongoclient.authors_openalex, 'authors', years=self.period)
        queryc.add_query_by_orcid(orcids, single=False)
        await queryc.run()


    async def new_openalex_author(self, data):
        scopus = None
        if data.get('ids').get('scopus'):
            try:
                scopus = data.get('ids').get('scopus').lower()
                if 'authorid' in scopus:
                    scopus = scopus.split('authorid=')[1].strip()
                if '&' in scopus:
                    scopus = scopus.split('&')[0].strip()
            except Exception as e:
                print(f'Error parsing scopus id: {e}')
                print(scopus)
        author = Author(name=data.get('display_name') ,openalex_id=data.get('id'), pure_id=None, orcid=data.get('orcid') if data.get('orcid') else data.get('ids').get('orcid'), datasources=[DataSource.OPENALEX], scopus=scopus, ids=data.get('ids'))
        self.flat_authors.append(author)
        self.authors[data.get('id')] = author
        if data.get('orcid'):
            self.authors[data.get('orcid')] = author
        if data.get('ids').get('orcid') and not data.get('orcid'):
            self.authors[data.get('ids').get('orcid')] = author
        if scopus:
            self.authors[scopus] = author

    async def update_author_with_pure_data(self, author=None, data=None):
        if not author:
            author = Author(datasources=[DataSource.PURE])
            self.flat_authors.append(author)

        author.pure_id = data.get('internal_repository_id')
        self.authors[author.pure_id] = author
        if data.get('orcid'):
            author.orcid = data.get('orcid')
            if author.orcid not in self.authors:
                self.authors[author.orcid] = author
        if data.get('scopus_id'):
            author.scopus = data.get('scopus_id')
            if author.scopus not in self.authors:
                self.authors[author.scopus] = author
        if DataSource.PURE not in author.datasources:
            author.datasources.append(DataSource.PURE)

        groups = []
        tmpgroups = []
        if data.get('affiliations'):
            for affil in data.get('affiliations'):
                id = affil.get('internal_repository_id')
                name = affil.get('name')
                if name != 'University of Twente':
                    if id in self.faculties:
                        tmpgroups.append(self.groups[id])
                    elif id not in self.groups:
                        co.print(f'group {name} with id {id} not in grouplist')
                    else:
                        groups.append(self.groups.get(id))
            if groups:
                author.groups = groups
            elif tmpgroups:
                author.groups = tmpgroups
        if not author.name:
            author.name = data.get('first_names') + ' ' + data.get('family_names')


    async def make_worklist(self):
        async for work in self.mongoclient.works_openalex.find({}):
            if work.get('doi'):
                doi = await normalize_doi(work.get('doi'))
            else:
                doi = None

        async for work in self.mongoclient.openaire_cris_publications.find():
            if work.get('doi'):
                doi = await normalize_doi(work.get('doi'))
            else:
                doi = None


        await self.add_main_data()

    async def add_main_data(self):
        '''
        adds the joined data to mongodb
        '''
        works = [w for w in self.flat_works if (w.openalex_id and w.pure_id and w.publishers and w.journals)]
        co.print(f'{len(works)} works to process')
        for i, entry in enumerate(works):
            datadict = {}
            datadict = entry.get_non_lists()
            datadict['faculties'] = entry.get_faculties()
            datadict['groups'] = entry.get_groups()
            datadict['authors'] = entry.get_authors()
            datadict['journals'] = entry.get_journals()
            datadict['publishers'] = entry.get_publishers()
            await self.mongoclient.mongoclient.data_export.insert_one(datadict)

    async def get_referenced_works_data(self, referenced_works) -> list[dict]:
        async def get_journal_and_publisher(work):
            journal = None
            publisher = None
            if item.get('primary_location'):
                source = item.get('primary_location').get('source')
                if source:
                    if source.get('host_organization'):
                        host_org_id: str = source.get('host_organization')
                        if host_org_id.startswith('https://openalex.org/P'):
                            pub_name = source.get('host_organization_name')
                            pub_id = host_org_id
                            publisher = await self.add_or_get_publisher(name=pub_name, id=pub_id)
                    if (source.get('type') and source.get('type') == 'journal') or publisher:
                        journal_data = {
                                'name': source.get('display_name'),
                                'openalex_id': source.get('id'),
                                'publisher': publisher,
                                'issns': source.get('issn'),
                                'issn_l': source.get('issn_l'),
                            }
                        journal = await self.add_or_get_journal(data=journal_data)
            return journal, publisher
        final_data = []
        querylist = []
        batch = []
        for i, id in enumerate(referenced_works):
            if id in self.reference_data:
                final_data.append(self.reference_data[id])
            else:
                batch.append(id)

            if len(batch) == 50 or i == len(referenced_works) - 1:
                itemids = "|".join(batch)
                querylist.append(Works().filter(openalex_id=itemids))
                batch = []

        for i, query in enumerate(querylist):
            querynum = i + 1
            try:
                for item in chain(*query.paginate(per_page=100, n_max=None)):
                    journal, publisher = await get_journal_and_publisher(item)
                    if journal and publisher:
                        final_data.append({'journal':journal, 'publisher':publisher})
                        self.reference_data[item.get('id')] = {'journal':journal, 'publisher':publisher}
            except Exception as e:
                co.print(f'error while retrieving results for query {querynum} of {len(querylist)}. Error: \n {e}. Query: \n {query.__dict__}')
                continue
        co.print(f'Retrieved journal+publisher data for {len(final_data)} references')
        return final_data
    async def make_dataframe(self):
        '''
        For each finished work in mongodb collection data_export, make a dataframe to be used for analysis

        Columns:
        -> title
        -> doi
        -> year
        -> type
        -> pure id
        -> openalex id
        -> num. authors
        -> 1 journal
        -> 1 publisher

        then, add a bool column for each faculty and each group and mark true if any of the authors linked to the work are in that faculty or group

        '''
        async def make_dataframe_inner(entry):
            no_more_check = True

            referenced_works_data = []
            ddict = {
                'title': entry['title'] if entry.get('title') else None,
                'doi': entry['doi'] if entry.get('doi') else None,
                'year': entry['year'] if entry.get('year') else None,
                'type': entry['type'] if entry.get('type') else None,
                'pure_id': entry['pure_id'] if entry.get('pure_id') else None,
                'openalex_id': entry['openalex_id'] if entry.get('openalex_id') else None,
                'num_authors': len(entry['authors']) if entry.get('authors') else 0,
                'journal': None,
                'publisher': None,
                'open_access_type':None,
                'is_oa':False,
                'primary_topic':None,
                'subfield':None,
                'field':None,
                'domain':None,
            }

            if entry.get('openalex_id'):
                data = await self.mongoclient.works_openalex.find_one({'id':entry.get('openalex_id')})
                if data:
                    ddict['open_access_type'] = data.get('open_access').get('oa_status') if data.get('open_access') else None
                    ddict['is_oa'] = data.get('open_access').get('is_oa') if data.get('open_access') else False
                    ddict['primary_topic'] = data.get('primary_topic').get('display_name') if data.get('primary_topic') else None
                    ddict['subfield'] = data.get('primary_topic').get('subfield').get('display_name') if data.get('primary_topic') else None
                    ddict['field'] = data.get('primary_topic').get('field').get('display_name') if data.get('primary_topic') else None
                    ddict['domain'] = data.get('primary_topic').get('domain').get('display_name') if data.get('primary_topic') else None
                    if (data.get('referenced_works') and entry.get('groups')):
                        if entry.get('pure_id'):
                            if ddict['type'] == 'journal-article':
                                if ddict['year'] >= 2020:
                                    referenced_works_data = await self.get_referenced_works_data(data.get('referenced_works'))
            if entry.get('publishers'):
                newlist = []
                dellist = []
                publist = set(entry['publishers'].copy())
                for k in publist:
                    if 'elsevier' in k.lower():
                        newlist.append('Elsevier')
                        dellist.append(k)
                    if 'springer' in k.lower():
                        newlist.append('Springer')
                        dellist.append(k)
                    if 'wiley' in k.lower():
                        newlist.append('Wiley')
                        dellist.append(k)
                    if 'gruyter' in k.lower():
                        newlist.append('de Gruyter')
                        dellist.append(k)
                    if 'ieee' in k.lower() or 'electrical and electronics engineers' in k.lower():
                        newlist.append('IEEE')
                        dellist.append(k)
                    if 'Multidisciplinary Digital Publishing Institute' in k or 'MDPI' in k:
                        newlist.append('MDPI')
                        dellist.append(k)
                    if 'F1000' in k or 'Faculty of 1000' in k:
                        newlist.append('F1000')
                        dellist.append(k)
                    if 'sage' in k.lower():
                        newlist.append('Sage')
                        dellist.append(k)
                    if 'frontiers' in k.lower():
                        newlist.append('Frontiers')
                        dellist.append(k)
                    if 'acm' in k.lower() or 'Association for Computing Machinery' in k:
                        newlist.append('ACM')
                        dellist.append(k)
                    if 'optical society' in k.lower():
                        newlist.append('The Optical Society')
                        dellist.append(k)
                    if 'optica publishing group' in k.lower() or 'formerly osa' in k.lower():
                        newlist.append('Optica Publishing Group')
                        dellist.append(k)
                for k in dellist:
                    publist.remove(k)
                for k in newlist:
                    publist.add(k)

                publist = list(publist)

                manual = False
                if len(publist) == 0:
                    ddict['publisher'] = None
                if len(publist) == 1:
                    ddict['publisher'] = publist[0]
                if len(publist) == 2:
                    if any(k in publist[0] for k in self.mainlist):
                        ddict['publisher'] = publist[0]
                    elif any(k in publist[1] for k in self.mainlist):
                        ddict['publisher'] = publist[1]
                    else:
                        for item in publist:
                            if any(k in item.lower().replace('.','').replace(',','') for k in self.secondlist):
                                ddict['publisher'] = item
                        else:
                            manual = True
                if no_more_check:
                    ddict['publisher'] = publist[0]
                elif len(publist) > 2 or manual:
                    co.print(f'Data for this item: {entry}')
                    co.print(f'{len(publist)} publishers:')
                    for i,k in enumerate(publist):
                        co.print(f'{i}:   {k}')
                    choice = co.input('Which publisher do you want to use?')
                    if choice == 'xxx':
                        no_more_check = True
                        ddict['publisher'] = publist[0]
                        co.print('Disabled manual publisher selection.')
                    else:
                        self.mainlist.append(publist[int(choice)])
                        ddict['publisher'] = publist[int(choice)]
                    co.print(f'Using publisher: {ddict["publisher"]}')
                    co.print(f'{num_items-itemnum} items remaining...')

            if entry.get('journals'):
                if len(entry['journals']) == 0:
                    ddict['journal'] = None
                elif len(entry['journals']) == 1:
                    ddict['journal'] = entry['journals'][0]
                else:
                    co.print(f'Data for this item: {entry}')
                    co.print(f'{len(entry["journals"])} journals:')
                    for i,k in enumerate(entry['journals']):
                        co.print(f'{i}:   {k}')
                    choice = co.input('Which journal do you want to use?')
                    ddict['journal'] = entry['journals'][int(choice)]
                    co.print(f'Using journal: {ddict["journal"]}')
                    co.print(f'{num_items-itemnum} items remaining...')

            for group in self.grouplist:
                ddict[group] = False
            for faculty in self.facultylist:
                ddict[faculty] = False

            if entry.get('groups'):
                for group in entry['groups']:
                    if group:
                        ddict[group] = True
            if entry.get('faculties'):
                for faculty in entry['faculties']:
                    if faculty:
                        ddict[faculty] = True

            all_refdicts = []
            if referenced_works_data:
                for ref in referenced_works_data:
                    refdict = ddict.copy()
                    refdict['journal'] = ref.get('journal').name
                    refdict['publisher'] = ref.get('publisher').name
                    all_refdicts.append(refdict)

            if all_refdicts:
                return ddict, all_refdicts
            else:
                return ddict, None

        grouplist = set()
        facultylist = set()
        num_items = await self.mongoclient.mongoclient.data_export.estimated_document_count()
        itemnum = 0
        co.print(f'Amount of of items in collection: {num_items}')
        async for entry in self.mongoclient.mongoclient.data_export.find(projection={'_id':0, 'groups':1, 'faculties':1}):
            if entry.get('groups'):
                for group in entry['groups']:
                    if group:
                        grouplist.add(group)
            if entry.get('faculties'):
                for faculty in entry['faculties']:
                    if faculty:
                        facultylist.add(faculty)
        self.grouplist = list(grouplist)
        self.facultylist = list(facultylist)
        co.print(f'{len(grouplist)} groups')
        co.print(f'{len(facultylist)} faculties')
        full_data = []
        full_ref_data = []
        self.mainlist = ['Optica Publishing Group',
            'Elsevier',
            'Taylor & Francis',
            'Nature Publishing Group',
            'Springer',
            'Wiley',
            'de Gruyter',
            'IEEE',
            'MDPI',
            'F1000',
            'Sage',
            'Frontiers',
            'IOP'
            'Emerald Publishing Limited',
            'ACM',
            'The Optical Society',
            'Optica Publishing Group',
        ]
        self.secondlist = ['publishers', 'ltd', 'bv', 'publish', 'inc', 'publishing', 'press', 'limited', 'publications']
        import time
        import aiometer
        import functools

        start_time = time.time()
        itemnum = 0
        itemlist = await self.mongoclient.mongoclient.data_export.find(projection={'_id':0}).to_list(length=50000)
        async with aiometer.amap(functools.partial(make_dataframe_inner), itemlist,
                                 max_at_once=100,
                                 max_per_second=20) as responses:
            async for response in responses:
                ddict, all_refdicts = response
                full_data.append(ddict)
                await self.mongoclient.mongoclient.data_export_rich.insert_one(ddict)
                if all_refdicts:
                    full_ref_data.extend(all_refdicts)
                    await self.mongoclient.mongoclient.data_export_refs.insert_many(all_refdicts)

                itemnum += 1
                if itemnum % 100 == 0:
                    end_time = time.time()
                    elapsed_time = int(end_time - start_time)
                    items_per_second = None
                    time_remaining = None
                    if elapsed_time > 0:
                        items_per_second = int(itemnum / elapsed_time)
                        if items_per_second > 0:
                            time_remaining = int((num_items - itemnum) / items_per_second)

                    co.print(f'Processed {itemnum} / {num_items} items')
                    co.print(f'{elapsed_time} seconds elapsed')
                    co.print(f'{items_per_second} items per second')
                    co.print(f'~{time_remaining} seconds remaining...')

        df = pd.DataFrame(full_data)
        co.print(df.info(verbose=True, memory_usage='deep', show_counts=True, max_cols=20))
        df.to_csv('dataframe.csv')
        df2 = pd.DataFrame(full_ref_data)
        co.print(df2.info(verbose=True, memory_usage='deep', show_counts=True, max_cols=20))
        df2.to_csv('dataframe_ref.csv')
    async def load_and_process_dataframe(self):
        df = pd.read_csv('dataframe.csv')
        co.print(f'{len(df)} items')
        result = {}
        for col in df.columns[9:]:
            result[col] = df[df[col]].iloc[:, :9]

    async def group_data(self):
        data_by_group = {}
        data_by_journal = {}
        data_by_publisher = {}
        data_by_faculty = {}

        async for i in self.mongoclient.mongoclient.data_export.find(projection={'_id':0}):
            data = {
                'publishers': {p:1 for p in i['publishers']} if i['publishers'] else {},
                'journals': {j:1 for j in i['journals']} if i['journals'] else {},
                'groups': {g:1 for g in i['groups']} if i['groups'] else {},
                'faculties': {f:1 for f in i['faculties']} if i['faculties'] else {},
                'authors': {a:1 for a in i['authors']} if i['authors'] else {},
            }
            if data.get('publishers'):
                replace_dict = {}
                pubdata = data['publishers'].copy()
                for k,v in pubdata.items():
                    if 'elsevier' in k.lower():
                        replace_dict['Elsevier'] = 1
                        del data['publishers'][k]
                    if ('springer' in k.lower() and 'nature' not in k.lower()):
                        replace_dict['Springer'] = 1
                        del data['publishers'][k]
                    if 'wiley' in k.lower():
                        replace_dict['Wiley'] = 1
                        del data['publishers'][k]
                    if 'gruyter' in k.lower():
                        replace_dict['de Gruyter'] = 1
                        del data['publishers'][k]
                    if 'ieee' in k.lower():
                        replace_dict['IEEE'] = 1
                        del data['publishers'][k]
                    if 'Multidisciplinary Digital Publishing Institute' in k or 'MDPI' in k:
                        replace_dict['MDPI'] = 1
                        del data['publishers'][k]
                    if 'F1000' in k or 'Faculty of 1000' in k:
                        replace_dict['F1000'] = 1
                        del data['publishers'][k]
                    if 'sage' in k.lower():
                        replace_dict['Sage'] = 1
                        del data['publishers'][k]
                    if 'frontiers' in k.lower():
                        replace_dict['Frontiers'] = v
                        del data['publishers'][k]
                for k,v in replace_dict.items():
                    data['publishers'][k] = v

            if i['publishers']:
                for publisher in i['publishers']:
                    if publisher:
                        if publisher not in data_by_publisher:
                            data_by_publisher[publisher] = data
                        else:
                            for itemtype, datadict in data.items():
                                if len(datadict.keys()) > 0:
                                    for k, v in datadict.items():
                                        if k in data_by_publisher[publisher][itemtype]:
                                            data_by_publisher[publisher][itemtype][k] += v
                                        else:
                                            data_by_publisher[publisher][itemtype][k] = v

            if i['journals']:
                for journal in i['journals']:
                    if journal:
                        if journal not in data_by_journal:
                            data_by_journal[journal] = data
                        else:
                            for itemtype, datadict in data.items():
                                if len(datadict.keys()) > 0:
                                    for k, v in datadict.items():
                                        if k in data_by_journal[journal][itemtype]:
                                            data_by_journal[journal][itemtype][k] += v
                                        else:
                                            data_by_journal[journal][itemtype][k] = v
            if i['groups']:
                for group in i['groups']:
                    if group:
                        if group not in data_by_group:
                            data_by_group[group] = data
                        else:
                            for itemtype, datadict in data.items():
                                if len(datadict.keys()) > 0:
                                    for k, v in datadict.items():
                                        if k in data_by_group[group][itemtype]:
                                            data_by_group[group][itemtype][k] += v
                                        else:
                                            data_by_group[group][itemtype][k] = v
            if i['faculties']:
                for faculty in i['faculties']:
                    if faculty:
                        if faculty not in data_by_faculty:
                            data_by_faculty[faculty] = data
                        else:
                            for itemtype, datadict in data.items():
                                if len(datadict.keys()) > 0:
                                    for k, v in datadict.items():
                                        if k in data_by_faculty[faculty][itemtype]:
                                            data_by_faculty[faculty][itemtype][k] += v
                                        else:
                                            data_by_faculty[faculty][itemtype][k] = v

        for faculty, data in data_by_publisher.items():
            co.print(f'{faculty}')
            publishers = [(k,v) for k, v in sorted(data['publishers'].items(), key=lambda item: item[1], reverse=True)]
            journals = [(k,v) for k, v in sorted(data['journals'].items(), key=lambda item: item[1], reverse=True)]
            groups = [(k,v) for k, v in sorted(data['groups'].items(), key=lambda item: item[1], reverse=True)]
            authors = [(k,v) for k, v in sorted(data['authors'].items(), key=lambda item: item[1], reverse=True)]

            co.print(f'top 5 of {len(publishers)} publishers')
            for i in range(0,5):
                try:
                    co.print(f'{i+1}. {publishers[i]}')
                except Exception as e:
                    ...
            co.print(f'top 5 of {len(journals)} journals')
            for i in range(0,5):
                try:
                    co.print(f'{i+1}. {journals[i]}')
                except Exception as e:
                    ...
            co.print(f'top 5 of {len(groups)} groups')
            for i in range(0,5):
                try:
                    co.print(f'{i+1}. {groups[i]}')
                except Exception as e:
                    ...
            co.print(f'top 5 of {len(authors)} authors')
            for i in range(0,5):
                try:
                    co.print(f'{i+1}. {authors[i]}')
                except Exception as e:
                    ...

    async def clean_publisher_names(self):
        import re
        async def update_publisher_names(collection_name):
            collection = self.mongoclient.mongoclient[collection_name]

            for pattern, replacement in publishers_to_update.items():
                # Create a case-insensitive regex pattern
                regex = re.compile(pattern, re.IGNORECASE)

                # Update documents where 'publisher' matches the regex
                result = await collection.update_many(
                    {'publisher': regex},
                    {'$set': {'publisher': replacement}}
                )

                co.print(f"Updated {result.modified_count} documents in {collection_name} for {replacement}")

        collections = ['data_export_rich', 'data_export_refs']

        # Dictionary of publisher names to standardize
        # Key: regex pattern to match, Value: standardized name
        publishers_to_update = {
            r'elsevier': 'Elsevier',
            r'springer': 'Springer',
            r'wiley': 'Wiley',
            r'gruyter': 'de Gruyter',
            r'ieee': 'IEEE',
            r'electrical and electronics engineers': 'IEEE',
            r'multidisciplinary digital publishing institute': 'MDPI',
            r'mdpi': 'MDPI',
            r'f1000': 'F1000',
            r'faculty of 1000': 'F1000',
            r'sage': 'Sage',
            r'frontiers': 'Frontiers',
            r'acm': 'ACM',
            r'association for computing machinery': 'ACM',
            r'optical society': 'The Optical Society',
            r'optica publishing group': 'Optica Publishing Group',
            r'formerly osa': 'Optica Publishing Group',
        }


        # Run the update for each collection
        for collection_name in collections:
            await update_publisher_names(collection_name)

    async def get_grouplist(self):
        item = await self.mongoclient.mongoclient.data_export_rich.find_one()
        return list(item.keys())[16:]


    async def export_csvs(self, group: str = 'All', output: str = 'excel'):

        '''
        exports csvs with aggregated publisher and journal data for a given group (faculty or department).
        Optional filters using parameters:
        itemtype [str]: journal-article, book-chapter, book, conference-proceeding, other
        year [list[int]]: list of years to filter by
        is_oa [str]: Return only oa works or only non-oa works. If empty, returns all works. Use a 'True' or 'False' string -- not a true/false bool!
        group [str]: Use TNW, EEMCS, BMS, ET, ITC to get data for faculties, or the full name of a department. If empty, all data is returned.

        '''
        itemtype = ['journal-article', 'conference-proceeding']
        pipeline = []
        if itemtype:
            pipeline.append({"$match": {"type": {'$in': itemtype}}})
        if group != 'All':
            pipeline.append({"$match": {group: True}})
        pipeline_journal = pipeline.copy()
        pipeline_publisher = pipeline.copy()
        pipeline_journal.extend([
            {"$group": {"_id": "$journal", "count": {"$sum": 1}}},
            {"$sort": SON([("count", -1), ("journal", -1)])},
            ])
        pipeline_publisher.extend([
            {"$group": {"_id": "$publisher", "count": {"$sum": 1}}},
            {"$sort": SON([("count", -1), ("publisher", -1)])},
            ])


        journals_pub = pd.DataFrame.from_records([item async for item in self.mongoclient.mongoclient.data_export_rich.aggregate(pipeline_journal)])
        journals_ref = pd.DataFrame.from_records([item async for item in self.mongoclient.mongoclient.data_export_refs.aggregate(pipeline_journal)])
        publishers_pub = pd.DataFrame.from_records([item async for item in self.mongoclient.mongoclient.data_export_rich.aggregate(pipeline_publisher)])
        publishers_ref = pd.DataFrame.from_records([item async for item in self.mongoclient.mongoclient.data_export_refs.aggregate(pipeline_publisher)])

        # dropna from all dataframes
        journals_pub.dropna(inplace=True)
        journals_ref.dropna(inplace=True)
        publishers_pub.dropna(inplace=True)
        publishers_ref.dropna(inplace=True)

        # rename columns
        journals_pub.rename(columns={'_id': 'Journal'}, inplace=True)
        journals_ref.rename(columns={'_id': 'Journal'}, inplace=True)
        publishers_pub.rename(columns={'_id': 'Publisher'}, inplace=True)
        publishers_ref.rename(columns={'_id': 'Publisher'}, inplace=True)

        if output == 'csv':
            journalspubpath = os.path.join(os.getcwd(), 'library_csv_output', f'{group}_journals_pub.csv')
            journalsrefpath = os.path.join(os.getcwd(), 'library_csv_output', f'{group}_journals_ref.csv')
            publisherspubpath = os.path.join(os.getcwd(), 'library_csv_output', f'{group}_publishers_pub.csv')
            publishersrefpath = os.path.join(os.getcwd(), 'library_csv_output', f'{group}_publishers_ref.csv')

            journals_pub.to_csv(journalspubpath, index=False)
            journals_ref.to_csv(journalsrefpath, index=False)
            publishers_pub.to_csv(publisherspubpath, index=False)
            publishers_ref.to_csv(publishersrefpath, index=False)
        elif output == 'excel':
            filepath = os.path.join(os.getcwd(), 'library_xlsx_output', f'{group}.xlsx')
            # Create an new Excel file and add a worksheet.
            writer = pd.ExcelWriter(filepath, engine="xlsxwriter")
            journals_pub.to_excel(writer, sheet_name='Journals (published)', index=False)
            journals_ref.to_excel(writer, sheet_name='Journals (referenced)', index=False)
            publishers_pub.to_excel(writer, sheet_name='Publishers (published)', index=False)
            publishers_ref.to_excel(writer, sheet_name='Publishers (referenced)', index=False)
            writer.close()

    async def get_oclc_token(self):
        try:
            self.key
        except AttributeError:
            self.key: str = None
        try:
            self.secret
        except AttributeError:
            self.secret: str = None
        if not self.key:
            self.key: str = os.environ.get('WORLDCAT_KEY')
        if not self.secret:
            self.secret: str =  os.environ.get('WORLDCAT_SECRET')

        client = httpx.AsyncClient()
        url = 'https://oauth.oclc.org/token'
        payload = {'grant_type': 'client_credentials',
                    'scope':'wcapi:view_holdings wcapi:view_bib wcapi:view_brief_bib wcapi:view_retained_holdings wcapi:view_summary_holdings wcapi:view_my_holdings wcapi:view_institution_holdings'


        }
        headers = {
            "Accept": "application/json"
        }
        auth = (self.key, self.secret)

        response = await client.post(url, data=payload, auth=auth, headers=headers)
        print(response.json())
        return response.json()['access_token']
        
    async def get_worldcat_data(self, client: httpx.AsyncClient, issns:list, token:str=None, raw=False):
        # get worldcat data for each issn in issns
        # return a tuple of issn and a dict of worldcat data
        # parameters:
        # client: httpx.AsyncClient
        # issns: list of issns
        # token: oclc token (use get_oclc_token)
        if not token:
            token = await self.get_oclc_token()
        headers = {'Authorization': f'Bearer {token}',
            'accept': 'application/json'}
        if not isinstance(issns, list):
            issns = [issns]
        results = []
        for i in issns:
            q=f'in:{i}'
            url = f'https://americas.discovery.api.oclc.org/worldcat/search/v2/bibs?q={q}&heldBySymbol=QHU&showHoldingsIndicators=true'
            holdings_url = f'https://americas.discovery.api.oclc.org/worldcat/search/v2/bibs-holdings?issn={q}&heldBySymbol=QHU'
            try:
                result = await client.get(holdings_url, headers=headers)
            except Exception as e:
                co.print(f"Error retrieving record: {e}")
                co.print(result)
                return
            data = result.json()
            if raw:
                results.append((i, data))
                continue
            itemdict = {}
            itemdict['in_collection'] = False
            stop = False
            if data.get('numberOfRecords'):
                if data.get('numberOfRecords') > 0:
                    found_item = data.get('briefRecords')[0]
                    itemdict['oclc_title'] = found_item.get('title')
                    itemdict['oclc_creator']= found_item.get('creator')
                    itemdict['oclc_number'] = found_item.get('oclcNumber')
                    itemdict['oclc_publisher'] = found_item.get('publisher')
                    itemdict['oclc_issns'] = found_item.get('issns')
                    itemdict['oclc_merged_numbers'] = found_item.get('mergedOclcNumbers')
                    itemdict['in_collection'] = False
                    if found_item.get('institutionHolding'):
                        if found_item.get('institutionHolding').get('totalHoldingCount') >= 1:
                            for holding in found_item.get('institutionHolding').get('briefHoldings'):
                                if holding.get('oclcSymbol') == 'QHU':
                                    itemdict['in_collection'] = True
                if data.get('numberOfRecords') > 1:
                    for found_item in data.get('briefRecords'):
                        if stop:
                            break
                        if found_item.get('institutionHolding'):
                            if found_item.get('institutionHolding').get('totalHoldingCount') >= 1:
                                for holding in found_item.get('institutionHolding').get('briefHoldings'):
                                    if holding.get('oclcSymbol') == 'QHU':
                                        itemdict['in_collection'] = True
                                        itemdict['oclc_title'] = found_item.get('title')
                                        itemdict['oclc_creator']= found_item.get('creator')
                                        itemdict['oclc_number'] = found_item.get('oclcNumber')
                                        itemdict['oclc_publisher'] = found_item.get('publisher')
                                        itemdict['oclc_issns'] = found_item.get('issns')
                                        itemdict['oclc_merged_numbers'] = found_item.get('mergedOclcNumbers')
                                        stop = True
                                        break
                results.append((i, itemdict)) 
        return results
    async def add_oclc_data(self):
        # use the worldcat api to get oclc data for each item in the mongodb collection
        # search worldcat ut holdings for the issns in the item
        #  each will return a list of results (?) -- see how to determine if journal is in collection or not
        # put true/false in the 'in_collection' column of the mongodb item if the journal is in the UT holding

        issns_ref = await self.mongoclient.mongoclient['data_refs'].distinct('issn', {'issn':{'$exists':True}})
        issns_rich = await self.mongoclient.mongoclient['data_export_rich'].distinct('issn', {'issn':{'$exists':True}})
        issns = list(set(issns_ref).union(set(issns_rich)))

        co.print(f'Retrieving {len(issns)} issns from worldcat in batches of 100')
        numdone = 0
        token = await self.get_oclc_token()

        async with httpx.AsyncClient() as client:
            for batch in batched(issns, 100):
                numdone += len(batch)
                jobs = [functools.partial(self.get_worldcat_data, client, issn, token) for issn in batch]
                results = await aiometer.run_all(jobs, max_at_once=50, max_per_second=10)
                co.print(f'Inserting data for {len(results)} issns into mongodb')
                updates = []
                for result in results:
                    if not result:
                        continue
                    issn, data = result
                    updates.append(UpdateMany({'issns':issn}, {'$set':data}))

                co.print(f'Running bulk write for {len(updates)} updates in both data_refs and data_export_rich')
                writeresult = await self.mongoclient.mongoclient['data_refs'].bulk_write(updates)
                co.print(f'Updated {writeresult.bulk_api_result} mongodb items in data_refs.')
                writeresult = await self.mongoclient.mongoclient['data_export_rich'].bulk_write(updates)
                co.print(f'Updated {writeresult.bulk_api_result} mongodb items in data_export_rich.')

                co.print(f'{numdone} of {len(issns) - numdone} done.')

    async def check_is_in_collection(self):
        # for each item in collection that has 'false' in column 'in_collection', 
        # retrieve worldcat data for the issns in that entry
        # keep multiple issns together
        # then manually look through to select the best match
        checklist = []
        issnset = set()
        async for item in self.mongoclient.mongoclient['data_export_rich'].find({'in_collection':False}):
            if not item.get('issns'):
                continue
            for issn in item.get('issns'):
                if issn in issnset:
                    continue
                issnset.add(issn)
                itemdict = {
                'issns': item.get('issns'),
                'journal': item.get('journal'),
                'publisher': item.get('publisher'),
                'in_collection': item.get('in_collection'),
                'oclc_publisher': item.get('oclc_publisher'),
                'oclc_title': item.get('oclc_title'),
                'oclc_issns': item.get('oclc_issns'),
                }
                checklist.append(itemdict)
        co.print('Got data from data_export_rich')
        async for item in self.mongoclient.mongoclient['data_refs'].find({'in_collection':False}):
            if not item.get('issns'):
                continue
            for issn in item.get('issns'):
                if issn in issnset:
                    continue
                issnset.add(issn)
                itemdict = {
                'issns': item.get('issns'),
                'journal': item.get('journal'),
                'publisher': item.get('publisher'),
                'in_collection': item.get('in_collection'),
                'oclc_publisher': item.get('oclc_publisher'),
                'oclc_title': item.get('oclc_title'),
                'oclc_issns': item.get('oclc_issns'),
                }
                checklist.append(itemdict)
        co.print('Got data from data_refs')

        co.print(f'checking {len(checklist)} journals in worldcat')
        token = await self.get_oclc_token()
        updates = []

        async with httpx.AsyncClient() as client:
            for item in checklist:
                try:
                    jobs = [functools.partial(self.get_worldcat_data, client, issn, token) for issn in item.get('issns')]
                    results = await aiometer.run_all(jobs, max_at_once=50, max_per_second=10)
                    co.print(f'got {len(results)} results for {len(item.get("issns"))} issns')
                    multiple_results = False
                    if results:
                        if len(results) > 1:
                            for i, result in enumerate(results):
                                if not result:
                                    continue
                                issn, data = result
                                if i == 0:
                                    issn = issn
                                    picked = data
                                    if data.get('oclc_issns'):
                                        oclc_issns:list = data.get('oclc_issns')
                                        picked['oclc_issns'] = sorted(oclc_issns)
                                else:
                                    if data.get('oclc_issns'):
                                        oclc_issns:list = data.get('oclc_issns')
                                        data['oclc_issns'] = sorted(oclc_issns)
                                    if (data==picked):
                                        continue
                                    else:
                                        multiple_results = True
                                        break

                    if not multiple_results and len(results) > 0:
                        issn, data = results[0]
                        if data.get('in_collection'):
                            if data.get('in_collection') == True:
                                co.print(f'Got only 1 result for {item.get("journal")}. Adding to updatelist.')
                                co.print(f'issn: {issn}')
                                co.print(f'in_collection?: {data.get("in_collection")}')
                                updates.append(UpdateMany({'issns':issn}, {'$set':data}))
                        continue

                    table = Table(show_header=True, header_style="bold magenta", title=f'results for {item.get("journal")}')
                    table.add_column('#', justify='center', style="bold red")
                    table.add_column('issn', justify='left', style="cyan")
                    table.add_column('publisher', justify='left', style="cyan")
                    table.add_column('in_collection', justify='right', style="yellow")
                    table.add_column('oclc_publisher', justify='right', style="yellow")
                    table.add_column('oclc_title', justify='right', style="yellow")
                    table.add_column('oclc_issns', justify='right', style="yellow")
                    incollection = False
                    multiple_in_collection = False
                    issn = None
                    data = None
                    picked = None
                    for i, result in enumerate(results):
                        if not result:
                            continue
                        issn, data = result
                        if data.get('in_collection'):
                            if data.get('in_collection') == True:
                                if not incollection:
                                    issn = issn
                                    picked = data
                                    incollection = True
                                else:
                                    multiple_in_collection = True
                                    co.print('Multiple items in collection for this item.')
                        table.add_row(str(i+1), str(issn), str(item.get('publisher')), str(data.get('in_collection')), str(data.get('oclc_publisher')), str(data.get('oclc_title')), str(data.get('oclc_issns')))
                    if incollection and not multiple_in_collection:
                        co.print(f'Auto-selected entry for {item.get("journal")}. Adding to updatelist.')
                        for result in results:
                            if result:
                                issn, data = result
                                if data.get('in_collection') == True:
                                    break
                        co.print(f'issn: {issn}')
                        co.print(f'in_collection?: {data.get("in_collection")}')
                    elif not picked:
                        choice = None
                        max_len = 0 
                        for i, k in enumerate(results):
                            issn, data = k
                            if data.get('oclc_issns'):
                                if len(data.get('oclc_issns')) > max_len:
                                    max_len = len(data.get('oclc_issns'))
                                    choice = i
                        if not choice:
                            issn, data = None, None
                            for k in results:
                                issn, data = k
                                if data.get('oclc_issns'):
                                    if len(data.get('oclc_issns')) > max_len:
                                        max_len = len(data.get('oclc_issns'))
                                        choice = i
                            
                            if not choice:
                                co.print(table)
                                co.print(f'[cyan]x[/cyan] skip | [cyan]e[/cyan] skip all & update | [cyan]q[/cyan] immediate quit | [cyan]1-{len(results)}[/cyan] select')
                                #choice = co.input(f'Which # do you want to use for {item.get("journal")}?')
                                #if choice == 'q':
                                #    return
                                #if choice == 'x':
                                #    continue
                                choice = 1
                                choice = int(choice)-1
                            if choice:
                                picked = results[int(choice)]
                        if not picked:
                            continue
                        issn, data = picked
                        co.print(f'picked {data.get("oclc_issns")} to match with {issn} for journal {item.get("journal")}')
                    if issn and data:
                        updates.append(UpdateMany({'issns':issn}, {'$set':data}))
                        co.print('added update to list')
                        co.print(f'{len(updates)} updates in list')
                    else:
                        co.print(f'No issn or data for {item.get("journal")} -- so no update.')
                except Exception as e:
                    co.print(f'Error in get_worldcat_data: {e}')
                    continue
        
        
            
            co.print(f'Running bulk write for {len(updates)} updates in both data_refs and data_export_rich')
            writeresult = await self.mongoclient.mongoclient['data_refs'].bulk_write(updates)
            co.print(f'Updated {writeresult.bulk_api_result} mongodb items in data_refs.')
            writeresult = await self.mongoclient.mongoclient['data_export_rich'].bulk_write(updates)
            co.print(f'Updated {writeresult.bulk_api_result} mongodb items in data_export_rich.')

    async def check_doaj(self):
        async def get_doaj_data(client: httpx.AsyncClient, issn):
            if not isinstance(issn, list):
                issn = [issn]
            result = []
            for iss in issn:
                url = f'https://doaj.org/api/search/journals/issn:{iss}'
                headers = {'accept': 'application/json'}
                response = await client.get(url, headers=headers)
                data = response.json()
                if data.get('results'):
                    if len(data.get('results')) > 0:
                        for item in data.get('results'):
                            if item.get('bibjson'):
                                result.append((iss, item.get('bibjson')))
            return result
        async def get_core_data(client: httpx.AsyncClient, issn):
            if not isinstance(issn, list):
                issn = [issn]
            result = []
            for iss in issn:
                url = f'https://api.core.ac.uk/v3/journals/issn:{iss}'
                headers = {'accept': 'application/json'}
                response = await client.get(url, headers=headers)
                if response.status_code != 200:
                    continue
                data = response.json()
                if data:
                    data['publisher_core'] = data.get('publisher')
                    del data['publisher']
                    data['title_core'] = data.get('title')
                    del data['title']
                    result.append((iss, data))
            return result
        issnlist = set()
        co.print(f'looking up issns in the DOAJ api')
        async for item in self.mongoclient.mongoclient['data_export_rich'].find({'in_collection':False}):
            if not item.get('issns'):
                continue
            for issn in item.get('issns'):
                if issn in issnlist:
                    continue
                issnlist.add(issn)
        async for item in self.mongoclient.mongoclient['data_refs'].find({'in_collection':False}):
            if not item.get('issns'):
                continue
            for issn in item.get('issns'):
                if issn in issnlist:
                    continue
                issnlist.add(issn)
        co.print(f'got {len(issnlist)} items to process')
        client = httpx.AsyncClient()
        updates = []

        for batch in batched(issnlist, 10):
            batch = list(batch)
            jobs = [functools.partial(get_doaj_data, client, i) for i in batch]
            jobs2 = [functools.partial(get_core_data, client, i) for i in batch]
            results1 = await aiometer.run_all(jobs, max_at_once=6, max_per_second=3)
            results2 = await aiometer.run_all(jobs2, max_at_once=6, max_per_second=3)

            for results in [results1, results2]:
                print(f'data for {len(results)} issns retrieved')
                for result in results:
                    for item in result:
                        if item:
                            co.print(item)
                            try:
                                id = item[0]
                                data = item[1]
                            except Exception as e:
                                co.print(f'Error: {e}')
                                continue
                            if not data:
                                continue
                            else:
                                data['in_doaj'] = True
                                if 'publisher' in data:
                                    data['doaj_publisher'] = data['publisher']
                                    del data['publisher']
                                if 'id' in data:
                                    del data['id']
                                updates.append(UpdateMany({'issns':id}, {'$set':data}))
                
        co.print(f'Running bulk write for {len(updates)} updates in both data_refs and data_export_rich')
        writeresult = await self.mongoclient.mongoclient['data_refs'].bulk_write(updates)
        co.print(f'Updated {writeresult.bulk_api_result} mongodb items in data_refs.')
        writeresult = await self.mongoclient.mongoclient['data_export_rich'].bulk_write(updates)
        co.print(f'Updated {writeresult.bulk_api_result} mongodb items in data_export_rich.')
    async def add_issn_data(self):

        async def get_issn_data(client: httpx.AsyncClient, id:str):
            queryids = []
            result = []
            for i in id:
                if i.startswith('https://openalex.org/'):
                    queryids.append(i.split('https://openalex.org/')[1])
            queryid = '|'.join(queryids)
            url=f'https://api.openalex.org/works?filter=openalex_id:{queryid}&select=id,primary_location&per-page=50'
            headers= {'From':'s.mok@utwente.nl'}
            response = await client.get(url, headers=headers)
            data = response.json()
            for item in data.get('results'):
                tmpdata = {'issns':set(), 'journal':'', 'publisher':'', 'publisher_lineage':''}
                if item.get('primary_location'):
                    if item['primary_location'].get('source'):
                        tmpdata['journal'] = item['primary_location']['source'].get('display_name')
                        tmpdata['publisher'] = item['primary_location']['source'].get('host_organization_name')
                        tmpdata['publisher_lineage'] = item['primary_location']['source'].get('host_organization_lineage')
                        if item['primary_location']['source'].get('issn_l'):
                            tmpdata['issns'].add(item['primary_location']['source']['issn_l'])
                        if item['primary_location']['source'].get('issn'):
                            issn = item['primary_location']['source'].get('issn')
                            if isinstance(issn, list):
                                for i in issn:
                                    if i:
                                        tmpdata['issns'].add(i)
                            elif issn:
                                    tmpdata['issns'].add(i)
                    tmpdata['issns'] = list(tmpdata['issns'])
                    result.append((item.get('id'), tmpdata))
            return result
        idlist = []
        faillist = []
        for collectionname in ['data_export_rich', 'data_export_refs']:
            co.print(f'Getting issn data for {collectionname}')

            co.print(await self.mongoclient.mongoclient[collectionname].estimated_document_count())

            distinct_ids = await self.mongoclient.mongoclient[collectionname].distinct('openalex_id', {'openalex_id': {'$exists': True, '$ne': None}})
            for id in distinct_ids:
                idlist.append(id)

            co.print(f'got {len(idlist)} items to process. Processing in batches of 500')
            client = httpx.AsyncClient()
            for batch in batched(idlist, 500):
                print(len(batch))
                jobs = [functools.partial(get_issn_data, client, ids) for ids in batched(batch,50)]
                results = await aiometer.run_all(jobs, max_at_once=5, max_per_second=5)
                updates = []
                print(f'data for {sum([len(i) for i in results])} openalexids retrieved')
                for result in results:
                    if result:
                        for item in result:
                            if item:
                                id = item[0]
                                data = item[1]
                                if not data or not data.get('issns') or not data.get('journal') or not data.get('publisher'):
                                    faillist.append(id)
                                    continue
                                else:
                                    updates.append(UpdateMany({'openalex_id':id}, {'$set':data}))

                co.print(f'Updating issns for {len(updates)} openalexids.')
                result = await self.mongoclient.mongoclient[collectionname].bulk_write(updates)
                co.print(f'Updated {result.bulk_api_result} mongodb items. Moving to next batch.')
            co.print(f'failed for {len(faillist)} items')
            for id in faillist:
                co.print(id)

    async def add_refs_data(self):
        async def get_refs(client: httpx.AsyncClient, id:str):
            queryids = []
            result = []
            for i in id:
                if i.startswith('https://openalex.org/'):
                    queryids.append(i.split('https://openalex.org/')[1])
            queryid = '|'.join(queryids)
            url=f'https://api.openalex.org/works?filter=openalex_id:{queryid}&select=id,referenced_works&per-page=50'
            headers= {'From':'s.mok@utwente.nl'}
            response = await client.get(url, headers=headers)
            data = response.json()
            for item in data.get('results'):
                tmpdata = []
                if item.get('referenced_works'):
                    for ref in item['referenced_works']:
                        tmpdata.append(ref)
                    result.append((item.get('id'), tmpdata))
            return result
        idlist = {}
        async for item in self.mongoclient.mongoclient['data_export_rich'].find({'openalex_id':{'$exists':True}}, projection={'_id':0, 'openalex_id':1, 'EEMCS':1, 'TNW':1, 'BMS':1, 'ET':1, 'ITC':1}):
            if item.get('openalex_id'):
                idlist[item.get('openalex_id')]={'EEMCS':item.get('EEMCS'), 'TNW':item.get('TNW'), 'BMS':item.get('BMS'), 'ET':item.get('ET'), 'ITC':item.get('ITC')}

        co.print(f'Looking up references for {len(idlist)} items. Processing in batches of 500')
        client = httpx.AsyncClient()
        for batch in batched(list(idlist.keys()), 500):
            jobs = [functools.partial(get_refs, client, ids) for ids in batched(batch,50)]
            results = await aiometer.run_all(jobs, max_at_once=5, max_per_second=5)
            updates = []
            print(f'data for {sum([len(i) for i in results])} openalexids retrieved')
            for result in results:
                if result:
                    for item in result:
                        if item:
                            id = item[0]
                            data = idlist[id]
                            data['list_of_refs'] = item[1]
                            if not data:
                                continue
                            else:
                                updates.append(UpdateMany({'parent_work':id}, {'$set':data}, upsert=True))
            self.mongoclient.mongoclient['data_export_refs'].bulk_write(updates)
        numitems = await self.mongoclient.mongoclient['data_export_refs'].estimated_document_count()
        co.print(f'Updated {len(updates)} mongodb items. Items in data_export_refs collection: {numitems}')
        self.mongoclient.mongoclient['data_export_refs'].create_index([('list_of_refs', 1)])
        self.mongoclient.mongoclient['data_export_refs'].create_index([('parent_work', 1)])
        self.mongoclient.mongoclient['data_refs'].create_index([('openalex_id', 1)])
        self.mongoclient.mongoclient['data_refs'].create_index([('primary_topic', 1)])
        self.mongoclient.mongoclient['data_refs'].create_index([('subfield', 1)])
        self.mongoclient.mongoclient['data_refs'].create_index([('field', 1)])
        self.mongoclient.mongoclient['data_refs'].create_index([('domain', 1)])
        self.mongoclient.mongoclient['data_refs'].create_index([('title', 1)])
        self.mongoclient.mongoclient['data_refs'].create_index([('doi', 1)])
        self.mongoclient.mongoclient['data_refs'].create_index([('year', 1)])
        self.mongoclient.mongoclient['data_refs'].create_index([('type', 1)])
        self.mongoclient.mongoclient['data_refs'].create_index([('issns', 1)])
        self.mongoclient.mongoclient['data_refs'].create_index([('journal', 1)])
        self.mongoclient.mongoclient['data_refs'].create_index([('publisher', 1)])
        self.mongoclient.mongoclient['data_refs'].create_index([('publisher_lineage', 1)])
        co.print('now retrieving data for all items in data_export_refs and adding to data_refs')
        i=0

    async def get_work_data(self, client: httpx.AsyncClient, id:str):
        queryids = []
        result = []
        for i in id:
            if i.startswith('https://openalex.org/'):
                queryids.append(i.split('https://openalex.org/')[1])
        queryid = '|'.join(queryids)
        url=f'https://api.openalex.org/works?filter=openalex_id:{queryid}&select=id,display_name,doi,publication_year,type_crossref,primary_location,open_access,primary_topic&per-page=50'
        headers= {'From':'s.mok@utwente.nl'}
        response = await client.get(url, headers=headers)
        data = response.json()
        for item in data.get('results'):
            if not item:
                continue
            if not item.get('id'):
                continue
            if not item.get('type_crossref'):
                continue
            if not item.get('primary_location'):
                continue

            tmpdata = {'openalex_id':item.get('id'),
                        'title':item.get('display_name'),
                        'doi':item.get('doi'),
                        'year':item.get('publication_year'), 
                        'type':item.get('type_crossref'), 
                        'open_access_type':item.get('open_access').get('oa_status'),
                        'is_oa':item.get('open_access').get('is_oa'),
                        'also_green':item.get('open_access').get('any_repository_has_fulltext'),
            }
            if item.get('primary_topic'):
                tmpdata['primary_topic'] = item.get('primary_topic').get('display_name')
                tmpdata['subfield'] = item.get('primary_topic').get('subfield').get('display_name')
                tmpdata['field'] = item.get('primary_topic').get('field').get('display_name')
                tmpdata['domain'] = item.get('primary_topic').get('domain').get('display_name')
            if item.get('primary_location'):
                if item['primary_location'].get('source'):
                    tmpdata['issns'] = set()
                    tmpdata['journal'] = item['primary_location']['source'].get('display_name')
                    tmpdata['publisher'] = item['primary_location']['source'].get('host_organization_name')
                    tmpdata['publisher_lineage'] = item['primary_location']['source'].get('host_organization_lineage')
                    if item['primary_location']['source'].get('issn_l'):
                        tmpdata['issns'].add(item['primary_location']['source']['issn_l'])
                    if item['primary_location']['source'].get('issn'):
                        issn = item['primary_location']['source'].get('issn')
                        if isinstance(issn, list):
                            for i in issn:
                                if i:
                                    tmpdata['issns'].add(i)
                        elif issn:
                                tmpdata['issns'].add(i)
                    tmpdata['issns'] = list(tmpdata['issns'])
            result.append((item.get('id'), tmpdata))
        return result
    
    async def get_refitems(self, refitems):
        datadict = {}
        lookup = []
        for refitem in refitems:
            lookup.extend(refitem.get('list_of_refs')) 
            for i in refitem.get('list_of_refs'):
                datadict[i] = refitem
        
        co.print(f'Looking up data for {len(lookup)} openalexids.')
        client = httpx.AsyncClient()
        jobs = [functools.partial(self.get_work_data_inner, client, ids) for ids in batched(lookup,50)]
        results = await aiometer.run_all(jobs, max_at_once=5, max_per_second=5)
        updates = []
        print(f'data for {sum([len(i) for i in results])} openalexids retrieved')
        for result in results:
            if result:
                for item in result:
                    if item:
                        id = item[0]
                        data = item[1]
                        refitem = datadict[id]
                        data['EEMCS'] = refitem.get('EEMCS')
                        data['TNW'] = refitem.get('TNW')
                        data['BMS'] = refitem.get('BMS')
                        data['ET'] = refitem.get('ET')
                        data['ITC'] = refitem.get('ITC')
                        data['parent_work'] = refitem.get('parent_work')
                        if not data:
                            continue
                        else:
                            updates.append(UpdateMany({'openalex_id':id}, {'$set':data}, upsert=True))
        if updates:
            result = await self.mongoclient.mongoclient['data_refs'].bulk_write(updates)
            co.print(f'Updated/added {len(updates)} mongodb items in data_refs.')
            co.print(f'Bulk write result: {result.bulk_api_result["nInserted"]=}, {result.bulk_api_result["nUpserted"]=}, {result.bulk_api_result["nMatched"]=}, {result.bulk_api_result["nModified"]=}')

    async def update_refitems_from_published_works(self):
        i = 0
        numitems = await self.mongoclient.mongoclient['data_export_refs'].estimated_document_count()
        batch = []
        numrefs = 0
        async for item in self.mongoclient.mongoclient['data_export_refs'].find():
                batch.append(item)
                numrefs += len(item.get('list_of_refs'))
                if numrefs > 500:
                    await self.get_refitems(batch)
                    batch = []
                    numrefs = 0
                i+=1
                if i % 25 == 0:
                    co.print(f'Retrieved {i} / {numitems} items')
        await self.get_refitems(batch)

    async def update_published_works(self):

        # get a list of all openalex_ids in data_export_rich

        pipeline = [
            {"$match": {"openalex_id": {"$exists": True}}},
            {"$group": {"_id": None, "openalex_ids": {"$addToSet": "$openalex_id"}}},
        ]
        openalexids = await self.mongoclient.mongoclient['data_export_rich'].aggregate(pipeline).to_list(length=None)
        openalexids = openalexids[0]['openalex_ids']
        co.print(f'Found {len(openalexids)} openalex ids in data_export_rich')
        client=httpx.AsyncClient()
        for idbatch in batched(openalexids,1000):
            jobs = [functools.partial(self.get_work_data, client, ids) for ids in batched(idbatch,50)]
            results = await aiometer.run_all(jobs, max_at_once=5, max_per_second=5)
            updates = []
            print(f'data for {sum([len(i) for i in results])} openalexids retrieved')
            for result in results:
                if result:
                    for item in result:
                        if item:
                            id = item[0]
                            data = item[1]
                            if not data:
                                continue

                            updates.append(UpdateMany({'openalex_id':id}, {'$set':data}, upsert=False))
            if updates:
                result = await self.mongoclient.mongoclient['data_export_rich'].bulk_write(updates)
                co.print(f'Updated/added {len(updates)} mongodb items in data_export_rich.')
                co.print(f'Bulk write result: {result.bulk_api_result["nInserted"]=}, {result.bulk_api_result["nUpserted"]=}, {result.bulk_api_result["nMatched"]=}, {result.bulk_api_result["nModified"]=}')

    async def get_publisher_lineage(self):
        async def get_publisher(client: httpx.AsyncClient, id:str):
            queryids = []
            result = []
            for i in id:
                if i.startswith('https://openalex.org/'):
                    queryids.append(i.split('https://openalex.org/')[1])
            queryid = '|'.join(queryids)

            url=f'https://api.openalex.org/publishers?filter=openalex_id:{queryid}&per-page=50'
            headers= {'From':'s.mok@utwente.nl'}
            response = await client.get(url, headers=headers)
            data = response.json()
            for item in data.get('results'):
                if not item:
                    continue
                if not item.get('id'):
                    continue
                if not item.get('display_name'):
                    continue
                item['openalex_id'] = item.get('id')
                del item['id']
                result.append((item.get('openalex_id'), item))
            return result


        pipeline = [
            # Filter for documents where publisher_lineage exists and has at least 2 items
            {"$match": {
                "publisher_lineage": {"$exists": True},
            }},
            # Unwind the publisher_lineage array
            {"$unwind": "$publisher_lineage"},
            # Group to get distinct values
            {"$group": {"_id": None, "distinct_values": {"$addToSet": "$publisher_lineage"}}},
        ]


        
        publishers_refs = await self.mongoclient.mongoclient['data_refs'].aggregate(pipeline).to_list(length=None)
        publishers_refs = publishers_refs[0]['distinct_values']
        publishers_rich = await self.mongoclient.mongoclient['data_export_rich'].aggregate(pipeline).to_list(length=None)
        publishers_rich = publishers_rich[0]['distinct_values']

        merged_publishers = list(set(publishers_refs).union(publishers_rich))
        co.print(f'Looking up publisher data for {len(merged_publishers)} openalexids.')
        client = httpx.AsyncClient()
        jobs = [functools.partial(get_publisher, client, ids) for ids in batched(merged_publishers,50)]
        results = await aiometer.run_all(jobs, max_at_once=5, max_per_second=5)
        updates = []
        print(f'data for {sum([len(i) for i in results])} openalexids retrieved')
        for result in results:
            if result:
                for item in result:
                    if item:
                        id = item[0]
                        data = item[1]
                        if not data:
                            continue
                        else:
                            updates.append(UpdateMany({'openalex_id':id}, {'$set':data}, upsert=True))
        if updates:
            result = await self.mongoclient.mongoclient['data_publishers'].bulk_write(updates)
            co.print(f'Updated/added {len(updates)} mongodb items in data_refs.')
            co.print(f'Bulk write result: {result.bulk_api_result["nInserted"]=}, {result.bulk_api_result["nUpserted"]=}, {result.bulk_api_result["nMatched"]=}, {result.bulk_api_result["nModified"]=}')

        publisher_data = await self.mongoclient.mongoclient['data_publishers'].find({},projection={'_id':0, 'openalex_id':1, 'display_name':1, 'hierarchy_level':1}).to_list(length=None)
        publisher_data = {item['openalex_id']:item for item in publisher_data}
        co.print(f'Found {len(publisher_data)} publishers in data_publishers')
        co.print(f'Now updating items in data_refs and data_export_rich for {len(merged_publishers)} publishers')
        updates = []
        for publisherid in merged_publishers:
                data = publisher_data.get(publisherid)
                if data:
                    if data.get('hierarchy_level') == 0:
                        update_data = {}
                        update_data['main_publisher'] = data['display_name']
                        update_data['main_publisher_id'] = data['openalex_id']
                        updates.append(UpdateMany({'publisher_lineage':publisherid}, {'$set':update_data}, upsert=False))
        co.print(f'{len(updates)}')
        if updates:
            co.print(f'{len(updates)} update commands ready to send to data_refs and data_export_rich')
            result = await self.mongoclient.mongoclient['data_refs'].bulk_write(updates)
            co.print(f'Updated/added {len(updates)} mongodb items in data_refs.')
            co.print(f'Bulk write result: {result.bulk_api_result["nInserted"]=}, {result.bulk_api_result["nUpserted"]=}, {result.bulk_api_result["nMatched"]=}, {result.bulk_api_result["nModified"]=}')
            result2 = await self.mongoclient.mongoclient['data_export_rich'].bulk_write(updates)
            co.print(f'Updated/added {len(updates)} mongodb items in data_export_rich.')
            co.print(f'Bulk write result: {result2.bulk_api_result["nInserted"]=}, {result2.bulk_api_result["nUpserted"]=}, {result2.bulk_api_result["nMatched"]=}, {result2.bulk_api_result["nModified"]=}')




