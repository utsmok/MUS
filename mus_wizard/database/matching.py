import datetime

import motor.motor_asyncio
import pandas as pd
from polyfuzz import PolyFuzz
from polyfuzz.models import TFIDF

from mus_wizard.constants import MONGOURL
from mus_wizard.database.mongo_client import MusMongoClient
from mus_wizard.harvester.openalex import OpenAlexQuery
from mus_wizard.utils import normalize_doi

from rich.console import Console
from rich.table import Table
from dataclasses import dataclass

console = Console()
class AuthorMatcher():
    motorclient: motor.motor_asyncio.AsyncIOMotorClient = motor.motor_asyncio.AsyncIOMotorClient(
        MONGOURL).metadata_unification_system

    def __init__(self):
        self.double_check_names = [
            'yang', 'yi', 'zhang', 'zhao', 'zhu', 'zhou', 'zhuang', 'zhun', 'zhuo', 'zhuy', 'zhang',
            'chen', 'cheng', 'chen', 'chen', 'liu', 'yuan', 'wang', 'bu', 'feng', 'fu', 'gu', 'guo',
            'hao', 'hu', 'jia', 'jiang', 'jie', 'jin', 'jing', 'li', 'xiao', 'xu', 'wu', 'lin', 'ying'
        ]
        self.authornames = []
        self.authororcids = []
        self.results = {'total': 0, 'names': []}

    async def get_authors(self):
        pureauthornamelist = []
        pureauthororcidlist = []
        async for a in self.motorclient['authors_pure'].find({},
                                                             projection={'id'                : 1, 'affl_periods': 1,
                                                                         'author_name'       : 1, 'author_last_name': 1,
                                                                         'author_first_names': 1, 'author_orcid': 1,
                                                                         'openalex_match'    : 1, 'author_pureid': 1}):
            if a.get('openalex_match'):
                if not a.get('id') or a.get('id') != a.get('openalex_match').get('id'):
                    print(f"{a.get('author_pureid')}  --  {a.get('openalex_match')}  -- {a.get('id')}")
                    await self.motorclient.authors_pure.update_one({'_id': a.get('_id')},
                                                                   {'$set': {'id': a.get('openalex_match').get('id')}})
            if a.get('affl_periods'):
                for period in a['affl_periods']:
                    if not period['end_date'] or period['end_date'] > datetime.datetime(2010, 1, 1):
                        if a.get('author_orcid'):
                            pureauthororcidlist.append((a['author_orcid'], a['author_name']))
                        elif a['author_last_name'].lower() not in self.double_check_names and a[
                            'author_first_names'].lower() not in self.double_check_names:
                            pureauthornamelist.append(a['author_name'])
        self.authornames = list(set(pureauthornamelist))
        self.authororcids = list(set(pureauthororcidlist))
        print(f'len of self.authornames for matching: {len(self.authornames)}')
        print(f'len of self.authororcids for matching: {len(self.authororcids)} ')

    async def match_orcids(self):
        orcidsnotfound = []
        for author in self.authororcids:
            orcid = 'https://orcid.org/' + author[0]
            name = author[1]
            openalex = await self.motorclient.authors_openalex.find_one({'ids.orcid': orcid})
            if not openalex:
                orcidsnotfound.append((orcid, name))
            if openalex:
                await self.motorclient.authors_pure.update_one({'author_name': name}, {
                    '$set': {'openalex_match': {'name': openalex['display_name'], 'id': openalex['id']}}})
        if orcidsnotfound:
            query = OpenAlexQuery(MusMongoClient(), MusMongoClient().authors_openalex, 'authors')
            query.add_query_by_orcid([orcid[0] for orcid in orcidsnotfound])
            await query.run()

            for author in orcidsnotfound:
                openalex = await self.motorclient.authors_openalex.find_one({'ids.orcid': author[0]})
                if openalex:
                    await self.motorclient.authors_pure.update_one({'author_name': author[1]}, {
                        '$set': {'openalex_match': {'name': openalex['display_name'], 'id': openalex['id']}}})

    async def match_names(self):
        to_list = [a['display_name'] async for a in
                   self.motorclient.authors_openalex.find({}, projection={'display_name': 1},
                                                          sort=[('display_name', 1)])]
        tfidf = TFIDF(n_gram_range=(3, 3), clean_string=True, min_similarity=0.7)
        model = PolyFuzz(tfidf)
        try:
            matchlist = model.match(self.authornames, to_list)
        except ValueError as e:
            print(f'Error when matching names, probably no authornames in self.authornames: {e}')
            print('aborting.')
            return
        results: pd.DataFrame = matchlist.get_matches()
        top_results = results[results['Similarity'] > 0.8]
        top_results_list = zip(top_results['From'].to_list(), top_results['To'].to_list())
        for from_name, to_name in top_results_list:
            openalexid = await self.motorclient.authors_openalex.find_one({'display_name': to_name})
            openalexid = openalexid['id']
            await self.motorclient.authors_pure.update_one({'author_name': from_name}, {
                '$set': {'openalex_match': {'name': to_name, 'id': openalexid}, 'id': openalexid}})
            self.results['names'].append(from_name)
            self.results['total'] = self.results['total'] + 1

    async def run(self):
        await self.get_authors()
        await self.match_orcids()
        await self.match_names()
        return self.results

