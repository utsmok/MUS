from mus_wizard.harvester.base_classes import GenericAPI
from rich.table import Table
from rich.console import Console
from mus_wizard.constants import ROR
console = Console()

class DataCiteAPI(GenericAPI):
    def __init__(self, itemlist = None):
        super().__init__('items_datacite', 'doi', itemlist)
        self.set_api_settings(headers = {"accept": "application/vnd.api+json"},
                            max_per_second=5,
                            max_at_once=5,
                            )

    async def get_ut_items(self) -> None:
        ut_results = []
        url = f"https://api.datacite.org/dois?affiliation=true&query=creators.affiliation.affiliationIdentifier:%22{ROR}%22&page[size]=1000&affiliation=true&detail=true&publisher=true"
        try:
            response = await self.httpxclient.get(url, headers=self.api_settings['headers'])
            if response.status_code != 200:
                raise Exception(f"DataCite API response code {response.status_code}")
            response_json = response.json()
        except Exception as e:
            console.print(f'Error while retrieving all UT datacite items: {e}')
        for item in response_json["data"]:
            tmp={}
            attrs=item['attributes']
            for key, value in attrs.items():
                if value is not None:
                    if isinstance(value, list):
                        if value!=[]:
                            tmp[key]=value
                    elif isinstance(value, dict):
                        if value!={}:
                            tmp[key]=value
                    elif isinstance(value, str):
                        if value != "":
                            tmp[key]=value
            tmp['id']=item['id']
            tmp['type']=item['type']
            tmp['relationships']=item['relationships']
            ut_results.append(tmp)

        return ut_results
    async def make_itemlist(self) -> None:
        ptable = Table(title=f"{self.item_id_type}s from OpenAlex works")
        ptable.add_column("# checked", style="green")
        ptable.add_column("# added",style="magenta")
        i=0

        numpapers = await self.motorclient['works_openalex'].count_documents({})
        console.print(f'getting dois from {numpapers} openalexworks to find in datacite')

        async for paper in self.motorclient['works_openalex'].find(projection={'id':1, 'doi':1}):
            i+=1
            if paper.get('doi'):
                if await self.collection.find_one({'id':paper['id']}, projection={'id': 1}):
                    continue
                self.itemlist.append({self.item_id_type:paper['doi'].replace('https://doi.org/',''), 'id':paper['id']})
        ptable.add_row(str(i), str(len(self.itemlist)))
        console.print(ptable)

    async def call_api(self, item) -> dict:
        async def httpget(doi: str):
            try:
                url = f'https://api.datacite.org/dois?query=relatedIdentifiers.relatedIdentifier:{doi}&affiliation=true&publisher=true&detail=true'
                r = await self.httpxclient.get(url)
                return r.json()
            except Exception as e:
                console.print(f'error querying datacite for doi {doi}: {e}')
                return None
        doi = item.get('doi')
        id = item.get('id')
        result = await httpget(doi)
        if not result:
            return {'id': id, 'doi': doi}
        else:
            if result.get('meta').get('total') == 0:
                return {'id': id, 'doi': doi}
            result['id']=id
            return result