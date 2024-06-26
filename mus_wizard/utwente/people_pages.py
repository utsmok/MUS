import asyncio
import functools

import aiometer
import pandas as pd
from nameparser import HumanName
from polyfuzz import PolyFuzz
from polyfuzz.models import TFIDF
from rich import print
from bs4 import BeautifulSoup as bs
from mus_wizard.harvester.base_classes import GenericScraper


class PeoplePageScraper(GenericScraper):
    def __init__(self):
        super().__init__('employees_peoplepage')
        self.id = 1
        self.set_scraper_settings(url='https://people.utwente.nl/wh_services/utwente_ppp/rpc/',
                                  headers={
                                      "accept"            : "*/*",
                                      "accept-language"   : "en-US,en;q=0.9",
                                      "content-type"      : "application/json; charset=UTF-8",
                                      "priority"          : "u=1, i",
                                      "sec-ch-ua"         : "\"Google Chrome\";v=\"125\", \"Chromium\";v=\"125\", \"Not.A/Brand\";v=\"24\"",
                                      "sec-ch-ua-mobile"  : "?0",
                                      "sec-ch-ua-platform": "\"Windows\"",
                                      "sec-fetch-dest"    : "empty",
                                      "sec-fetch-mode"    : "cors",
                                      "sec-fetch-site"    : "same-origin",
                                      "referrer"          : "https://people.utwente.nl/overview?query=professor",
                                      "referrerPolicy"    : "strict-origin-when-cross-origin",
                                  },
                                  max_at_once=100,
                                  max_per_second=20
                                  )
        print('Currently the PeoplePageScraper is not working properly so the run() method just returns an empty dict.')

    async def run(self):
        return {}

    async def make_itemlist(self) -> None:
        async for author in self.motorclient['authors_openalex'].find({}, projection={'id'                       : 1,
                                                                                      'display_name'             : 1,
                                                                                      'display_name_alternatives': 1,
                                                                                      'ids'                      : 1,
                                                                                      'affiliations'             : 1},
                                                                      sort=[('id', 1)]):
            if author.get('affiliations'):
                for affl in author['affiliations']:
                    inst = affl.get('institution')
                    if inst:
                        if inst.get('ror') == 'https://ror.org/006hf6230' or 'twente' in inst.get(
                                'display_name').lower():
                            if 2024 in affl.get('years') or 2023 in affl.get('years') or 2022 in affl.get('years'):
                                authordict = {
                                    'id'               : author['id'],
                                    'name'             : author['display_name'],
                                    'name_alternatives': author['display_name_alternatives'],
                                    'ids'              : author['ids']
                                }
                                self.itemlist.append(authordict)
        print(f'number of authors added: {len(self.itemlist)}')

    async def call_api(self, item) -> dict | None:
        async def get_data(id, searchname) -> list[dict] | None:
            url = 'https://people.utwente.nl/wh_services/utwente_ppp/rpc/'
            body = {"id"    : self.id, "method": "SearchPersons",
                    "params": [{"query": f"{searchname}", "page": 0, "resultsperpage": 10000, "langcode": "en"}]}

            try:
                r = await self.scraperclient.post(url, headers=self.scraper_settings['headers'], json=body)
                data = r.json()
            except Exception as e:
                print(f'error getting data for {url}: {e}')
                print(r.request.content)
                print(r.request.headers)
                print(r.request.url)
                return None
            output = []
            self.id = self.id + 1
            try:
                soup = bs(data['result']['resultshtml'], 'html.parser')
            except Exception as e:
                print(f'error getting results for data: {data}')
                return None
            #print(soup.prettify())
            entries = soup.find_all('div', class_='ut-person-tile')
            for entry in entries:
                name = entry.find('h3', class_='ut-person-tile__title').text
                full_name = entry["name"] if entry["name"] is not None else ""
                first_name = entry["givenName"] if entry["givenName"] is not None else ""
                email = entry["mail"] if entry["mail"] is not None else ""
                avatar = entry.find('img', class_='ut-person-tile__image')['src']
                research = entry["researchUrl"] if entry["researchUrl"] is not None else ""
                profile = entry["profileUrl"] if entry["profileUrl"] is not None else ""
                jobtitle = entry["jobtitle"] if entry["jobtitle"] is not None else ""
                affiliation = entry["affiliation"] if entry["affiliation"] is not None else ""
                deptlist = entry['organizations'] if entry['organizations'] is not None else []

                deptlist = [x for x in deptlist if x['section'] is not None]

                checkname = HumanName(full_name)
                if first_name:
                    checkname.first = first_name

                tmp = {
                    "searchname"  : searchname,
                    "foundname"   : name,
                    "fullname"    : full_name,
                    'first_name'  : first_name,
                    "position"    : jobtitle,
                    "avatar_url"  : avatar,
                    "research_url": research,
                    "profile_url" : profile,
                    "email"       : email,
                    'affiliation' : affiliation,
                    "grouplist"   : deptlist,
                    "id"          : id,
                    'checkname'   : str(checkname)
                }
                output.append(tmp)
                print(tmp)
            return output

        names = []
        result_list = []
        return_value = {
            'id'               : item.get('id'),
            'name'             : item.get('name'),
            'name_alternatives': item.get('name_alternatives')
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
                        elif len(r) > 1:
                            for rr in r:
                                result_list.append(rr)

        # now find the best namematch in list of results
        if not result_list:
            return None
        to_list = [a['checkname'] for a in result_list]
        if not to_list:
            return None
        tfidf = TFIDF(n_gram_range=(3, 3), clean_string=True, min_similarity=0.8)
        model = PolyFuzz(tfidf)
        matchlist = model.match(names, to_list)
        results: pd.DataFrame = matchlist.get_matches()
        if results.empty:
            return None
        top_results = results[results['Similarity'] > 0.9]
        if top_results.empty:
            return None
        final_match = top_results.sort_values(by='Similarity', ascending=False).iloc[0]
        return_value['similarity'] = final_match['Similarity']
        for match in result_list:
            if match['checkname'] == final_match['To']:
                for k, v in match.items():
                    if k not in return_value:
                        return_value[k] = v
        await self.collection.update_one({'id': item.get('id')}, {'$set': return_value}, upsert=True)
        self.results['total'] = self.results['total'] + 1
        self.results['items_added'].append(return_value['id'])