@dataclass
class Work:
    '''
    A class to store a Work object for matching works 
    -- not to be confused with the django MUS model Work.

    Will return an equality if any of the id, doi, or isbn fields are equal.
    '''
    id: str | None = None
    doi: str | None = None
    fulldict: dict[str,str] = None
    has_match: bool = False
    internal_repo_id: str | None = None

    def __post_init__(self) -> None:
        self.fulldict = {'id': self.id, 'doi': self.doi, 'internal_repo_id': self.internal_repo_id}

    def __eq__(self, value: object) -> bool:
        if value.__class__ is self.__class__:
            if self.id:
                if self.id == value.id:
                    return True
            elif self.doi:
                if self.doi == value.doi:
                    return True
        return False

class WorkList:
    '''
    A class to store and manage a list of Work objects for matching works.
    '''
    works_by_id: dict[str, Work] = None
    works_by_doi: dict[str, Work] = None
    works_as_list: list[Work] = None
    unmatched_works: list[Work] = None

    def __init__(self) -> None:
        self.works_by_id = {}
        self.works_by_doi = {}
        self.works_as_list = []
        self.unmatched_works = []

    def add_work(self, work: Work) -> None:
        '''
        Parameters:
            work (Work): A Work object to add to this WorkList.
        '''
        if work.id:
            self.works_by_id[work.id] = work
        if work.doi:
            self.works_by_doi[work.doi] = work
        self.works_as_list.append(work)
    
    def add_works(self, works: list[Work]) -> None:
        '''
        Parameters:
            works (list[Work]): A list of Work objects to add to this WorkList.
        '''
        for work in works:
            self.add_work(work)

    def remove_works_without_doi(self) -> None:
        '''
        Removes all works from this WorkList that do not have a DOI.
        '''
        self.works_as_list = [work for work in self.works_as_list if any(work.doi, work.id)]
        self.works_by_id = {work.id: work for work in self.works_as_list if work.id}
        self.works_by_doi = {work.doi: work for work in self.works_as_list if work.doi}

    def get_unmatched_works(self) -> list[Work]:
        '''
        Returns a list of all works in the list that have not been matched yet.
        '''
        self.unmatched_works = [work for work in self.works_as_list if not work.has_match]
        return self.unmatched_works

    def match_one(self, work: Work, return_match_param=False) -> tuple[Work, str] | Work | None:
        '''
        Finds a matching for the work in the list based on id, doi, or isbn.
        If return_match_param is True, returns a tuple of the matching Work and the matching parameter (id, doi, or isbn).
        Otherwise, returns the matching Work.
        Returns None if no match is found.

        Parameters:
            work (Work): The work to match.
            return_match_param (bool, optional): Whether to return the matching parameter (id, doi, or isbn). Defaults to False.

        Returns:
            tuple[Work, str] | Work | None: The matching Work (with the matching parameter if return_match_param is True), or None if no match is found.
        '''
        val = None
        param = None

        if work.id:
            if work.id in self.works_by_id:
                val = self.works_by_id[work.id]
                param = work.id
        if work.doi:
            if work.doi in self.works_by_doi:
                val = self.works_by_doi[work.doi]
                param = work.doi
        if return_match_param:
            return val, param
        else:
            return val
    def match_multiple(self, works: list[Work]) -> dict[str, dict[str,Work]] | dict:
        '''
        Parameters:
            works (list[Work]): A list of Work objects to match.
        Returns:
            dict[str, dict[str,Work]]: A dict with matching id/doi as keys, and a dict with the Work objects 'found_work' and 'search_param' as values.
        '''
        matches = {}
        for work in works:
            match, val = self.match_one(work, True)
            if match:
                work.has_match = True
                matches[val] = {'found_work': match, 'search_param': work}
        return matches


