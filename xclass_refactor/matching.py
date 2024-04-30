import pandas as pd
from polyfuzz.models import TFIDF
from polyfuzz import PolyFuzz
import datetime
from xclass_refactor.mus_mongo_client import MusMongoClient
from xclass_refactor.openalex_import import OpenAlexQuery
import motor.motor_asyncio
from xclass_refactor.constants import APIEMAIL, OPENAIRETOKEN, MONGOURL, ORCID_CLIENT_ID, ORCID_CLIENT_SECRET, ORCID_ACCESS_TOKEN

class AuthorMatcher():
    motorclient : motor.motor_asyncio.AsyncIOMotorClient = motor.motor_asyncio.AsyncIOMotorClient(MONGOURL).metadata_unificiation_system

    def __init__(self):
        self.double_check_names = [
            'yang','yi','zhang','zhao','zhu','zhou','zhuang','zhun','zhuo','zhuy','zhang',
            'chen','cheng','chen','chen','liu','yuan','wang','bu','feng','fu','gu','guo',
            'hao','hu','jia','jiang','jie','jin','jing','li','xiao','xu','wu','lin','ying'
        ]
        self.authornames = []
        self.authororcids = []

    async def get_authors(self):
        pureauthornamelist = []
        pureauthororcidlist = []
        async for a in self.motorclient.authors_pure.find():
            if a.get('openalex_match'):
                if not a.get('id') or a.get('id') != a.get('openalex_match').get('id'):
                    print(f"{a.get('author_pureid')}  --  {a.get('openalex_match')}  -- {a.get('id')}")
                    await self.motorclient.authors_pure.update_one({'_id': a.get('_id')}, {'$set': {'id': a.get('openalex_match').get('id')}})
            if a.get('affl_periods'):
                for period in a['affl_periods']:
                    if not period['end_date'] or period['end_date'] > datetime.datetime(2010,1,1):
                        if a.get('author_orcid'):
                            pureauthororcidlist.append((a['author_orcid'], a['author_name']))
                        elif a['author_last_name'].lower() not in self.double_check_names and a['author_first_names'].lower() not in self.double_check_names:
                            pureauthornamelist.append(a['author_name'])
        self.authornames = list(set(pureauthornamelist))
        self.authororcids = list(set(pureauthororcidlist))

    async def match_orcids(self):
        orcidsnotfound = []
        for author in self.authororcids:
            orcid = 'https://orcid.org/'+author[0]
            name = author[1]
            openalex = await self.motorclient.authors_openalex.find_one({'ids.orcid': orcid})
            if not openalex:
                orcidsnotfound.append((orcid, name))
            if openalex:
                await self.motorclient.authors_pure.update_one({'author_name': name}, {'$set': {'openalex_match': {'name':openalex['display_name'], 'id': openalex['id']}}})
        if orcidsnotfound:
            query = OpenAlexQuery(MusMongoClient(), MusMongoClient().authors_openalex, 'authors')
            query.add_query_by_orcid([orcid[0] for orcid in orcidsnotfound])
            await query.run()

            for author in orcidsnotfound:
                openalex = await self.motorclient.authors_openalex.find_one({'ids.orcid': author[0]})
                if openalex:
                    await self.motorclient.authors_pure.update_one({'author_name': author[1]}, {'$set': {'openalex_match': {'name':openalex['display_name'], 'id': openalex['id']}}})
    
    async def match_names(self):
        to_list = [a['display_name'] async for a in self.motorclient.authors_openalex.find()]
        tfidf = TFIDF(n_gram_range=(3, 3), clean_string=True, min_similarity=0.7)
        model = PolyFuzz(tfidf)
        matchlist = model.match(self.authornames, to_list)
        results: pd.DataFrame = matchlist.get_matches()
        top_results=results[results['Similarity']>0.8]
        top_results_list=zip(top_results['From'].to_list(), top_results['To'].to_list())
        for from_name, to_name in top_results_list:
            openalexid = await self.motorclient.authors_openalex.find_one({'display_name': to_name})
            openalexid = openalexid['id']
            await self.motorclient.authors_pure.update_one({'author_name': from_name}, {'$set': {'openalex_match': {'name':to_name, 'id': openalexid}, 'id': openalexid}})

    async def run(self):
        await self.get_authors()
        await self.match_orcids()
        await self.match_names()
