
from mus_wizard.database.mongo_client import MusMongoClient
from mus_wizard.harvester.crossref import CrossrefAPI
from mus_wizard.harvester.openalex import OpenAlexAPI, OpenAlexQuery
from mus_wizard.harvester.openaire import OpenAIREAPI
from mus_wizard.harvester.oai_pmh import OAI_PMH
from mus_wizard.harvester.orcid import ORCIDAPI
from mus_wizard.database.matching import AuthorMatcher, WorkMatcher
from mus_wizard.constants import FACULTYNAMES, UTRESEARCHGROUPS_FLAT, ROR, APIEMAIL
import asyncio
from dataclasses import dataclass, field
from enum import Enum
from rich.console import Console
from rich.table import Table
from mus_wizard.utils import normalize_doi
from itertools import count
from typing import Literal
import pandas as pd
from pyalex import Works
import pyalex
from itertools import chain
from bson import SON
import os

# import module to create excel files
import xlsxwriter

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
    async def run(self, period = None):
        if period:
            self.period = period
        else:
            self.period = [2020, 2021, 2022, 2023, 2024]

        ut = Faculty(name='University of Twente', pure_id='491145c6-1c9b-4338-aedd-98315c166d7e')
        self.faculties[ut.pure_id] = ut

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
        grouplist = await self.get_grouplist()
        for group in grouplist:
            await self.export_csvs(group)

    async def harvest_pure(self):
        harvester = OAI_PMH(motorclient=self.mongoclient)
        await harvester.get_item_results()

    async def get_ut_works_openalex(self):
        # gets all ut-affiliated works from openalex
        # also retrieves all ut-affiliated authors for those works
        await OpenAlexAPI(years=self.period, openalex_requests={'works_openalex':None, 'authors_openalex':None}, mongoclient=self.mongoclient).run()

    async def make_groups(self):
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

        '''co.print(f'Now retrieving Openalex data for {len(orcid_searchlist)} ORCIDs and {len(scopus_searchlist)} Scopus IDs')
        orcids = [o.replace('\'','') for o in orcid_searchlist.keys()]
        queryc = OpenAlexQuery(self.mongoclient, self.mongoclient.authors_openalex, 'authors', years=self.period)
        queryc.add_query_by_orcid(orcids, single=False)
        await queryc.run()'''
        
        resulttable = Table(title='Author results')
        resulttable.add_column('value', justify='right')
        resulttable.add_column('count', justify='right')
        from_pure = len([a for a in self.flat_authors if a.pure_id])
        from_openalex = len([a for a in self.flat_authors if a.openalex_id])
        from_pure_aff = len([a for a in self.flat_authors if a.pure_id and a.groups])
        resulttable.add_row('# of authors total', str(len(self.flat_authors)))
        resulttable.add_row('Found in Pure', str(from_pure))
        resulttable.add_row('Found in Pure with affiliation', str(from_pure_aff))
        resulttable.add_row('Found in OpenAlex', str(from_openalex))
        resulttable.add_row('Pure <-> OpenAlex matches', str(len([a for a in self.flat_authors if a.openalex_id and a.pure_id])))
        resulttable.add_row('ORCIDS', str(len([a for a in self.flat_authors if a.orcid])))
        resulttable.add_row('Scopus IDs', str(len([a for a in self.flat_authors if a.scopus])))
        resulttable.add_row('Unmatched', str(len([a for a in self.flat_authors if not (a.openalex_id and a.pure_id)])))
        
        co.print(resulttable)
        
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
        # get work data from mongodb and put into self.works as Work objects
        async for work in self.mongoclient.works_openalex.find({},projection={'id':1, 'type_crossref':1, 'doi':1,'title':1,'publication_year':1,'authorships':1, 'primary_location':1}):
            if work.get('id') in self.works:
                continue

            await self.add_openalex_work(work)
        async for work in self.mongoclient.openaire_cris_publications.find():
            if work.get('internal_repository_id') in self.works:
                continue

            existing_work = None
            if work.get('doi'):
                doi = await normalize_doi(work.get('doi'))
                if doi and doi in self.works:
                    existing_work = self.works.get(doi)

            await self.add_pure_work(work, existing_work=existing_work)

        workresults = Table(title='Work results')
        workresults.add_column('value', justify='right')
        workresults.add_column('count', justify='right')
        from_pure = len([w for w in self.flat_works if w.pure_id])
        from_openalex = len([w for w in self.flat_works if w.openalex_id])
        matched = len([w for w in self.flat_works if w.pure_id and w.openalex_id])
        journal_articles = len([w for w in self.flat_works if w.type == WorkType.JOURNAL_ARTICLE])
        conference_proceedings = len([w for w in self.flat_works if w.type == WorkType.CONFERENCE_PROCEEDING])
        book_chapters = len([w for w in self.flat_works if w.type == WorkType.BOOK_CHAPTER])
        books = len([w for w in self.flat_works if w.type == WorkType.BOOK])
        publishers = len([w for w in self.publishers])
        journals = len([w for w in self.journals])
        without_authors = len([w for w in self.flat_works if not w.authors])
        at_least_1_author_has_group = len([w for w in self.flat_works if w.has_group_data()])
        avg_works_per_publisher = round(len(self.flat_works)/len(self.publishers_flat),0) if len(self.publishers_flat) > 0 else 0
        avg_works_per_journal = round(len(self.flat_works)/len(self.journals_flat),0) if len(self.journals_flat) > 0 else 0
        workresults.add_row('# of works total', str(len(self.flat_works)))
        workresults.add_row('Found in Pure', str(from_pure))
        workresults.add_row('Found in OpenAlex', str(from_openalex))
        workresults.add_row('Pure <-> OpenAlex matches', str(matched))
        workresults.add_row('Works without authors', str(without_authors))
        workresults.add_row('Works with at least 1 author with UT affil data', str(at_least_1_author_has_group))
        workresults.add_row('Journal articles', str(journal_articles))
        workresults.add_row('Conference proceedings', str(conference_proceedings))
        workresults.add_row('Book chapters', str(book_chapters))
        workresults.add_row('Books', str(books))
        workresults.add_row('Publishers', str(publishers))
        workresults.add_row('Journals', str(journals))
        workresults.add_row('Avg works per publisher', str(avg_works_per_publisher))
        workresults.add_row('Avg works per journal', str(avg_works_per_journal))
        co.print(workresults)
        await self.add_main_data()
    async def add_openalex_work(self, data: dict, existing_work: Work | None = None):
        if data.get('id') in self.works:
            return
        type_crossref = data.get('type_crossref')
        work_type = None
        match type_crossref:
            case 'journal-article':
                work_type = WorkType.JOURNAL_ARTICLE
            case 'report':
                work_type = WorkType.JOURNAL_ARTICLE
            case 'journal-volume':
                work_type = WorkType.JOURNAL_ARTICLE
            case 'journal-issue':
                work_type = WorkType.JOURNAL_ARTICLE
            case 'journal':
                work_type = WorkType.JOURNAL_ARTICLE
            case 'proceedings-article':
                work_type = WorkType.CONFERENCE_PROCEEDING
            case 'proceedings-series':
                work_type = WorkType.CONFERENCE_PROCEEDING
            case 'proceedings':
                work_type = WorkType.CONFERENCE_PROCEEDING
            case 'book-chapter':
                work_type = WorkType.BOOK_CHAPTER
            case 'book-series':
                work_type = WorkType.BOOK
            case 'edited-book':
                work_type = WorkType.BOOK
            case 'reference-book':
                work_type = WorkType.BOOK
            case 'book-set':
                work_type = WorkType.BOOK
            case 'book':
                work_type = WorkType.BOOK
            case 'book-part':
                work_type = WorkType.BOOK_CHAPTER
            case _:
                work_type = WorkType.OTHER
        
        authors = []
        for authorsh in data.get('authorships'):
            author = authorsh.get('author')
            if author:
                if author.get('id') in self.authors:
                    auth = self.authors[author.get('id')]
                    if len(auth.groups) > 0:
                        authors.append(auth)
                else:
                    if authorsh.get('institutions'):
                        for institution in authorsh.get('institutions'):
                            if institution.get('ror') == ROR:
                                self.missing_authors.append(author)
        journal = None
        publisher = None
        if data.get('primary_location'):
            source = data.get('primary_location').get('source')
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

        if not existing_work:
            work = Work(data_sources=[DataSource.OPENALEX],
                        openalex_id=data.get('id'), 
                        authors=authors, 
                        doi=await normalize_doi(data.get('doi')), 
                        title=data.get('title'), 
                        year=data.get('publication_year'), 
                        type=work_type,
                        journals=[journal],
                        publishers=[publisher],)
            
        else:
            work = existing_work
            work.data_sources.append(DataSource.OPENALEX)
            work.openalex_id = data.get('id')
            if authors:
                if len(work.authors)>0:
                    authorlist = work.authors.copy()
                    authorlist.extend(authors)
                    unique_ids = set(map(id, authorlist))
                    uniquelist = []
                    for i in authorlist:
                        if id(i) in unique_ids:
                            uniquelist.append(i)
                            unique_ids.remove(id(i))
                    work.authors = uniquelist
                else:
                    work.authors = authors
            if not work.doi:
                work.doi = await normalize_doi(data.get('doi'))
            if not work.year:
                work.year = data.get('publication_year')
            if not work.type:
                work.type = work_type
            
                journal = None
                publisher = None
                if data.get('primary_location'):
                    source = data.get('primary_location').get('source')
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
                if journal:
                    if not work.journals:
                        work.journals = [journal]
                    else:
                        work.journals.append(journal)
                if publisher:
                    if not work.publishers:
                        work.publishers = [publisher]
                    else:
                        work.publishers.append(publisher)

        self.works[work.openalex_id] = work
        if work.doi not in self.works:
            self.works[work.doi] = work

        self.flat_works.append(work)

    async def add_pure_work(self, data: dict, existing_work: Work | None = None):
        if data.get('internal_repository_id') in self.works:
            return
        
        authors = []
        if data.get('authors'):
            for auth in data.get('authors'):
                if auth.get('internal_repository_id') in self.authors:
                    auth = self.authors[auth.get('internal_repository_id')]
                    if len(auth.groups) > 0:
                        authors.append(auth)
                    
                
        journals = []
        publishers = []

        if data.get('publishers'):
            for pub in data.get('publishers'):
                publishers.append(await self.add_or_get_publisher(name=pub))
        if data.get('issn'):
            issns = []
            issn_rawlist : list[dict[str,str]] = data.get('issn')
            for issn in issn_rawlist:
                issns.append(issn.values())
            for issn in issns:
                if issn in self.journals:
                    journals.append(self.journals[issn])
                else:
                    self.missing_issns.append(issn)
        pure_id = data.get('internal_repository_id')
        doi = await normalize_doi(data.get('doi'))
        title = data.get('title')
        year = data.get('publication_date')

        if not existing_work:
            work = Work(data_sources=[DataSource.PURE],
                        pure_id=pure_id,
                        authors=authors,
                        doi=doi,
                        title=title,
                        year=year,
                        journals=journals,
                        publishers=publishers,
                    )
        else:
            
            work = existing_work
            work.data_sources.append(DataSource.PURE)
            work.pure_id = data.get('internal_repository_id')
            if authors:
                if len(work.authors)>0:
                    authorlist = work.authors.copy()
                    authorlist.extend(authors)
                    unique_ids = set(map(id, authorlist))
                    uniquelist = []
                    for i in authorlist:
                        if id(i) in unique_ids:
                            uniquelist.append(i)
                            unique_ids.remove(id(i))
                    work.authors = uniquelist
                else:
                    work.authors = authors
            if not work.doi:
                work.doi = doi
            if not work.year:
                work.year = year
            if not work.title:
                work.title = title
            if not work.journals:
                work.journals = journals
            elif journals:
                work.journals.extend(journals)
            if not work.publishers:
                work.publishers = publishers
            elif publishers:
                work.publishers.extend(publishers)

        self.works[work.pure_id] = work
        if work.doi not in self.works:
            self.works[work.doi] = work
        self.flat_works.append(work)
    async def add_or_get_publisher(self, name: str, id: str | None = None) -> Publisher:
        if id and id in self.publishers:
            return self.publishers[id]
        elif name and name in self.publishers:
            return self.publishers[name]
        else:
            publisher = Publisher(name=name, openalex_id=id)
            self.publishers[publisher.openalex_id] = publisher
            self.publishers[publisher.name] = publisher
            self.publishers_flat.append(publisher)
            return publisher
    
    async def add_or_get_journal(self, data: dict) -> Journal:
        journal = None
        if data.get('openalex_id') and data.get('openalex_id') in self.journals:
            journal = self.journals[data.get('openalex_id')]
        elif data.get('issn_l') and data.get('issn_l')in self.journals:
            journal = self.journals[data.get('issn_l')]
        elif data.get('issns'):
            for issn in data.get('issns'):
                if issn and issn in self.journals:
                    co.print(f'Found journal in list by {issn}')
                    journal = self.journals[issn]
                    break
        elif data.get('name') and data.get('name') in self.journals:
            journal = self.journals[data.get('name')]
        
        if not journal:
            journal = Journal(name=data.get('name'), openalex_id=data.get('openalex_id'), publisher=data.get('publisher'), issns = data.get('issns'), issn_l=data.get('issn_l'))
            if journal.openalex_id:
                self.journals[journal.openalex_id] = journal
            self.journals[journal.name] = journal
            if journal.issn_l:
                self.journals[journal.issn_l] = journal
            if journal.issns:
                for issn in journal.issns:
                    self.journals[issn] = journal
            self.journals_flat.append(journal)
        
        if not journal.openalex_id and data.get('openalex_id'):
            journal.openalex_id = data.get('openalex_id')
            self.journals[journal.openalex_id] = journal
        if not journal.issn_l and data.get('issn_l'):
            journal.issn_l = data.get('issn_l')
            self.journals[journal.issn_l] = journal
        return journal
    

    async def add_works_by_author(self):
        # from the authorlist, grab all works by those people
        # use openalexid, orcid, etc
        ...

    async def get_work_data_from_openaire():
        # for each work in the list that doesn't have openaire id: pull data from openaire
        ...

    async def get_work_data_from_crossref():
        # for each doi query crossref
        ...

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