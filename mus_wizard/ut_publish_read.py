'''
Make an overview of data to help decisions for library budgets.


Scope:
Year of publication = 2020-2024
Output type: articles, proceedings, books

-> Retrieve all publications from UT OAI-PMH endpoint
-> Retrieve all UT authors from UT OAI-PMH endpoint

Author route:
    -> Find each author in:
        OpenAlex
        ORCID

    -> For each author, retrieve all publications in scope

Work route:
    -> Retrieve all works in scope from:
        - OpenAlex
        - OpenAIRE
        - Crossref
    -> For each identified work from the various sources, match to OpenAlex item

Now we have our base collection.

Now use the list of works to make lists:
-> Published work
    -> Overview per year, faculty, group/dept, author
    -> Show journal, publisher
-> Cited works (so referenced in the works published by UT authors)
    -> Overview per year, faculty, group/dept, author
    -> Show journal, publisher
-> Citations (so works by UT authors that are cited by others)
    -> Overview per year, faculty, group/dept, author
    -> Show journal, publisher
'''

from mus_wizard.database.mongo_client import MusMongoClient
from mus_wizard.harvester.crossref import CrossrefAPI
from mus_wizard.harvester.openalex import OpenAlexAPI, OpenAlexQuery
from mus_wizard.harvester.openaire import OpenAIREAPI
from mus_wizard.harvester.oai_pmh import OAI_PMH
from mus_wizard.harvester.orcid import ORCIDAPI
from mus_wizard.database.matching import AuthorMatcher, WorkMatcher
from mus_wizard.constants import FACULTYNAMES, UTRESEARCHGROUPS_FLAT, ROR
import asyncio
from dataclasses import dataclass, field
from enum import Enum
from rich.console import Console

co = Console()

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

@dataclass
class Group:
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
@dataclass
class Publisher:
    name: str
    openalex_id: str

@dataclass
class Journal:
    name: str
    openalex_id: str
    publisher: Publisher


class WorkType(Enum):
    JOURNAL_ARTICLE = 1
    CONFERENCE_PROCEEDING = 2
    BOOK = 3
    BOOK_CHAPTER = 4

@dataclass
class Work:
    data_sources: list[DataSource]
    openalex_id: str | None = None
    pure_id: str | None = None
    openaire_id: str | None = None
    authors: list[Author] = field(default_factory=list)

    publisher: Publisher | None = None
    journal: Journal | None = None
    doi: str | None = None
    title: str | None = None
    year: int | None = None
    type: WorkType | None = None

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


    async def run(self, period = None):
        if period:
            self.period = period
        else:
            self.period = [2020, 2021, 2022, 2023, 2024]

        ut = Faculty(name='University of Twente', pure_id='491145c6-1c9b-4338-aedd-98315c166d7e')
        self.faculties[ut.pure_id] = ut

        co.print('step 1: Initializing indexes, get first batch of items from oai-pmh and openalex')
        if False:
            async with asyncio.TaskGroup() as tg:
                indexes = tg.create_task(self.mongoclient.add_indexes())
                pure_harvest = tg.create_task(self.harvest_pure())
                all_openalex = tg.create_task(self.get_ut_works_openalex())
        await self.make_groups()
        await self.make_authorlist()
        co.print('Done.')
        # step 2: for each author:
        #     - match to openalex author
        #     - get all works from openalex and orcid

        # step 3: for each remaining oai-pmh work:
        #     - match to openalex work

        # step 4: for each work:
        #     - get openaire and crossref data

        # step 5: combine and process the data
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
        # get author data from mongodb and put into self.authors as Author objects
        co.print(f'{await self.mongoclient.authors_openalex.estimated_document_count()=}')
        co.print(f'{await self.mongoclient.openaire_cris_persons.estimated_document_count()=}')
        found = 0
        async for entry in self.mongoclient.authors_openalex.find({},projection={'id':1, 'affiliations':1, 'display_name':1, 'ids':1, 'orcid':1}):
            if entry['id'] in self.authors:
                continue
            if entry.get('affiliations'):
                for aff in entry['affiliations']:
                    if aff.get('institution'):
                        if aff.get('institution').get('ror') == ROR:
                            await self.new_openalex_author(entry)
                            found += 1
                            break
        print(found)
        print(f'OpenAlex authors with UT affils added to list: ', len(self.flat_authors))
        orcid_authors = [ author.orcid for author in self.authors.values() if author.orcid]
        scopus_authors = [ author.scopus for author in self.authors.values() if author.scopus]
        print(f'# with ORCIDS: {len(orcid_authors)}')
        print(f'# with Scopus IDs: {len(scopus_authors)}')
        scopus = 0
        orcid = 0
        orcid_searchlist = {}
        scopus_searchlist = {}
        scopusmatches = 0
        orcidmatches = 0
        async for entry in self.mongoclient.openaire_cris_persons.find({},projection={'internal_repository_id':1, 'first_names':1, 'family_names':1, 'scopus_id':1, 'orcid':1,'affiliations':1}):
            if entry.get('orcid'):
                orcid +=1
                if entry.get('orcid') in self.authors:
                    await self.update_author_with_pure_data(self.authors[entry.get('orcid')], entry)
                    orcidmatches += 1
                else:
                    orcid_searchlist[entry.get('orcid')] = entry
            if entry.get('scopus_id'):
                scopus+=1
                if entry.get('scopus_id') in self.authors:
                    await self.update_author_with_pure_data(self.authors[entry.get('scopus_id')], entry)
                    scopusmatches += 1
                else:
                    scopus_searchlist[entry.get('scopus_id')] = entry
        co.print(f'orcids in pure authors: {orcid} \n number not matched: {len(orcid_searchlist)}')
        co.print(f'scopus ids in pure authors: {scopus} \n number not matched: {len(scopus_searchlist)}')
        co.print(f'# Matches found Openalex <-> Pure authors: {orcidmatches=}, {scopusmatches=}')

        co.print(f'Now retrieving Openalex data for {len(orcid_searchlist)} ORCIDs and {len(scopus_searchlist)} Scopus IDs')
        orcids = [o.replace('\'','') for o in orcid_searchlist.keys()]
        queryc = OpenAlexQuery(self.mongoclient, self.mongoclient.authors_openalex, 'authors', years=self.period)
        queryc.add_query_by_orcid(orcids, single=True)
        await queryc.run()
        co.print(f'Total added to list: ', len(self.flat_authors))

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
        ...

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

