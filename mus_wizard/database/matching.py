import datetime

import motor.motor_asyncio
import pandas as pd
from polyfuzz import PolyFuzz
from polyfuzz.models import TFIDF

from mus_wizard.constants import MONGOURL
from mus_wizard.database.mongo_client import MusMongoClient
from mus_wizard.harvester.openalex import OpenAlexQuery
from mus_wizard.utils import normalize_doi, remove_invalid_dois

from typing import Self
from rich.console import Console
from rich.table import Table
from dataclasses import dataclass
from pyinstrument import Profiler

console = Console()
class AuthorMatcher():
    # todo: match cerif data
    motorclient: motor.motor_asyncio.AsyncIOMotorDatabase = motor.motor_asyncio.AsyncIOMotorClient(
        MONGOURL).metadata_unification_system

    def __init__(self):
        self.double_check_names = [
            'yang', 'yi', 'zhang', 'zhao', 'zhu', 'zhou', 'zhuang', 'zhun', 'zhuo', 'zhuy', 'zhang',
            'chen', 'cheng', 'chen', 'chen', 'liu', 'yuan', 'wang', 'bu', 'feng', 'fu', 'gu', 'guo',
            'hao', 'hu', 'jia', 'jiang', 'jie', 'jin', 'jing', 'li', 'xiao', 'xu', 'wu', 'lin', 'ying'
        ]
        self.names = {}
        self.orcids = {}
        self.scopusids = {}
        self.isnis = {}
        self.results = {'orcid_matches': 0, 'repo_authors_checked': 0, 'scopus_id_matches': 0, 'isni_matches': 0, 'name_matches': 0}

    async def get_authors(self):
        print('getting data from mongodb for author matching')
        self.names = {}
        self.orcids = {}
        self.scopusids = {}
        self.isnis = {}

        async for a in self.motorclient.openaire_cris_persons.find():
            self.results['repo_authors_checked']+=1
            if a.get('orcid'):
                self.orcids[a['internal_repository_id']] = a['orcid']
            if a.get('scopus_id'):
                self.scopusids[a['internal_repository_id']] = a['scopus_id']
            if a.get('isni'):
                self.isnis[a['internal_repository_id']] = a['isni']

            if a['internal_repository_id'] not in self.orcids and a['internal_repository_id'] not in self.scopusids and a['internal_repository_id'] not in self.isnis:
                first_name = a.get('first_names')
                first_name_normal = first_name
                if first_name:
                    first_name = first_name.lower()
                else:
                    first_name = ''
                last_name = a.get('family_names')
                last_name_normal = last_name
                if last_name:
                    last_name = last_name.lower()
                else:
                    last_name = ''
                if first_name not in self.double_check_names and last_name not in self.double_check_names:
                    if first_name and last_name:
                        self.names[a['internal_repository_id']] = first_name_normal + ' ' + last_name_normal
                    elif first_name:
                        self.names[a['internal_repository_id']] = first_name_normal
                    elif last_name:
                        self.names[a['internal_repository_id']] = last_name_normal


        print(f'len of self.authororcids for matching: {len(self.orcids)} ')
        print(f'len of self.authorscopusids for matching: {len(self.scopusids)} ')
        print(f'len of self.isnis for matching: {len(self.isnis)} ')
        print(f'len of self.authornames for authors without any pids: {len(self.names)}')

    async def match_pids(self):
        await self.match_orcids()
        await self.match_scopusids()
        await self.match_isnis()
        
    async def match_orcids(self):
        if not self.orcids:
            print('no orcids to match')
            return None
        print(f'matching {len(self.orcids)} orcids')
        orcidsnotfound = {}
        for internal_repository_id, orcid in self.orcids.items():
            openalex = await self.motorclient.authors_openalex.find_one({'ids.orcid': orcid})
            if not openalex:
                orcidsnotfound[internal_repository_id] = orcid
            if openalex:
                await self.motorclient.openaire_cris_persons.update_one({'internal_repository_id': internal_repository_id}, {'$set': {'id':openalex.get('id'), 'openalex_match': {'name': openalex['display_name'], 'id': openalex['id']}}})
                self.results['orcid_matches']+=1
        if orcidsnotfound:
            query = OpenAlexQuery(MusMongoClient(), MusMongoClient().authors_openalex, 'authors')
            query.add_query_by_orcid(orcidsnotfound.values())
            await query.run()
            for author in orcidsnotfound:
                openalex = await self.motorclient.authors_openalex.find_one({'ids.orcid': orcid})
                if openalex:
                    await self.motorclient.openaire_cris_persons.update_one({'internal_repository_id': internal_repository_id}, {'$set': {'id':openalex.get('id'), 'openalex_match': {'name': openalex['display_name'], 'id': openalex['id']}}})
                    self.results['orcid_matches']+=1
        print(f'{self.results["orcid_matches"]} orcids matched')
        print(f'{len(orcidsnotfound)} orcids not found in openalex')
    async def match_scopusids(self):
        if not self.scopusids:
            print('no scopusids to match')
            return None
        print(f'matching {len(self.scopusids)} scopusids')
        scopusidsnotfound = {}
        for internal_repository_id, scopusid in self.scopusids.items():
            openalex = await self.motorclient.authors_openalex.find_one({ 'ids.scopus': {'$in':[f'/{scopusid}/i']} })
            if not openalex:
                scopusidsnotfound[internal_repository_id] = scopusid
            if openalex:
                await self.motorclient.openaire_cris_persons.update_one({'internal_repository_id': internal_repository_id}, {'$set': {'id':openalex.get('id'), 'openalex_match': {'name': openalex['display_name'], 'id': openalex['id']}}})
                self.results['scopus_id_matches']+=1
        print(f'{self.results["scopus_id_matches"]} scopusids matched')
        print(f'{len(scopusidsnotfound)} scopusids not found in openalex')
    async def match_isnis(self):
        if not self.isnis:
            print('no isnis to match')
            return None
        print('openalex does not have isnis to match.')
        
    async def match_names(self):
        if not self.names:
            print('no names to match')
            return None
        
        print(f'matching {len(self.names)} names')
        reverse_names_dict = {v:k for k,v in self.names.items()}
        to_list = [a['display_name'] async for a in
                   self.motorclient.authors_openalex.find({}, projection={'display_name': 1},
                                                          sort=[('display_name', 1)])]
        tfidf = TFIDF(n_gram_range=(3, 3), clean_string=True, min_similarity=0.7)
        model = PolyFuzz(tfidf)
        try:
            matchlist = model.match(list(self.names.values()), to_list)
        except ValueError as e:
            print(f'Error when matching names: {e}')
            print('aborting.')
            return
        results: pd.DataFrame = matchlist.get_matches()
        top_results = results[results['Similarity'] > 0.8]
        top_results_list = zip(top_results['From'].to_list(), top_results['To'].to_list())
        for from_name, to_name in top_results_list:
            openalexid = await self.motorclient.authors_openalex.find_one({'display_name': to_name})
            openalexid = openalexid['id']
            await self.motorclient.openaire_cris_persons.update_one({'internal_repository_id': reverse_names_dict[from_name]}, {'$set': {'id':openalexid, 'openalex_match': {'name': to_name, 'id': openalexid}}})
            self.results['name_matches']+=1

        print(f'{self.results["name_matches"]} names matched')
    async def run(self):
        profiler = Profiler()
        profiler.start()
        print('running author matcher')
        await self.get_authors()
    
        await self.match_pids()
        #await self.match_names()
        profiler.stop()
        profiler.print()
        with open(f'profiler_authormatcher.html', 'w') as f:
            f.write(profiler.output_html())
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
        if value.__class__ is not self.__class__:
            return False
        if self.id:
            if self.id == value.id:
                return True
        elif self.doi:
            if self.doi == value.doi:
                return True
        elif self.internal_repo_id:
            if self.internal_repo_id == value.internal_repo_id:
                return True
        return False
    
    def is_match(self) -> Self:
        self.has_match = True
        return self

