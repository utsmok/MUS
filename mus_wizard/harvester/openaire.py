from datetime import datetime, timedelta

import httpx
import motor.motor_asyncio
import xmltodict
from rich.console import Console
from rich.table import Table

from mus_wizard.constants import MONGOURL, OPENAIRETOKEN
from mus_wizard.harvester.base_classes import GenericAPI

console = Console()


class OpenAIREAPI(GenericAPI):
    def __init__(self, itemlist=None):
        '''
        Creates a new OpenAIREAPI instance
        call OpenAIREAPI().run() to execute standard queries & update mongodb -- no parameters needed.
        see docs for advanced usage.
        '''
        super().__init__('items_openaire', 'doi', itemlist)

        self.motorclient = motor.motor_asyncio.AsyncIOMotorClient(MONGOURL).metadata_unification_system
        self.collection = self.motorclient['items_openaire']
        self.refreshtime = datetime.now() - timedelta(hours=3)
        self.api_settings['tokens'] = {'refresh_token': OPENAIRETOKEN}

        accesstoken = ""
        self.set_api_settings(
            url='https://api.openaire.eu/search/researchProducts',
            headers={'Authorization': f'Bearer {accesstoken}'},
            tokens={'refresh_token': OPENAIRETOKEN,
                    },
            max_at_once=5,
            max_per_second=2
        )
        try:
            self.update_access_token(refresh=True)
        except Exception as e:
            console.print(f'error refreshing OpenAIRE access token: {e}')
            console.print(f'{self.api_settings=}')

    def update_access_token(self, refresh: bool = False) -> str:
        r = ''
        if refresh or datetime.now() - self.refreshtime > timedelta(minutes=45) or not self.api_settings['tokens'].get(
                'access_token'):
            try:
                self.refreshtime = datetime.now()
                r = httpx.get(
                    f'https://services.openaire.eu/uoa-user-management/api/users/getAccessToken?refreshToken={self.api_settings['tokens']['refresh_token']}')
                tokendata = r.json()
                self.api_settings['tokens']['access_token'] = tokendata.get("access_token")
                console.print('OpenAIRE access token updated')
                self.api_settings['headers'] = {
                    'Authorization': f'Bearer {self.api_settings["tokens"]["access_token"]}'}
            except Exception as e:
                console.print(f'error refreshing OpenAIRE access token: {e}')
                console.print(self.api_settings)
                console.print(r.text)
                raise LookupError('Cannot refresh OpenAIRE access token')
        return self.api_settings['tokens']['access_token']

    async def make_itemlist(self):
        ptable = Table(title=f"{self.item_id_type}s from OpenAlex works")
        ptable.add_column("# checked", style="green")
        ptable.add_column("# added", style="magenta")
        i = 0
        numpapers = await self.motorclient['works_openalex'].count_documents({})
        console.print(f'getting dois from {numpapers} openalexworks to find in openaire')

        async for paper in self.motorclient['works_openalex'].find({}, projection={'id': 1, 'doi': 1},
                                                                   sort=[('id', 1)]):
            i += 1
            if paper.get('doi'):
                if await self.collection.find_one({'id': paper['id']}, projection={'id': 1}):
                    continue
                self.itemlist.append(
                    {self.item_id_type: paper['doi'].replace('https://doi.org/', ''), 'id': paper['id']})
        ptable.add_row(str(i), str(len(self.itemlist)))
        console.print(ptable)

    async def call_api(self, item: dict) -> dict:
        async def httpget() -> dict | bool:
            params = {
                'doi': doi
            }
            r = await self.httpxclient.get(self.api_settings['url'], params=params,
                                           headers=self.api_settings['headers'])
            try:
                parsedxml = xmltodict.parse(r.text, attr_prefix='', dict_constructor=dict, cdata_key='text',
                                            process_namespaces=True)
            except Exception as e:
                console.print(f'error querying openaire for doi {item.get("doi")}: {e}')
                if 'token' in str(e):
                    self.update_access_token(refresh=True)
                    return await httpget()
                else:
                    return False
            if not parsedxml.get('response').get('results'):
                console.print(f'no results for {doi}')
                return False
            elif isinstance(parsedxml.get('response').get('results').get('result'), list):
                if len(parsedxml.get('response').get('results').get('result')) > 1:
                    console.print('multiple results (?) only returning the first')
                return parsedxml.get('response').get('results').get('result')[0].get('metadata').get(
                    'http://namespace.openaire.eu/oaf:entity').get('http://namespace.openaire.eu/oaf:result')
            else:
                return parsedxml.get('response').get('results').get('result').get('metadata').get(
                    'http://namespace.openaire.eu/oaf:entity').get('http://namespace.openaire.eu/oaf:result')

        id = item.get('id')
        doi = item.get('doi')
        result = await httpget()
        if not result == {}:
            result['id'] = id
            self.results['total'] += 1
            self.results['ids'].append(id)
            self.results['dois'].append(doi)
        else:
            result = {'id': id, 'doi': doi}
        return result
