from xclass_refactor.generics import GenericScraper
import urllib.parse
from bs4 import BeautifulSoup as bs
from rich import print, progress, console
import aiometer
import functools
from xclass_refactor.constants import JOURNAL_BROWSER_URL
class JournalBrowserScraper(GenericScraper):
    def __init__(self):
        super().__init__('deals_journalbrowser')
        self.set_scraper_settings(url=JOURNAL_BROWSER_URL,
                                max_at_once=100,
                                max_per_second=50
                                )
    async def make_itemlist(self) -> None:
        async for journal in self.motorclient['sources_openalex'].find({}, projection={'id':1, 'display_name':1, 'issn_l':1, 'issn':1}, sort=[('id', 1)]):
            tmp = {}
            tmp['id'] = journal['id']
            tmp['name'] = journal['display_name']
            if journal.get('issn_l'):
                if journal.get('issn_l') not in self.itemlist:
                    tmp['issn_l']=journal['issn_l']
            if journal.get('issn'):
                if journal.get('issn') not in self.itemlist:
                    tmp['issn']=journal['issn']
            self.itemlist.append(tmp)
        print(f'number of journals added: {len(self.itemlist)}')

    async def get_item_results(self) -> None:
        async with aiometer.amap(functools.partial(self.call_api), self.itemlist, max_at_once=self.scraper_settings['max_at_once'], max_per_second=self.scraper_settings['max_per_second']) as responses:
            async for response in responses:
                if response:
                    self.collection.update_one({'id':response['id']}, {'$set':response}, upsert=True)
                    self.results['total'] = self.results['total'] + 1
                    self.results['items_added'].append(response['id'])
    async def call_api(self, journal) -> dict:
        soup = {}
        query = (self.scraper_settings['url']
            + '?q="'
            + urllib.parse.quote(f"""{journal['name']}""")
            + f'"&wq_srt_desc=refs-and-pubs/referenties/aantal&wq_ofs={0}&wq_max=200'
        )
        try:
            page = await self.scraperclient.get(query)
        except Exception as e:
            return None
        if page.status_code == 200:
            content = page.text
            soup[journal['name']] = bs(content, "html.parser")
            titles = [
                x.contents
                for x in soup[journal['name']].find_all("a", title="more info")
            ]
            apc_deal = [
                x.contents
                for x in soup[journal['name']].find_all("a", class_="apc_discount")
            ]
            oa_types = [
                x["title"]
                for x in soup[journal['name']].find_all(
                    "li", class_="open_access opendialog_helpbusinessmodel"
                )
            ]
            urls = [
                x["href"]
                for x in soup[journal['name']].find_all("a", class_="apc_discount")
            ]
            keywords = [
                x.contents
                for x in soup[journal['name']].find_all("div", class_="keywords")
            ]
            publisher = [
                x.contents
                for x in soup[journal['name']].find_all("div", class_="author")
            ]
            issns = [
                x.contents
                for x in soup[journal['name']].find_all("div", class_="issns")
            ]

            for title, apc, keyword, publish, issn, url, oa_type in zip(
                titles, apc_deal, keywords, publisher, issns, urls, oa_types
            ):
                if journal['name'].lower() in title[0].lower():
                    if keyword == []:
                        keyword = [""]
                    if issn == []:
                        issn = [""]
                    if publish == []:
                        publish = [""]
                    if title == []:
                        title = [""]
                    if apc == []:
                        apc = [""]
                    if oa_type == []:
                        oa_type = ""
                    journalapc ={
                            "id":journal['id'],
                            "oa_display_name": journal['name'],
                            "oa_issn_l":journal.get('issn_l'),
                            "oa_issn":journal.get('issn'),
                            "title": title[0],
                            "APCDeal": apc[0],
                            "publisher": publish[0],
                            "keywords": [x.strip() for x in keyword[0].split("-") if x.strip() != ""],
                            "issns": [x.strip() for x in issn[0].strip("ISSN:").strip(')').strip().split('(') if x.strip() != ""],
                            "journal_browser_url": "".join(
                                ["https://library.wur.nl/WebQuery/", url]
                            ),
                            "oa_type": oa_type,
                        }
                    return journalapc
                else:
                    continue
            return None
        else:
            return None

