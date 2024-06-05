import datetime

import motor.motor_asyncio
import pandas as pd
from polyfuzz import PolyFuzz
from polyfuzz.models import TFIDF

from mus_wizard.constants import MONGOURL
from mus_wizard.database.mongo_client import MusMongoClient
from mus_wizard.harvester.openalex import OpenAlexQuery
from mus_wizard.utils import normalize_doi


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


class WorkMatcher():
    # match OpenAlex works to Pure works
    # OpenAlex works are already linked to the other sources (datacite, crossref, openaire)
    # start with matching DOIs and ISBNs
    # then maybe by using other data if much is missing

    motorclient: motor.motor_asyncio.AsyncIOMotorClient = motor.motor_asyncio.AsyncIOMotorClient(
        MONGOURL).metadata_unification_system

    def __init__(self):
        self.results = {'total': 0, 'works': []}
        self.missing_dois = {}
        self.missing_isbns = {}

    async def run(self):
        await self.get_works()
        print(f'got {len(self.works)} openalex works ready to match')
        await self.match_dois()

        return self.results

    async def get_works(self):
        works = {}
        async for work in self.motorclient.works_openalex.find({}, projection={'id': 1, 'doi': 1, 'ids.isbn': 1}):
            try:
                doi = await normalize_doi(work.get('doi')) if work.get('doi') else None
            except ValueError as e:
                print(f'{work.get("id")} has invalid DOI: {work.get("doi")} - got error: {e}')
                doi = None
            isbn = work.get('ids').get('isbn') if work.get('ids') else None
            fulldict = {'id': work.get('id'), 'isbn': isbn, 'doi': doi}
            works[work.get('id')] = fulldict
            if doi:
                works[doi] = fulldict
            if isbn:
                works[isbn] = fulldict
            works
        self.works = works

    async def match_dois(self):

        # use self.motorclient.items_pure_oaipmh.find() to loop over all items in pure_oaipmh collection
        # projection: only _id, id, identifier fields, nothing else
        # filter out all items that already have a value in the 'id' field

        num_items = 0
        num_matched = 0
        num_total = await self.motorclient.openaire_cris_publications.estimated_document_count()
        num_without_match = await self.motorclient.openaire_cris_publications.estimated_document_count(
            {'id': {'$exists': False}})
        print(f'matching {num_total} pure items -- {num_without_match} without a match')
        num_dois = 0
        num_isbns = 0
        # here is the functioncall to get all items, but it is missing the filter for items that already have a value in the 'id' field
        async for pure_item in self.motorclient['openaire_cris_publications'].find({'id': {'$exists': False}}):
            num_items = num_items + 1
            if num_items % 250 == 0:
                print(f'{num_items} total checked (+250)')
            if pure_item.get('id'):  # already matched, shouldn't happen
                continue
            if pure_item.get('doi'):
                num_dois = num_dois + 1
                doi = await normalize_doi(pure_item['doi'])
                if doi in self.works:
                    await self.motorclient.openaire_cris_publications.update_one({'_id': pure_item['_id']}, {
                        '$set': {'id': self.works[doi]['id']}})
                    num_matched = num_matched + 1
                    continue
                else:
                    self.missing_dois[doi] = pure_item
            if pure_item.get('isbn'):
                for isbn_entry in pure_item['isbn']:
                    num_isbns = num_isbns + 1
                    isbn = isbn_entry.get('value')
                    if isbn:
                        if isbn in self.works:
                            await self.motorclient.openaire_cris_publications.update_one({'_id': pure_item['_id']}, {
                                '$set': {'id': self.works[isbn]['id']}})
                            num_matched = num_matched + 1
                            continue
                        else:
                            self.missing_isbns[isbn] = pure_item
        print(
            f'matched {num_matched} out of {num_items} items \n found {num_dois} dois and {num_isbns} isbns in repo data \n ~{num_total} total items in the collection')

    async def get_missing_dois(self):
        # grab missing dois from openalex api
        ...

    async def get_missing_isbns(self):
        # grab missing isbns from openalex api
        ...
