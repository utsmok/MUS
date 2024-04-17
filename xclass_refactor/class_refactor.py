'''
temporary file

refactoring all the functions in mus_backend for retrieving items from apis, scrapers etc
-> from function-based into class-based

instead of calling the functions one after another we'll use classes to manage it all

main structure:
-> base class that manages the current update process
-> creates instances of all kinds of other classes that will hold/retrieve the data
-> take note that we want to bundle api calls and db operations in batches instead of one at a time


implement some multiprocessing/threading/asyncio where it makes sense

import multiprocessing as mp
from concurrent.futures import ProcessPoolExecutor

'''

from loguru import logger
from xclass_refactor.pure_import import PureAPI, PureReports, PureAuthorCSV
from xclass_refactor.openalex_import import OpenAlexAPI, OpenAlexQuery
from xclass_refactor.mus_mongo_client import MusMongoClient
from xclass_refactor.journal_browser_scraper import JournalBrowserScraper
from xclass_refactor.other_apis_import import CrossrefAPI, DataCiteAPI, OpenAIREAPI, SemanticScholarAPI, ZenodoAPI
from xclass_refactor.people_page_scraper import PeoplePageScraper

class UpdateManager:
    def __init__(self, years: list[int], include: dict):
        '''
        years: the publication years of the items to retrieve
        include: a dict detailing which apis/scrapes to run.
            default:
            {
                'works_openalex': True,
                'items_pure_oaipmh': True,
            }
            instead of True, you can also pass a list of ids to retrieve from that api as a value instead.
            e.g. {'works_openalex': ['https://openalex.org/W2105846236', 'https://openalex.org/W2105846237'], 'items_pure_oaipmh': True}
            '''

        if not include:
            include = {
                'works_openalex': True,
                'authors_openalex': True,
                'items_pure_oaipmh': True,
            }

        self.years = years
        self.include = include
        self.mongoclient = MusMongoClient()
        self.results = {}
        self.queries = []

    def run(self):
        '''
        runs the queries based on the include dict
        note: add some sort of multiprocessing/threading/asyncio/scheduling here
        '''
        print(self.include)
        print(self.years)
        openalex_results = ['works_openalex', 'authors_openalex', 'sources_openalex', 'funders_openalex', 'institutions_openalex', 'topics_openalex']
        if not self.include.keys():
            raise KeyError('dict UpdateManager.include is empty or invalid -- no updates to run.')
        openalex_requests = {}
        for key,item in self.include.items():
            if key in openalex_results:
                if not isinstance(item, list):
                    openalex_requests[key]=None
                else:
                    openalex_requests[key]=item

        if openalex_requests:
            print('running openalex')
            OpenAlexAPI(openalex_requests, self.years, self.mongoclient).run()
        if self.include.get('items_pure_oaipmh'):
            self.queries.append(PureAPI(self.years, self.mongoclient))
        if self.include.get('items_pure_reports'):
            self.queries.append(PureReports(self.mongoclient))
        if self.include.get('items_datacite'):
            self.queries.append(DataCiteAPI(self.mongoclient))
        if self.include.get('items_crossref'):
            print('running crossref')
            CrossrefAPI(self.years, self.mongoclient).run()
        if self.include.get('items_openaire'):
            self.queries.append(OpenAIREAPI(self.mongoclient))
        if self.include.get('items_zenodo'):
            self.queries.append(ZenodoAPI(self.mongoclient))
        if self.include.get('items_semantic_scholar'):
            self.queries.append(SemanticScholarAPI(self.mongoclient))
        if self.include.get('deals_journalbrowser'):
            self.queries.append(JournalBrowserScraper(self.mongoclient))
        if self.include.get('employees_peoplepage'):
            self.queries.append(PeoplePageScraper(self.mongoclient))