class WorkMatcher():
    # match OpenAlex works to Pure works
    # OpenAlex works are already linked to the other sources (datacite, crossref, openaire)
    # start with matching DOIs and ISBNs
    # then maybe by using other data if much is missing
    
    motorclient: motor.motor_asyncio.AsyncIOMotorClient = motor.motor_asyncio.AsyncIOMotorClient(
        MONGOURL).metadata_unification_system

    def __init__(self):
        self.results = {'total': 0, 'works': []}
        self.missing_dois : WorkList | None = None
        self.worklist : WorkList = WorkList()
        self.unmatched_works : WorkList= WorkList()
        

    async def run(self):
        await self.get_works()
        print(f'got {len(self.worklist.works_as_list)} openalex works ready to match')
        await self.match_dois()

        return self.results

    async def get_works(self):
        async for work in self.motorclient.works_openalex.find({}, projection={'id': 1, 'doi': 1}):
            try:
                doi = await normalize_doi(work.get('doi')) if work.get('doi') else None
            except ValueError as e:
                print(f'{work.get("id")} has invalid DOI: {work.get("doi")} - got error: {e}')
                doi = None
            work = Work(id=work.get('id'), doi=doi)
            self.worklist.add_work(work)

    async def match_dois(self):
        num_total = await self.motorclient.openaire_cris_publications.estimated_document_count()
        num_without_match = await self.motorclient.openaire_cris_publications.estimated_document_count(
            {'id': {'$exists': False}})
        print(f'matching {num_total} pure items | {num_without_match} without a match')
        async for pure_item in self.motorclient['openaire_cris_publications'].find():
            doi = None
            if pure_item.get('doi'):
                doi = await normalize_doi(pure_item['doi'])
            work = Work(id=pure_item.get('id'), doi=doi, internal_repo_id=pure_item.get('internal_repository_id'))
            self.unmatched_works.add_work(work)

        console.print(f'matching {len(self.unmatched_works.works_as_list)} publications from the repository to {len(self.worklist.works_as_list)} openalex works.')
        console.print(f'OpenAlex works: {len(self.worklist.works_by_doi.keys())} with dois | {len(self.worklist.works_by_id.keys())} with ids')
        console.print(f'Repository works: {len(self.unmatched_works.works_by_doi.keys())} dois | {len(self.unmatched_works.works_by_id.keys())} with ids')
        self.matches = self.worklist.match_multiple(self.unmatched_works.works_as_list)
        print(f'found {len(self.matches.keys())} matches.')
        for pid, work_dict in self.matches.items():
            try:
                found_work = work_dict['found_work']
                search_work = work_dict['search_param']
                await self.motorclient.openaire_cris_publications.update_one({'internal_repository_id': search_work.internal_repo_id}, {'$set': {'id': found_work.id}})
            except Exception as e:
                print(f'Error adding match:\n     repo item {search_work} <|> found work {found_work}:\n        {e}')

        self.unmatched_works = WorkList()
        self.unmatched_works.add_works(self.unmatched_works.get_unmatched_works())
        self.unmatched_works.remove_works_without_doi()
        console.print(f'{len(self.unmatched_works.works_as_list) if self.unmatched_works.works_as_list else None} publications with DOIs in the repository currently unmatched with OpenAlex works.\n Retrieving missing DOIs from OpenAlex API.')
        #await self.get_missing_dois()

    async def get_missing_dois(self):
        # grab missing dois from openalex api
        # todo: fix this!
        print('getting missing dois seems to be broken, check it out!')
        query = OpenAlexQuery(MusMongoClient(), MusMongoClient().works_openalex, 'works', [work.doi for work in self.unmatched_works.works_as_list])
        await query.add_to_querylist()
        results = await query.run()
        print(f'added {len(results["results"])} works to works_openalex collection using missing dois.')
        if len(results["results"])>0:
            print('Re-running match_dois() to match missing dois to OpenAlex works.')
            await self.match_dois()

