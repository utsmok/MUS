
from xclass_refactor.generics import GenericScraper
from collections import defaultdict
import aiometer
import functools
import pandas as pd
from polyfuzz.models import TFIDF
from polyfuzz import PolyFuzz
from rich import print, table

class PeoplePageScraper(GenericScraper):
    def __init__(self):
        super().__init__('employees_peoplepage')
        self.set_scraper_settings(url='https://people.utwente.nl/data/search',
                                headers = {
                                    "X-Requested-With": "XMLHttpRequest",
                                    "Host": "people.utwente.nl",
                                    "Referer": "https://people.utwente.nl",
                                    "Accept": "*/*",
                                    "Accept-Encoding": "gzip, deflate, br",
                                },
                                max_at_once=100,
                                max_per_second=20
                                )
    async def make_itemlist(self) -> None:
        async for author in self.motorclient['authors_openalex'].find({}, projection={'id':1, 'display_name':1, 'display_name_alternatives':1, 'ids':1, 'affiliations':1}, sort=[('id', 1)]):
            if author.get('affiliations'):
                for affl in author['affiliations']:
                    inst = affl.get('institution')
                    if inst:
                        if inst.get('ror')=='https://ror.org/006hf6230' or 'twente' in inst.get('display_name').lower():
                            if 2024 in affl.get('years') or 2023 in affl.get('years') or 2022 in affl.get('years'):
                                authordict = {}
                                authordict['id'] = author['id']
                                authordict['name'] = author['display_name']
                                authordict['name_alternatives']=author['display_name_alternatives']
                                authordict['ids']=author['ids']
                                self.itemlist.append(authordict)
        print(f'number of authors added: {len(self.itemlist)}')

    async def call_api(self, item) -> dict:
        async def get_data(id, searchname) -> list[dict]:
            try:
                r = await self.scraperclient.get(self.scraper_settings['url'], params={"query": searchname}, headers=self.scraper_settings['headers'])
            except Exception as e:
                print(f'error getting data for {searchname}: {e}')
                return None
            if r.status_code == 200:
                data = r.json()
                output=[]
                for entry in data['data']:
                    name = entry["name"] if entry["name"] is not None else ""
                    jobtitle = entry["jobtitle"] if entry["jobtitle"] is not None else ""
                    avatar = entry["avatar"] if entry["avatar"] is not None else ""
                    profile_url = entry["profile"] if entry["profile"] is not None else ""
                    email = entry["email"] if entry["email"] is not None else ""
                    deptlist = []
                    for dept in entry["organizations"]:
                        dept_faculty = (
                            dept["department"] if dept["department"] is not None else ""
                        )
                        dept_name = dept["section"] if dept["section"] is not None else ""
                        deptlist.append({"group": dept_name, "faculty": dept_faculty})
                    tmp = {
                            "searchname": searchname,
                            "foundname": name,
                            "position": jobtitle,
                            "avatar_url": avatar,
                            "profile_url": profile_url,
                            "email": email,
                            "grouplist": deptlist,
                            "id":id
                        }
                    output.append(tmp)
                return output
            else:
                return None

        names = []
        result_list = []
        return_value = {
                        'id':item.get('id'),
                        'name':item.get('name'),
                        'name_alternatives':item.get('name_alternatives')
                    }
        names.append(item.get('name'))
        if isinstance(item.get('name_alternatives'), list):
            names.extend(item.get('name_alternatives'))
        elif isinstance(item.get('name_alternatives'), str):
            names.append(item.get('name_alternatives'))

        async with aiometer.amap(functools.partial(get_data, item.get('id')), names) as result:
            if result:
                async for r in result:
                    if r is not None:
                        if len(r) == 1:
                            result_list.append(r[0])
                        elif len(r)>1:
                            for rr in r:
                                result_list.append(rr)

        #now find the best namematch in list of results
        if not result_list:
            return None
        to_list = [a['foundname'] for a in result_list]
        if not to_list:
            return None
        tfidf = TFIDF(n_gram_range=(3, 3), clean_string=True, min_similarity=0.8)
        model = PolyFuzz(tfidf)
        matchlist = model.match(names, to_list)
        results: pd.DataFrame = matchlist.get_matches()
        if results.empty:
            return None
        top_results=results[results['Similarity']>0.9]
        if top_results.empty:
            return None
        top_results.sort_values(by='Similarity', inplace=True, ascending=False)
        final_match = top_results.iloc[0]
        return_value['similarity'] = final_match['Similarity']
        for match in result_list:
            if match['foundname'] == final_match['To']:
                for k,v in match.items():
                    if k not in return_value:
                        return_value[k] = v
        self.collection.update_one({'id':item.get('id')}, {'$set':return_value}, upsert=True)
        self.results['total'] = self.results['total'] + 1
        self.results['items_added'].append(return_value['id'])