class WorkList:
    '''
    A class to store and manage a list of Work objects for matching works.
    '''
    works_by_id: dict[str, Work] = None
    works_by_doi: dict[str, Work] = None
    works_by_internal_repo_id: dict[str, Work] = None
    works_as_list: list[Work] = None
    unmatched_works: list[Work] = None
    matched_works: list[Work] = None

    def __init__(self) -> None:
        self.works_by_id = {}
        self.works_by_doi = {}
        self.works_as_list = []
        self.unmatched_works = []
        self.works_by_internal_repo_id = {}
        self.matched_works = []

    def __str__(self) -> str:
        self.update()
        return f'WorkList with:\n {len(self.works_by_id)} works by id\n {len(self.works_by_doi)} works by doi\n {len(self.works_as_list)} works as list\n {len(self.unmatched_works)} unmatched works\n {len(self.works_by_internal_repo_id)} works by internal repo id\n {len(self.matched_works)} matched works'
    
    def get_all(self, param: str | None = None) -> list[Work] | dict[str, Work]:
        '''
        Returns a list of all works in the list.
        '''
        self.update()
        if param:
            if param == 'id':
                return self.works_by_id
            if param == 'doi':
                return self.works_by_doi
            if param == 'internal_repo_id':
                return self.works_by_internal_repo_id
            if param == 'unmatched':
                return self.unmatched_works
            if param == 'matched':
                return self.matched_works
        return self.works_as_list
    
    def add_work(self, work: Work) -> None:
        '''
        Parameters:
            work (Work): A Work object to add to this WorkList.
        '''
        self.works_as_list.append(work)
    
    def add_works(self, works: list[Work]) -> None:
        '''
        Parameters:
            works (list[Work]): A list of Work objects to add to this WorkList.
        '''
        for work in works:
            self.add_work(work)
        self.update()

    def remove_works_without_doi(self) -> None:
        '''
        Removes all works from this WorkList that do not have a DOI.
        '''
        startlen = len(self.works_as_list)
        self.works_as_list = [work for work in self.works_as_list if work.doi]
        self.update()
        print(f'removed works without dois, from {startlen} works to {len(self.works_as_list)} works')

    def update(self) -> None:
        '''
        Updates the list & dict attributes with the current state of the works in works_as_list
        '''
        self.works_by_id = {work.id: work for work in self.works_as_list if work.id}
        self.works_by_doi = {work.doi: work for work in self.works_as_list if work.doi}
        self.works_by_internal_repo_id = {work.internal_repo_id: work for work in self.works_as_list if work.internal_repo_id}
        
    def get_unmatched_works(self) -> list[Work]:
        '''
        Returns a list of all works in the list that have not been matched yet.
        '''
        dois = {work.doi:'' for work in self.matched_works if work.doi}
        self.unmatched_works = [work for work in self.works_as_list if work.doi not in dois]
        print(f'returning {len(self.unmatched_works)} unmatched works')
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

        if work.doi in self.works_by_doi:
            val = self.works_by_doi[work.doi]
            param = work.doi
            self.matched_works.append(val.is_match())
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
        self.update()
        for work in works:
            match, val = self.match_one(work, True)
            if match:
                matches[val] = {'found_work': match, 'search_param': work}
        self.update()
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
        profiler = Profiler()
        profiler.start()
        await self.get_works()
        print(f'got {len(self.worklist.works_as_list)} openalex works ready to match')
        await self.match_dois()
        profiler.stop()
        profiler.print()
        with open(f'profiler_workmatcher.html', 'w') as f:
            f.write(profiler.output_html())
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

        print(f'matching {num_total} pure items to {len(self.worklist.get_all())} openalex works.')
        async for pure_item in self.motorclient['openaire_cris_publications'].find():
            doi = None
            if pure_item.get('doi'):
                doi = await normalize_doi(pure_item['doi'])
            work = Work(id=pure_item.get('id'), doi=doi, internal_repo_id=pure_item.get('internal_repository_id'))
            self.unmatched_works.add_work(work)

        console.print(f'OpenAlex works: {len(self.worklist.get_all('doi').keys())} with dois | {len(self.worklist.get_all('id').keys())} with ids')
        console.print(f'Repository works: {len(self.unmatched_works.get_all('doi').keys())} with dois | {len(self.unmatched_works.get_all('id').keys())} with ids')
        self.matches = self.unmatched_works.match_multiple(self.worklist.get_all())
        print(f'found {len(self.matches.keys())} matches.')
        '''for pid, work_dict in self.matches.items():
            try:
                found_work = work_dict['found_work']
                search_work = work_dict['search_param']
                await self.motorclient.openaire_cris_publications.update_one({'internal_repository_id': search_work.internal_repo_id}, {'$set': {'id': found_work.id}})
            except Exception as e:
                print(f'Error adding match:\n     repo item {search_work} <|> found work {found_work}:\n        {e}')
        '''
        print('unmatched_works contents before filtering out matches & non-doi works:')
        print(self.unmatched_works)
        self.unmatched_works.remove_works_without_doi()
        self.unmatched_works.get_unmatched_works()

        print('unmatched_works contents after filtering out matches & non-doi works:')
        print(self.unmatched_works)
        console.print(f'{len(self.unmatched_works.get_unmatched_works())} publications with DOIs in the repository currently unmatched with OpenAlex works.\n Disabled retrieving missing DOIs from OpenAlex API.')
        #await self.get_missing_dois()

    async def get_missing_dois(self):
        dois = [work.doi for work in self.unmatched_works.get_unmatched_works()]
        dois = await remove_invalid_dois(dois)
        if dois:
            console.print(f'getting OpenAlex works for {len(dois)} dois')
            query = OpenAlexQuery(mongoclient=MusMongoClient(), mongocollection=MusMongoClient().works_openalex, pyalextype='works', item_ids=dois, id_type='doi')
            await query.add_to_querylist()
            results = await query.run()
            console.print(f'added {len(results["results"])} works to works_openalex collection using missing dois.')
            console.print(f'full results: {results}')
            if len(results["results"])>0:
                console.print('Advice: re-run WorkMatcher().match_dois() for possible new matches.')
                
        else:
            console.print('no missing dois!')

