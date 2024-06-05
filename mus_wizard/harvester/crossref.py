import xmltodict
from habanero import Crossref
from rich.console import Console
from rich.table import Table

from mus_wizard.constants import APIEMAIL
from mus_wizard.harvester.base_classes import GenericAPI

console = Console()


class CrossrefAPI(GenericAPI):
    '''
    TODO: import xml data instead of json, see https://www.crossref.org/documentation/retrieve-metadata/xml-api/doi-to-metadata-query/
    '''

    def __init__(self, itemlist=None):
        super().__init__('items_crossref', 'doi', itemlist)
        self.set_api_settings(headers={"accept": "application/vnd.api+json"},
                              max_per_second=5,
                              max_at_once=5,
                              )
        self.crossref = Crossref(mailto=APIEMAIL)
        self.pagesize = 100

    async def make_itemlist(self) -> None:
        ptable = Table(title=f"{self.item_id_type}s from OpenAlex works")
        ptable.add_column("# checked", style="green")
        ptable.add_column("# added", style="magenta")
        i = 0

        numpapers = await self.motorclient['works_openalex'].count_documents({})
        console.print(f'getting dois from {numpapers} openalexworks to find in crossref')

        async for paper in self.motorclient['works_openalex'].find(projection={'id': 1, 'doi': 1}):
            i += 1
            if paper.get('doi'):
                if await self.collection.find_one({'id': paper['id']}, projection={'id': 1}):
                    continue
                self.itemlist.append(
                    {self.item_id_type: paper['doi'].replace('https://doi.org/', ''), 'id': paper['id']})
        ptable.add_row(str(i), str(len(self.itemlist)))
        console.print(ptable)

    async def call_api(self, item):
        async def addrecord(record, openalexid, doi):
            item = None
            if record:
                if record['crossref'].get('error'):
                    return None
                if record['crossref'].get('journal'):
                    item = record['crossref']['journal']
                elif record['crossref'].get('conference'):
                    item = record['crossref']['conference']
                elif record['crossref'].get('book'):
                    item = record['crossref']['book']
                elif record['crossref'].get('posted_content'):
                    item = record['crossref']['posted_content']
                elif record['crossref'].get('peer_review'):
                    item = record['crossref']['peer_review']
                elif record['crossref'].get('database'):
                    item = record['crossref']['database']['dataset']
                elif record['crossref'].get('dissertation'):
                    item = record['crossref']['dissertation']
                elif record['crossref'].get('report-paper'):
                    item = record['crossref']['report-paper']['report-paper_metadata']
                if not item:
                    console.print(f'no journal, book, or conference for doi {doi}')
                    return None
                else:
                    item['id'] = openalexid
                    return item

        url = f'https://doi.crossref.org/servlet/query?pid={APIEMAIL}&format=unixref&id={item['doi']}'
        results = []
        try:
            r = await self.httpxclient.get(url)
            data = xmltodict.parse(r.text, attr_prefix='', dict_constructor=dict)
        except Exception as e:
            console.print(f'error querying crossref for doi {item['doi']}: {e}')
        try:
            if data.get('doi_records'):
                if isinstance(data.get('doi_records'), list):
                    for record in data.get('doi_records'):
                        result = await addrecord(record, item['id'], item['doi'])
                        if not result:
                            result = {'id': item['id'], 'doi': item['doi']}
                        results.append(result)
                else:
                    result = await addrecord(data.get('doi_records').get('doi_record'), item['id'], item['doi'])
                    if not result:
                        result = {'id': item['id'], 'doi': item['doi']}

                    results.append(result)
        except Exception as e:
            console.print(f'error storing crossref result for doi {item['doi']}: {e}')

        return results