def main():
    mngr = UpdateManager([2020,2019,2018,2021], {'authors_openalex': True, 'sources_openalex':True})
    mngr.run()
    '''    from collections import defaultdict
        mongoclient = MusMongoClient()
        yeardict = defaultdict(int)
        for work in mongoclient.works_openalex.find():
            yeardict[work['publication_year']] += 1
        print(yeardict)'''
    import pandas as pd
    from polyfuzz.models import TFIDF
    from polyfuzz import PolyFuzz
    import datetime
    mongoclient = MusMongoClient()
    double_check_names = [
        'yang',
        'yi',
        'zhang',
        'zhao',
        'zhu',
        'zhou',
        'zhuang',
        'zhun',
        'zhuo',
        'zhuy',
        'zhang',
        'chen',
        'cheng',
        'chen',
        'chen',
        'liu',
        'yuan',
        'wang',
        'bu',
        'feng',
        'fu',
        'gu',
        'guo',
        'hao',
        'hu',
        'jia',
        'jiang',
        'jie',
        'jin',
        'jing',
        'jin',
        'jin',
        'li',
        'xiao',
        'xu',
        'wu',
        'lin',
        'ying'
    ]
    i=0
    j=0
    for author in mongoclient.authors_pure.find():
        j=j+1
        if author.get('openalex_match'):
            #delete the openalex_match field
            mongoclient.authors_pure.update_one({'author_name': author['author_name']}, {'$unset': {'openalex_match': ''}})
            i = i+1
    print(f'{i} of {j} authors have openalex match' )


    pureauthornamelist = []
    pureauthororcidlist = []
    totalpureauths = 0

    for a in mongoclient.authors_pure.find():
        totalpureauths = totalpureauths+1
        if a.get('affl_periods'):
            for period in a['affl_periods']:
                if not period['end_date'] or period['end_date'] > datetime.datetime(2020,1,1):
                    if a.get('author_orcid'):
                        pureauthororcidlist.append((a['author_orcid'], a['author_name']))
                    elif a['author_last_name'].lower() not in double_check_names and a['author_first_names'].lower() not in double_check_names:
                        pureauthornamelist.append(a['author_name'])

    pureauthornamelist = list(set(pureauthornamelist))
    pureauthororcidlist = list(set(pureauthororcidlist))
    print(f'{len(pureauthororcidlist)} of {totalpureauths} authors have orcid')
    print(f'{len(pureauthornamelist)} of {totalpureauths} authors included in name matching process')

    i = 0
    j = 0
    orcidsnotfound = []
    for author in pureauthororcidlist:
        j = j+1
        orcid = 'https://orcid.org/'+author[0]
        name = author[1]
        # find document in authors_openalex that matches the orcid
        openalex = mongoclient.authors_openalex.find_one({'ids.orcid': orcid})
        if not openalex:
            orcidsnotfound.append((orcid, name))
        if openalex:
            i = i+1
            mongoclient.authors_pure.update_one({'author_name': name}, {'$set': {'openalex_match': {'name':openalex['display_name'], 'id': openalex['id']}}})
    print(f'orcid matching results: {i} matches / {len(orcidsnotfound)} not found / {j} total')
    if orcidsnotfound:
        print('found orcids without openalex author data -- retrieving...')
        query = OpenAlexQuery(mongoclient, mongoclient.authors_openalex, 'authors')
        query.add_query_by_orcid([orcid[0] for orcid in orcidsnotfound])
        query.run()
        i=0
        j=0
        n=0
        for author in orcidsnotfound:
            j=j+1
            openalex = mongoclient.authors_openalex.find_one({'ids.orcid': author[0]})
            if openalex:
                i=i+1
                mongoclient.authors_pure.update_one({'author_name': author[1]}, {'$set': {'openalex_match': {'name':openalex['display_name'], 'id': openalex['id']}}})
            else:
                n=n+1
        print('retrieved authordata for missing orcids and matched to pure authors. result:')
        print(f'{i} matches / {n} not found / {j} total')


    from_list = pureauthornamelist
    to_list = [a['display_name'] for a in mongoclient.authors_openalex.find()]

    tfidf = TFIDF(n_gram_range=(3, 3), clean_string=True, min_similarity=0.7)
    model = PolyFuzz(tfidf)
    matchlist = model.match(from_list, to_list)
    results: pd.DataFrame = matchlist.get_matches()

    top_results=results[results['Similarity']>0.8]
    top_results_list=zip(top_results['From'].to_list(), top_results['To'].to_list())
    for from_name, to_name in top_results_list:
        openalexid = mongoclient.authors_openalex.find_one({'display_name': to_name})['id']
        mongoclient.authors_pure.update_one({'author_name': from_name}, {'$set': {'openalex_match': {'name':to_name, 'id': openalexid}}})
    i=0
    j=0
    for author in mongoclient.authors_pure.find():
        j=j+1
        if author.get('openalex_match'):
            #print(f'{author["author_name"]} matched to {author["openalex_match"]["name"]}')
            i = i+1
    print(f'{i} of {j} authors have openalex match' )



