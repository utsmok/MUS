import re

import httpx
import xmltodict
from rich.console import Console
from rich.table import Table

from mus_wizard.constants import ORCID_CLIENT_ID, ORCID_CLIENT_SECRET
from mus_wizard.harvester.base_classes import GenericAPI

console = Console()


class ORCIDAPI(GenericAPI):

    def __init__(self, itemlist=None) -> None:
        super().__init__('items_orcid', 'orcid', itemlist)
        self.refresh_access_token()
        self.set_api_settings(headers={'Accept'       : 'application/orcid+xml',
                                       'Authorization': f'Bearer {self.api_settings['tokens']['access_token']}'},
                              max_at_once=10, max_per_second=10)
        self.NAMESPACES = {
            'http://www.orcid.org/ns/internal'           : 'internal',
            'http://www.orcid.org/ns/education'          : 'education',
            'http://www.orcid.org/ns/distinction'        : 'distinction',
            'http://www.orcid.org/ns/deprecated'         : 'deprecated',
            'http://www.orcid.org/ns/other-name'         : 'other-name',
            'http://www.orcid.org/ns/membership'         : 'membership',
            'http://www.orcid.org/ns/error'              : 'error',
            'http://www.orcid.org/ns/common'             : 'common',
            'http://www.orcid.org/ns/record'             : 'record',
            'http://www.orcid.org/ns/personal-details'   : 'personal-details',
            'http://www.orcid.org/ns/keyword'            : 'keyword',
            'http://www.orcid.org/ns/email'              : 'email',
            'http://www.orcid.org/ns/external-identifier': 'external-identifier',
            'http://www.orcid.org/ns/funding'            : 'funding',
            'http://www.orcid.org/ns/preferences'        : 'preferences',
            'http://www.orcid.org/ns/address'            : 'address',
            'http://www.orcid.org/ns/invited-position'   : 'invited-position',
            'http://www.orcid.org/ns/work'               : 'work',
            'http://www.orcid.org/ns/history'            : 'history',
            'http://www.orcid.org/ns/employment'         : 'employment',
            'http://www.orcid.org/ns/qualification'      : 'qualification',
            'http://www.orcid.org/ns/service'            : 'service',
            'http://www.orcid.org/ns/person'             : 'person',
            'http://www.orcid.org/ns/activities'         : 'activities',
            'http://www.orcid.org/ns/researcher-url'     : 'researcher-url',
            'http://www.orcid.org/ns/peer-review'        : 'peer-review',
            'http://www.orcid.org/ns/bulk'               : 'bulk',
            'http://www.orcid.org/ns/research-resource'  : 'research-resource'
        }

    def refresh_access_token(self) -> None:
        url = 'https://orcid.org/oauth/token'
        header = {'Accept': 'application/json'}
        data = {
            'client_id'    : ORCID_CLIENT_ID,
            'client_secret': ORCID_CLIENT_SECRET,
            'grant_type'   : 'client_credentials',
            'scope'        : '/read-public'
        }
        r = httpx.post(url, headers=header, data=data)
        self.api_settings['tokens']['access_token'] = r.json().get('access_token')
        self.api_settings['tokens']['refresh_token'] = r.json().get('refresh_token')

    async def make_itemlist(self) -> None:
        ptable = Table(title="Retrieved ORCID iDs")
        ptable.add_column("authors checked", style="cyan")
        ptable.add_column("orcids added to list", style="magenta")
        checked = 0
        async for auth in self.motorclient['authors_openalex'].find({'ids.orcid': {'$exists': True}},
                                                                    projection={'id': 1, 'ids': 1}):
            checked += 1
            if auth.get('ids').get('orcid'):
                check = await self.collection.find_one({'id': auth['id']}, projection={'id': 1, 'orcid-identifier': 1})
                if check:
                    if check.get('orcid-identifier'):
                        continue
                self.itemlist.append(
                    {self.item_id_type: auth['ids']['orcid'].replace('https://orcid.org/', ''), 'id': auth['id']})
        ptable.add_row(str(checked), str(len(self.itemlist)))
        console.print(ptable)

    async def call_api(self, item: dict) -> dict:
        async def httpget(item_id: str):
            def remove_colon_from_keys(item):
                if isinstance(item, dict):
                    newitem = {}
                    for key, value in item.items():
                        if ':' in key:
                            key = key.split(':')[-1]
                        newitem[key] = remove_colon_from_keys(value)
                    return newitem
                if isinstance(item, list):
                    return [remove_colon_from_keys(x) for x in item]
                else:
                    return item

            try:
                url = f'https://pub.orcid.org/v3.0/{item_id}/record'
                r = None
                r = await self.httpxclient.get(url, headers=self.api_settings['headers'])
                parsedxml = xmltodict.parse(r.text, process_namespaces=True, namespaces=self.NAMESPACES, attr_prefix='')
                if r.status_code == 301 or parsedxml.get(
                        'error:error') or '' in 'error xmlns="http://www.orcid.org/ns/error"' in r.text:
                    if parsedxml.get('error:developer-message'):
                        if 'Moved Permanently' in parsedxml.get('error:developer-message'):
                            msg = parsedxml.get('error:developer-message')
                            foundorcids = re.findall(r'(\w{4}-){3}\w{4}', msg)
                            neworcid = foundorcids[0]  # first found orcid should be  the new one
                            console.print(
                                f'[bold red]ORCID {item_id}[/bold red] moved permanently to [bold cyan]{neworcid}[/bold cyan] - retrying')
                            return await httpget(neworcid)
                record = parsedxml.get('record:record')
                del record['xmlns']
                del record['path']
                return remove_colon_from_keys(record)
            except Exception as e:
                console.print(f'error querying for ORCID {item_id}: {e}')
                return None

        result = await httpget(item[self.item_id_type])
        if isinstance(result, dict):
            result['id'] = item['id']
        if not result:
            return {'id': item['id']}
        return result
