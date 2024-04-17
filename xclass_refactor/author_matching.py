import pandas as pd
from polyfuzz.models import TFIDF
from polyfuzz import PolyFuzz
import datetime
from xclass_refactor.mus_mongo_client import MusMongoClient
from xclass_refactor.openalex_import import OpenAlexQuery

class AuthorMatcher():
    def __init__(self, mongoclient: MusMongoClient):
        self.self.mongoclient = mongoclient
        self.double_check_names = [
            'yang','yi','zhang','zhao','zhu','zhou','zhuang','zhun','zhuo','zhuy','zhang',
            'chen','cheng','chen','chen','liu','yuan','wang','bu','feng','fu','gu','guo',
            'hao','hu','jia','jiang','jie','jin','jing','li','xiao','xu','wu','lin','ying'
        ]
        self.authornames = []
        self.authororcids = []

    def get_authors(self):
        pureauthornamelist = []
        pureauthororcidlist = []
        for a in self.self.mongoclient.authors_pure.find():
            if a.get('affl_periods'):
                for period in a['affl_periods']:
                    if not period['end_date'] or period['end_date'] > datetime.datetime(2010,1,1):
                        if a.get('author_orcid'):
                            pureauthororcidlist.append((a['author_orcid'], a['author_name']))
                        elif a['author_last_name'].lower() not in self.double_check_names and a['author_first_names'].lower() not in self.double_check_names:
                            pureauthornamelist.append(a['author_name'])
        self.authornames = list(set(pureauthornamelist))
        self.authororcids = list(set(pureauthororcidlist))

    def match_orcids(self):
        orcidsnotfound = []
        for author in self.authororcids:
            orcid = 'https://orcid.org/'+author[0]
            name = author[1]
            openalex = self.mongoclient.authors_openalex.find_one({'ids.orcid': orcid})
            if not openalex:
                orcidsnotfound.append((orcid, name))
            if openalex:
                self.mongoclient.authors_pure.update_one({'author_name': name}, {'$set': {'openalex_match': {'name':openalex['display_name'], 'id': openalex['id']}}})
        if orcidsnotfound:
            query = OpenAlexQuery(self.mongoclient, self.mongoclient.authors_openalex, 'authors')
            query.add_query_by_orcid([orcid[0] for orcid in orcidsnotfound])
            query.run()

            for author in orcidsnotfound:
                openalex = self.mongoclient.authors_openalex.find_one({'ids.orcid': author[0]})
                if openalex:
                    self.mongoclient.authors_pure.update_one({'author_name': author[1]}, {'$set': {'openalex_match': {'name':openalex['display_name'], 'id': openalex['id']}}})
    
    def match_names(self):
        to_list = [a['display_name'] for a in self.mongoclient.authors_openalex.find()]
        tfidf = TFIDF(n_gram_range=(3, 3), clean_string=True, min_similarity=0.7)
        model = PolyFuzz(tfidf)
        matchlist = model.match(self.authornames, to_list)
        results: pd.DataFrame = matchlist.get_matches()
        top_results=results[results['Similarity']>0.8]
        top_results_list=zip(top_results['From'].to_list(), top_results['To'].to_list())
        for from_name, to_name in top_results_list:
            openalexid = self.mongoclient.authors_openalex.find_one({'display_name': to_name})['id']
            self.mongoclient.authors_pure.update_one({'author_name': from_name}, {'$set': {'openalex_match': {'name':to_name, 'id': openalexid}}})

    def run(self):
        self.get_authors()
        self.match_orcids()
        self.match_names()
