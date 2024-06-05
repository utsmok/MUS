import functools
import time
from collections import defaultdict
from datetime import datetime
from typing import Any

import aiocsv
import aiofiles
import aiometer
import motor.motor_asyncio
import xmltodict
from rich import print
from rich.console import Console

from mus_wizard.constants import OAI_PMH_URL
from mus_wizard.database.mongo_client import MusMongoClient
from mus_wizard.harvester.base_classes import GenericAPI

cons = Console(markup=True)


class PureAPI(GenericAPI):
    # ! Note: check documentation for the correct namespaces and keys to use -- maybe switch to openaire cerif style??
    def __init__(self, years: list[int] = None):
        super().__init__('items_pure_oaipmh', 'doi', itemlist=None)
        if years:
            self.years: list[int] = years
        else:
            self.years: list[int] = [2022, 2023, 2024]
        self.years.sort(reverse=True)
        self.set_api_settings(max_at_once=5,
                              max_per_second=5)
        self.NAMESPACES = {
            "http://www.openarchives.org/OAI/2.0/"       : None,
            "http://www.openarchives.org/OAI/2.0/oai_dc/": None,
            'http://purl.org/dc/elements/1.1/'           : None,
            'http://www.w3.org/2001/XMLSchema-instance'  : None,
            'http://www.w3.org/XML/1998/namespace'       : None,
            'http://purl.org/dc/terms/'                  : None,
        }
        self.KEYS_TO_FIX = {
            'title'      : 'value',
            'subject'    : ['value'],
            'description': 'value',
        }

    async def run(self):
        await self.get_item_results()
        return self.results

    async def get_item_results(self) -> None:
        '''
        uses call_api() to get the result for each item in itemlist and puts them in the mongodb collection
        '''
        cons.print(f"calling api to get data for {self.item_id_type}s")
        async with aiometer.amap(functools.partial(self.call_api), self.years,
                                 max_at_once=self.api_settings['max_at_once'],
                                 max_per_second=self.api_settings['max_per_second']) as responses:
            # do something with the returned items?
            ...
        cons.print(f"finished gathering Pure Data for {self.years}")

    async def call_api(self, year) -> list[dict]:
        cons.print(f"gathering Pure Data for year {year}")

        async def fetch_response(url):
            async def remove_lang_fields(json):
                for key, value in json.items():
                    if key in self.KEYS_TO_FIX:
                        mapping = self.KEYS_TO_FIX[key]
                        if isinstance(mapping, str):
                            tmp = value['value']
                        elif isinstance(mapping, list):
                            tmp = []
                            for i in value:
                                tmp.append(i['value'])
                        json[key] = tmp
                return json

            try:
                r = await self.httpxclient.get(url)
                parsed = xmltodict.parse(r.text, process_namespaces=True, namespaces=self.NAMESPACES, attr_prefix="",
                                         cdata_key='value')
                parsed = await remove_lang_fields(parsed)
                return parsed['OAI-PMH']['ListRecords']
            except Exception as e:
                cons.print(f'error fetching {url}: {e}')
                return None

        base_url = OAI_PMH_URL
        metadata_prefix = "oai_dc"
        set_name = f"publications:year{year}"
        url = (
            f"{base_url}?verb=ListRecords&metadataPrefix={metadata_prefix}&set={set_name}"
        )
        while True:
            response = await fetch_response(url)
            if not response:
                time.sleep(5)
                continue
            results = []
            items = response.get('record')
            if not isinstance(items, list):
                items = [items]
            for result in items:
                del result['metadata']['dc']['xmlns']
                del result['metadata']['dc']['schemaLocation']
                temp = result['metadata']['dc']
                temp['pure_identifier'] = result['header']['identifier']
                temp['pure_datestamp'] = result['header']['datestamp']
                results.append(temp)

            if results:
                for result in results:
                    await self.collection.find_one_and_update({"pure_identifier": result['pure_identifier']},
                                                              {'$set': result}, upsert=True)
                    self.results['ids'].append(result['pure_identifier'])
                    self.results['total'] += 1
            if response.get('resumptionToken'):
                resumetoken = response.get('resumptionToken').get('value')
                url = f"{base_url}?verb=ListRecords&resumptionToken={resumetoken}"
                continue
            else:
                cons.print(f'no more pure results for year {year}')
                return True


class OAI_PMH(GenericAPI):
    OAI_PMH_VERBS = {
        'itemsets': 'ListSets',
        'schemas' : 'ListMetadataFormats',
        'records' : 'ListRecords',
        'identify': 'Identify',
    }

    def __init__(self, baseurl: str = None) -> None:
        collection = ''
        item_id_type = 'internal_repository_id'
        itemlist = None
        super().__init__(collection, item_id_type, itemlist)
        if not baseurl:
            baseurl = 'https://ris.utwente.nl/ws/oai'

        self.set_api_settings(
            url=baseurl,
            max_at_once=20,
            max_per_second=10,
        )

    # --------------------------------------------------------
    #                 CERIF MAPPING FUNCTIONS
    # --------------------------------------------------------
    #                      PERSONS
    # --------------------------------------------------------
    async def get_person_affiliations(self, values: list) -> tuple[str, list[dict]]:
        affiliations = []
        if isinstance(values, list):
            for v in values:
                tmp = v.get('cerif:OrgUnit')
                org = {
                    'internal_repository_id': tmp.get('@id'),
                    'name'                  : tmp.get('cerif:Name').get('#text'),
                }
                affiliations.append(org)
        elif isinstance(values, str):
            return values
        return 'affiliations', affiliations

    # --------------------------------------------------------
    #                 CERIF MAPPING FUNCTIONS
    # --------------------------------------------------------
    #                      ORGANIZATIONS
    # --------------------------------------------------------
    async def get_org_identifiers(self, values: list) -> tuple[str, dict[list]]:
        identifiers = defaultdict(list)
        if isinstance(values, list):
            for v in values:
                identifiers[v.get('@type')].append(v.get('#text'))
        return 'identifiers', identifiers

    async def get_org_part_of(self, value: dict | list) -> tuple[str, dict] | tuple[str, list[dict]]:
        try:
            if isinstance(value, dict):
                part_of = {
                    'internal_repository_id': value.get('cerif:OrgUnit').get('@id'),
                    'name'                  : value.get('cerif:OrgUnit').get('cerif:Name').get('#text'),
                }
            elif isinstance(value, list):
                part_of = []
                for v in value:
                    part_of.append({
                        'internal_repository_id': v.get('cerif:OrgUnit').get('@id'),
                        'name'                  : v.get('cerif:OrgUnit').get('cerif:Name').get('#text'),
                    })
        except Exception as e:
            print(f'error parsing {value}: {e}')
            part_of = None
        return 'part_of', part_of

    # --------------------------------------------------------
    #                 CERIF MAPPING FUNCTIONS
    # --------------------------------------------------------
    #                      WORKS
    # --------------------------------------------------------
    async def get_work_file_locations(self, cerif_medium: dict[list] | dict[dict]) -> tuple[str, list[dict] | None]:
        async def map_values(value: dict) -> dict:
            if not isinstance(value, dict):
                return None
            result = {
                'type'     : value.get('cerif:Type').get('#text') if value.get('cerif:Type') else None,
                'title'    : value.get('cerif:Title').get('#text') if value.get('cerif:Title') else None,
                'uri'      : value.get('cerif:URI'),
                'mime_type': value.get('cerif:MimeType'),
                'size'     : value.get('cerif:Size'),
                'access'   : value.get('ar:Access'),
            }
            return result

        if not isinstance(cerif_medium, dict):
            return 'file_locations', None
        value = cerif_medium.get('cerif:Medium')
        if isinstance(value, dict):
            return 'file_locations', [await map_values(value)]
        elif isinstance(value, list):
            return 'file_locations', [await map_values(v) for v in value]
        else:
            return 'file_locations', None

    async def get_work_published_in(self, cerif: dict[list] | dict[dict]) -> tuple[str, list[dict] | None]:
        async def map_values(value: dict) -> dict:
            if not isinstance(value, dict):
                return None
            title = value.get('cerif:Title')
            if title:
                if isinstance(title, dict):
                    title = title.get('#text')
                if isinstance(title, list):
                    title = [i.get('#text') for i in title]

            result = {
                'internal_repository_id': value.get('@id'),
                'type'                  : value.get('pubt:Type'),
                'title'                 : title,
            }
            return result

        fieldname = 'published_in'
        if not isinstance(cerif, dict) and not isinstance(cerif, list):
            return fieldname, None
        if isinstance(cerif, dict):
            return fieldname, [await map_values(cerif.get('cerif:Publication'))]
        elif isinstance(cerif, list):
            return fieldname, [await map_values(v.get('cerif:Publication')) for v in cerif]
        else:
            return fieldname, None

    async def get_work_isbn(self, cerif: dict[list] | dict[dict]) -> tuple[str, list[dict] | None]:
        fieldname = 'isbn'
        if not isinstance(cerif, dict) and not isinstance(cerif, list):
            return fieldname, None
        if isinstance(cerif, dict):
            return fieldname, [{'medium': cerif.get('@medium'), 'value': cerif.get('#text')}]
        elif isinstance(cerif, list):
            return fieldname, [{'medium': c.get('@medium'), 'value': c.get('#text')} for c in cerif]
        else:
            return fieldname, None

    async def get_work_references(self, cerif: dict[list] | dict[dict]) -> tuple[str, list[dict] | None]:
        async def map_values(value: dict) -> dict:
            if not isinstance(value, dict):
                return None
            title = value.get('cerif:Title')
            if title:
                if isinstance(title, dict):
                    title = title.get('#text')
                if isinstance(title, list):
                    title = [i.get('#text') for i in title]
            result = {
                'internal_repository_id': value.get('@id'),
                'peer_reviewed'         : value.get('pubt:Type').get('@pure:peerReviewed') if value.get(
                    'pubt:Type') else None,
                'publication_category'  : value.get('pubt:Type').get('@pure:publicationCategory') if value.get(
                    'pubt:Type') else None,
                'type'                  : value.get('pubt:Type').get('#text') if value.get('pubt:Type') else None,
                'title'                 : title,
            }
            return result

        fieldname = 'references'
        if not isinstance(cerif, dict) and not isinstance(cerif, list):
            return fieldname, None
        if isinstance(cerif, dict):
            return fieldname, [await map_values(cerif.get('cerif:Publication'))]
        elif isinstance(cerif, list):
            return fieldname, [await map_values(v.get('cerif:Publication')) for v in cerif]
        else:
            return fieldname, None

    async def get_work_originates_from(self, cerif: dict[list] | dict[dict]) -> tuple[str, list[dict] | None]:
        async def map_project_values(value: dict) -> dict:
            if not isinstance(value, dict):
                return None
            result = {
                'internal_repository_id': value.get('@id'),
                'title'                 : value.get('cerif:Title').get('#text'),
            }
            return result

        fieldname = 'originates_from'
        if not isinstance(cerif, dict) and not isinstance(cerif, list):
            return fieldname, None
        if isinstance(cerif, dict):
            if cerif.get('cerif:Funding'):
                return fieldname, [cerif.get('cerif:Funding').get('cerif:Description').get('#text')]
            elif cerif.get('cerif:Project'):
                return fieldname, [await map_project_values(cerif.get('cerif:Project'))]
        elif isinstance(cerif, list):
            results = []
            for c in cerif:
                if c.get('cerif:Funding'):
                    results.append(c.get('cerif:Funding').get('cerif:Description').get('#text'))
                elif c.get('cerif:Project'):
                    results.append(await map_project_values(c.get('cerif:Project')))
            return fieldname, results
        return fieldname, None

    async def get_work_publishers(self, cerif: dict[list] | dict[dict]) -> tuple[str, list[dict] | None]:
        if not isinstance(cerif, dict) and not isinstance(cerif, list):
            return 'publishers', None
        fieldname = 'publishers'
        try:
            if isinstance(cerif, dict):
                return fieldname, [cerif.get('cerif:Publisher').get('cerif:OrgUnit').get('cerif:Name').get('#text')]
            elif isinstance(cerif, list):
                return fieldname, [c.get('cerif:Publisher').get('cerif:OrgUnit').get('cerif:Name').get('#text') for c in
                                   cerif]
        except Exception as e:
            print(f'error parsing {cerif}: {e}')
            return fieldname, None

    async def get_work_presented_at(self, cerif: dict[list] | dict[dict]) -> tuple[str, list[dict] | None]:
        async def map_values(value: dict) -> dict:
            if not isinstance(value, dict):
                return None
            result = {
                'acronym'   : value.get('cerif:Acronym'),
                'name'      : value.get('cerif:Name').get('#text') if value.get('cerif:Name') else None,
                'start_date': value.get('cerif:StartDate'),
                'end_date'  : value.get('cerif:EndDate'),
                'place'     : value.get('cerif:Place'),
                'country'   : value.get('cerif:Country'),

            }
            return result

        fieldname = 'presented_at'
        if not isinstance(cerif, dict) and not isinstance(cerif, list):
            return fieldname, None
        if isinstance(cerif, dict):
            return fieldname, [await map_values(cerif.get('cerif:Event'))]
        elif isinstance(cerif, list):
            return fieldname, [await map_values(v.get('cerif:Event')) for v in cerif]
        else:
            return fieldname, None

    async def get_work_authors(self, cerif: dict[list] | dict[dict]) -> tuple[str, list[dict] | None]:
        async def map_values(value: dict) -> dict:
            if not isinstance(value, dict):
                return None
            result = {}
            affiliations = value.get('cerif:Affiliation')
            if affiliations:
                if isinstance(affiliations, dict):
                    affiliations = [affiliations]
                affils = []
                for affil in affiliations:
                    affils.append({
                        'internal_repository_id': affil.get('cerif:OrgUnit').get('@id') if affil.get(
                            'cerif:OrgUnit') else None,
                        'name'                  : affil.get('cerif:OrgUnit').get('cerif:Name').get(
                            '#text') if affil.get('cerif:OrgUnit') else None,
                        'acronym'               : affil.get('cerif:OrgUnit').get('cerif:Acronym') if affil.get(
                            'cerif:OrgUnit') else None,
                    })
                result['affiliations'] = affils
            person = value.get('cerif:Person')
            if person:
                result['internal_repository_id'] = person.get('@id')
                result['family_names'] = person.get('cerif:PersonName').get('cerif:FamilyNames') if person.get(
                    'cerif:PersonName') else None
                result['first_names'] = person.get('cerif:PersonName').get('cerif:FirstNames') if person.get(
                    'cerif:PersonName') else None
            return result

        fieldname = 'authors'
        cerif = cerif.get('cerif:Author')
        if not isinstance(cerif, dict) and not isinstance(cerif, list):
            return fieldname, None
        if isinstance(cerif, dict):
            return fieldname, [await map_values(cerif)]
        elif isinstance(cerif, list):
            return fieldname, [await map_values(v) for v in cerif]
        else:
            return fieldname, None

    async def get_work_editors(self, cerif: dict[list] | dict[dict]) -> tuple[str, list[dict] | None]:
        async def map_values(value: dict) -> dict:
            if not isinstance(value, dict):
                return None
            result = {}
            affiliations = value.get('cerif:Affiliation')
            if affiliations:
                if isinstance(affiliations, dict):
                    affiliations = [affiliations]
                affils = []
                for affil in affiliations:
                    affils.append({
                        'internal_repository_id': affil.get('@id'),
                        'name'                  : affil.get('cerif:Name').get('#text') if affil.get(
                            'cerif:Name') else None,
                        'acronym'               : affil.get('cerif:Acronym'),
                    })
                result['affiliations'] = affils
            person = value.get('cerif:Person')
            if person:
                result['internal_repository_id'] = person.get('@id')
                result['family_names'] = person.get('cerif:FamilyNames')
                result['first_names'] = person.get('cerif:FirstNames')
            return result

        fieldname = 'editors'
        cerif = cerif.get('cerif:Editor')
        if not isinstance(cerif, dict) and not isinstance(cerif, list):
            return fieldname, None
        if isinstance(cerif, dict):
            return fieldname, [await map_values(cerif)]
        elif isinstance(cerif, list):
            return fieldname, [await map_values(v) for v in cerif]
        else:
            return fieldname, None

    async def get_work_issn(self, cerif: dict[list] | dict[dict]) -> tuple[str, list[dict] | None]:
        fieldname = 'issn'
        if not isinstance(cerif, dict) and not isinstance(cerif, list):
            return fieldname, None
        if isinstance(cerif, dict):
            medium = cerif.get('@medium').split('#')[1]
            return fieldname, [{medium: cerif.get('#text')}]
        elif isinstance(cerif, list):
            return fieldname, [{v.get('@medium').split('#')[1]: v.get('#text')} for v in cerif]
        else:
            return fieldname, None

    async def get_work_keywords(self, cerif: dict[list] | dict[dict]) -> tuple[str, list[str] | None]:
        fieldname = 'keywords'
        if not isinstance(cerif, dict) and not isinstance(cerif, list):
            return fieldname, None
        if isinstance(cerif, dict):
            return fieldname, [cerif.get('#text')]
        elif isinstance(cerif, list):
            return fieldname, [v.get('#text') for v in cerif]
        else:
            return fieldname, None

    # --------------------------------------------------------
    #                 CERIF MAPPING FUNCTIONS
    # --------------------------------------------------------
    #                      DATASETS
    # --------------------------------------------------------
    async def get_dataset_file_locations(self, cerif_medium: dict[list] | dict[dict]) -> tuple[str, list[dict] | None]:
        async def map_values(value: dict) -> dict:
            if not isinstance(value, dict):
                return None
            result = {
                'type'     : value.get('cerif:Type').get('#text') if value.get('cerif:Type') else None,
                'title'    : value.get('cerif:Title').get('#text') if value.get('cerif:Title') else None,
                'uri'      : value.get('cerif:URI'),
                'mime_type': value.get('cerif:MimeType'),
                'size'     : value.get('cerif:Size'),
                'access'   : value.get('ar:Access'),
                'license'  : value.get('cerif:License').get('#text') if value.get('cerif:License') else None,
            }
            return result

        if not isinstance(cerif_medium, dict):
            return 'file_locations', None
        value = cerif_medium.get('cerif:Medium')
        if isinstance(value, dict):
            return 'file_locations', [await map_values(value)]
        elif isinstance(value, list):
            return 'file_locations', [await map_values(v) for v in value]
        else:
            return 'file_locations', None

    async def get_dataset_references(self, cerif: dict[list] | dict[dict]) -> tuple[str, list[dict] | None]:
        async def map_values(value: dict) -> dict:
            if not isinstance(value, dict):
                return None
            title = value.get('cerif:Title')
            if title:
                if isinstance(title, dict):
                    title = title.get('#text')
                if isinstance(title, list):
                    title = [i.get('#text') for i in title]
            result = {
                'internal_repository_id': value.get('@id'),
                'peer_reviewed'         : value.get('pubt:Type').get('@pure:peerReviewed') if value.get(
                    'pubt:Type') else None,
                'publication_category'  : value.get('pubt:Type').get('@pure:publicationCategory') if value.get(
                    'pubt:Type') else None,
                'type'                  : value.get('pubt:Type').get('#text') if value.get('pubt:Type') else None,
                'title'                 : title,
            }
            return result

        fieldname = 'references'
        if not isinstance(cerif, dict) and not isinstance(cerif, list):
            return fieldname, None
        if isinstance(cerif, dict):
            return fieldname, [await map_values(cerif.get('cerif:Publication'))]
        elif isinstance(cerif, list):
            return fieldname, [await map_values(v.get('cerif:Publication')) for v in cerif]
        else:
            return fieldname, None

    async def get_dataset_dates(self, cerif: dict[list] | dict[dict]) -> tuple[str, list[dict] | dict | None]:

        fieldname = 'dates'
        if not isinstance(cerif, dict) and not isinstance(cerif, list):
            result = None
        elif isinstance(cerif, dict):
            result = {}
            for date, vals in cerif.items():
                result[str(date).split(':')[1].lower()] = {'start': vals.get('@startDate'), 'end': vals.get('@endDate')}
            result = [result]
        elif isinstance(cerif, list):
            result = []
            for i in cerif:
                res = {}
                for date, vals in i.items():
                    res[str(date).split(':')[1].lower()] = {'start': vals.get('@startDate'),
                                                            'end'  : vals.get('@endDate')}
                result.append(res)
        return fieldname, result

    async def get_dataset_creators(self, cerif: dict[list] | dict[dict]) -> tuple[str, list[dict] | None]:
        async def map_values(value: dict) -> dict:
            if not isinstance(value, dict):
                return None
            result = {}
            affiliations = value.get('cerif:Affiliation')
            if affiliations:
                if isinstance(affiliations, dict):
                    affiliations = [affiliations]
                affils = []
                for affil in affiliations:
                    affils.append({
                        'internal_repository_id': affil.get('cerif:OrgUnit').get('@id') if affil.get(
                            'cerif:OrgUnit') else None,
                        'name'                  : affil.get('cerif:OrgUnit').get('cerif:Name').get(
                            '#text') if affil.get('cerif:OrgUnit') else None,
                        'acronym'               : affil.get('cerif:OrgUnit').get('cerif:Acronym') if affil.get(
                            'cerif:OrgUnit') else None,
                    })
                result['affiliations'] = affils
            person = value.get('cerif:Person')
            if person:
                result['internal_repository_id'] = person.get('@id')
                result['family_names'] = person.get('cerif:PersonName').get('cerif:FamilyNames') if person.get(
                    'cerif:PersonName') else None
                result['first_names'] = person.get('cerif:PersonName').get('cerif:FirstNames') if person.get(
                    'cerif:PersonName') else None
            return result

        fieldname = 'authors'
        if 'cerif:Creator' in cerif:
            cerif = cerif.get('cerif:Creator')
        if not isinstance(cerif, dict) and not isinstance(cerif, list):
            return fieldname, None
        if isinstance(cerif, dict):
            return fieldname, [await map_values(cerif)]
        elif isinstance(cerif, list):
            return fieldname, [await map_values(v) for v in cerif]
        else:
            return fieldname, None

    async def get_dataset_generated_by(self, cerif: dict[list] | dict[dict]) -> tuple[str, list[dict] | None]:
        fieldname = 'generated_by'
        if not isinstance(cerif, dict) and not isinstance(cerif, list):
            result = None
        elif isinstance(cerif, dict):
            result = [{
                'internal_repository_id': cerif.get('cerif:Equipment').get('@id') if cerif.get(
                    'cerif:Equipment') else None,
                'name'                  : cerif.get('cerif:Equipment').get('cerif:Name').get('#text') if cerif.get(
                    'cerif:Equipment') else None,
            }]
        elif isinstance(cerif, list):
            result = []
            for i in cerif:
                result.append({
                    'internal_repository_id': i.get('cerif:Equipment').get('@id') if i.get('cerif:Equipment') else None,
                    'name'                  : i.get('cerif:Equipment').get('cerif:Name').get('#text') if i.get(
                        'cerif:Equipment') else None,
                })
        return fieldname, result

    async def get_dataset_publishers(self, cerif: dict[list] | dict[dict]) -> tuple[str, list[dict] | None]:
        fieldname = 'publishers'
        cerif = cerif.get('cerif:Publisher')
        if not isinstance(cerif, dict) and not isinstance(cerif, list):
            result = None
        elif isinstance(cerif, dict):
            result = [{
                'internal_repository_id': cerif.get('cerif:OrgUnit').get('@id') if cerif.get('cerif:OrgUnit') else None,
                'name'                  : cerif.get('cerif:DisplayName'),
                'org_unit_name'         : cerif.get('cerif:OrgUnit').get('cerif:Name').get('#text') if cerif.get(
                    'cerif:OrgUnit') else None,
            }]
        elif isinstance(cerif, list):
            result = []
            for i in cerif:
                result.append({
                    'internal_repository_id': i.get('cerif:OrgUnit').get('@id') if i.get('cerif:OrgUnit') else None,
                    'name'                  : i.get('cerif:DisplayName'),
                    'org_unit_name'         : i.get('cerif:OrgUnit').get('cerif:Name').get('#text') if i.get(
                        'cerif:OrgUnit') else None,
                })
        return fieldname, result

    async def get_dataset_originates_from(self, cerif: dict[list] | dict[dict]) -> tuple[str, list[dict] | None]:
        async def map_values(value: dict) -> dict:
            funder = None
            funderdict = value.get('cerif:Funder')

            if funderdict:
                funder = {
                    'internal_repository_id': funderdict.get('cerif:OrgUnit').get('@id') if funderdict.get(
                        'cerif:OrgUnit') else None,
                    'acronym'               : funderdict.get('cerif:OrgUnit').get('cerif:Acronym') if funderdict.get(
                        'cerif:OrgUnit') else None,
                    'name'                  : funderdict.get('cerif:OrgUnit').get('cerif:Name').get(
                        '#text') if funderdict.get('cerif:OrgUnit') else None,
                }
            return {
                'internal_repository_id': value.get('cerif:Equipment').get('@id') if value.get(
                    'cerif:Equipment') else None,
                'funder'                : funder,
                'identifier'            : value.get('cerif:Identifier').get('#text') if value.get(
                    'cerif:Identifier') else None,
                'identifier_type'       :
                    value.get('cerif:Identifier').get('@type').split('/dk/atira/funding/fundingdetails/')[
                        -1] if value.get('cerif:Identifier') else None,
                'type'                  : value.get('funt:Type').split('#')[-1] if value.get('funt:Type') else None,
            }

        fieldname = 'originates_from'
        if not isinstance(cerif, dict) and not isinstance(cerif, list):
            result = None
        elif isinstance(cerif, dict):
            result = [await map_values(cerif)]
        elif isinstance(cerif, list):
            result = []
            for i in cerif:
                result.append(await map_values(i))
        return fieldname, result

    # Check keys for missing values in cerif mapping
    async def check_keys(self, item, keylist) -> list[str]:
        missing_keys = []
        for k in item.keys():
            if k.startswith('cerif:') and k not in keylist:
                missing_keys.append(k)
        return missing_keys

    async def process_cerif(self, type: str, data: list[dict]) -> tuple[list[dict], set[str]]:
        keys_missing = set()
        results = []
        mapping = self.CERIF_RESULT_KEY_MAPPING[type]
        keylist = self.CERIF_RESULT_KEYLIST[type]
        for i in data:
            try:
                item = i['metadata'].get(self.CERIF_ITEM_MAPPING[type])
            except Exception as e:
                print(f'error processing cerif data for {type}: {e}')
                continue
            result = {}
            if not item:
                continue
            for key, value in mapping.items():
                try:
                    if isinstance(value, str):
                        result[key] = item.get(value)
                    elif isinstance(value, dict):
                        temp = item.get(key)

                        if temp:
                            if isinstance(temp, list):
                                for k, v in value.items():
                                    result[k] = []
                                    for u in temp:
                                        try:
                                            result[k].append(u.get(v))
                                        except Exception:
                                            ...
                            elif isinstance(temp, dict):
                                for k, v in value.items():
                                    result[k] = temp.get(v)
                    elif callable(value):
                        item_result = item.get(key)
                        if item_result:
                            keyname, fullvalue = await value(self, item_result)
                            result[keyname] = fullvalue
                except Exception as e:
                    print(f'error {e} processing {key, value} for {type}. Full item: {item}')
            missing = await self.check_keys(item, keylist)
            if missing:
                [keys_missing.add(m) for m in missing]
            results.append(result)
        return results, keys_missing

    async def get_results(self, type: str, url: str, collection: motor.motor_asyncio.AsyncIOMotorCollection) -> dict[
        str, list[Any] | Any]:
        results = {
            'raw'         : [],
            'processed'   : [],
            'missing_keys': [],
        }

        async def fetch_response(url):
            try:
                r = await self.httpxclient.get(url)
                parsed = xmltodict.parse(r.text)
                return parsed['OAI-PMH']['ListRecords']
            except Exception as e:
                print(f'error fetching {url}: {e}')
                return None

        resume_url = url.split('&metadataPrefix')[0]
        while True:
            response = await fetch_response(url)
            if not response:
                time.sleep(5)
                continue
            items = response.get('record')
            raw_results = []
            if not isinstance(items, list):
                items = [items]
            for result in items:
                raw_results.append(result)
            tmp = await self.process_cerif(type, raw_results)
            results['processed'].extend(tmp[0])
            results['missing_keys'].extend(tmp[1])
            results['missing_keys'] = list(set(results['missing_keys']))
            try:
                for subitem in tmp[0]:
                    await collection.find_one_and_update({"internal_repository_id": subitem['internal_repository_id']},
                                                         {'$set': subitem}, upsert=True)
            except Exception as e:
                print('probably missing internal_repository_id field')
                print(f'error inserting {type} records: {e}')
            if response.get('resumptionToken'):
                print(
                    f'{response.get('resumptionToken').get('@cursor')}/{response.get("resumptionToken").get("@completeListSize")}')
                resumetoken = response.get('resumptionToken').get('#text')
                url = f"{resume_url}&resumptionToken={resumetoken}"
            else:
                return results

    async def get_item_results(self):
        # 'products':'openaire_cris_products', 'patents':'openaire_cris_patents', 'projects':'openaire_cris_projects', 'funding':'openaire_cris_funding'
        # 'works': 'openaire_cris_publications', 'persons': 'openaire_cris_persons', 'orgs' : 'openaire_cris_orgunits',
        all_itemsets = {'datasets': 'datasets:all'}
        itemsets = [(k, v) for k, v in all_itemsets.items()]

        async with aiometer.amap(functools.partial(self.call_api), itemsets,
                                 max_at_once=self.api_settings['max_at_once'],
                                 max_per_second=self.api_settings['max_per_second']) as responses:
            async for response in responses:
                cons.print(f'finished getting results {response}')

    async def call_api(self, item) -> str:
        scheme = 'oai_cerif_openaire'
        type = item[0]
        itemset = item[1]
        url = f'{self.api_settings["url"]}?verb=ListRecords&metadataPrefix={scheme}&set={itemset}'
        collectionname = f'{itemset}'
        collection: motor.motor_asyncio.AsyncIOMotorCollection = self.motorclient.collectionname
        cons.print(f'processing {type} records from {url}, storing in collection {itemset}')
        start_time = time.time()
        results = await self.get_results(type, url, collection)
        end_time = time.time()
        self.results['total']+=len(results['processed'])
        return f'Inserted {len(results['processed'])} {type} records into {collectionname} in {int(end_time - start_time)} seconds. Possible missing keys: {results["missing_keys"]}'

    # mus internal type name : cerif type name
    CERIF_ITEM_MAPPING = {
        'persons' : 'cerif:Person',
        'orgs'    : 'cerif:OrgUnit',
        'works'   : 'cerif:Publication',
        'products': 'cerif:Product',
        'patents' : 'cerif:Patent',
        'datasets': 'cerif:Product',
        'projects': 'cerif:Project',
        'funding' : 'cerif:Funding',
    }

    # this indicates how a cerif result is mapped to the stored mongodb item
    CERIF_RESULT_KEY_MAPPING = {
        'persons'            : {
            'internal_repository_id': '@id',
            'cerif:PersonName'      : {'family_names': 'cerif:FamilyNames', 'first_names': 'cerif:FirstNames'},
            'orcid'                 : 'cerif:ORCID',
            'scopus_id'             : 'cerif:ScopusAuthorID',
            'scopus_affil_id'       : 'cerif:ScopusAffiliationID',
            'cerif:Affiliation'     : get_person_affiliations,
            'researcher_id'         : 'cerif:ResearcherID',
            'isni'                  : 'cerif:ISNI',
            'cris-id'               : 'cerif:CRIS-ID',
            'uuid'                  : 'cerif:UUID',
            'uri'                   : 'cerif:URI',
            'url'                   : 'cerif:URL',
        },
        'orgs'               : {
            'internal_repository_id': '@id',
            'cerif:Identifier'      : get_org_identifiers,
            'cerif:Type'            : {'type': '#text'},
            'cerif:PartOf'          : get_org_part_of,
            'cerif:Name'            : {'name': '#text'},
            'acronym'               : 'cerif:Acronym',
            'url'                   : 'cerif:ElectronicAddress'
        },
        'datasets'           : {
            'internal_repository_id': '@id',
            'cerif:FileLocations'   : get_dataset_file_locations,
            'cerif:Name'            : {'name': '#text'},
            'cerif:Description'     : {'description': '#text'},
            'cerif:References'      : get_dataset_references,
            'cerif:Dates'           : get_dataset_dates,
            'url'                   : 'cerif:URL',
            'cerif:Creators'        : get_dataset_creators,
            'cerif:GeneratedBy'     : get_dataset_generated_by,
            'doi'                   : 'cerif:DOI',
            'cerif:License'         : {'license': '#text'},
            'cerif:Publishers'      : get_dataset_publishers,
            'cerif:OriginatesFrom'  : get_dataset_originates_from,
        },

        # possible fields to add:  ['cerif:PublishedIn']
        'works'              : {
            'cerif:Subtitle'        : {'subtitle': '#text'},
            'cerif:FileLocations'   : get_work_file_locations,
            'cerif:Publication'     : get_work_published_in,
            'cerif:ISBN'            : get_work_isbn,
            'volume'                : 'cerif:Volume',
            'language'              : 'cerif:Language',
            'number'                : 'cerif:Number',
            'cerif:References'      : get_work_references,
            'cerif:OriginatesFrom'  : get_work_originates_from,
            'start_page'            : 'cerif:StartPage',
            'edition'               : 'cerif:Edition',
            'cerif:Status'          : {'status': '#text'},
            'cerif:License'         : {'license': '#text'},
            'cerif:Title'           : {'title': '#text'},
            'issue'                 : 'cerif:Issue',
            'cerif:Publishers'      : get_work_publishers,
            'cerif:Abstract'        : {'abstract': '#text'},
            'isi'                   : 'cerif:ISI-Number',
            'cerif:PresentedAt'     : get_work_presented_at,
            'publication_date'      : 'cerif:PublicationDate',
            'cerif:Authors'         : get_work_authors,
            'scp_number'            : 'cerif:SCP-Number',
            'part_of'               : 'cerif:PartOf',
            'endpage'               : 'cerif:EndPage',
            'url'                   : 'cerif:URL',
            'doi'                   : 'cerif:DOI',
            'cerif:Editors'         : get_work_editors,
            'cerif:ISSN'            : get_work_issn,
            'cerif:Keyword'         : get_work_keywords,
            'internal_repository_id': '@id',
        },
        'products'           : {
            'internal_repository_id': '@id',
            'presented_at'          : 'cerif:PresentedAt',
            'keywords'              : 'cerif:Keyword',
            'filelocations'         : 'cerif:FileLocations',
            'name'                  : 'cerif:Name',
            'description'           : 'cerif:Description',
            'references'            : 'cerif:References',
            'dates'                 : 'cerif:Dates',
            'url'                   : 'cerif:URL',
            'creators'              : 'cerif:Creators',
            'generated_by'          : 'cerif:GeneratedBy',
            'doi'                   : 'cerif:DOI',
            'license'               : 'cerif:License',
            'publishers'            : 'cerif:Publishers',
            'originates_from'       : 'cerif:OriginatesFrom',
        },
        'patents'            : {
            'internal_repository_id': '@id',
            'subject'               : 'cerif:Subject',
            'keywords'              : 'cerif:Keyword',
            'references'            : 'cerif:References',
            'abstract'              : 'cerif:Abstract',
            'issuer'                : 'cerif:Issuer',
            'approval_date'         : 'cerif:ApprovalDate',
            'title'                 : 'cerif:Title',
            'countrycode'           : 'cerif:CountryCode',
            'patentnumber'          : 'cerif:PatentNumber',
            'inventors'             : 'cerif:Inventors'
        },
        'projects'           : {
            'internal_repository_id': '@id',
            'enddate'               : 'cerif:EndDate',
            'consortium'            : 'cerif:Consortium',
            'startdate'             : 'cerif:StartDate',
            'keywords'              : 'cerif:Keyword',
            'title'                 : 'cerif:Title',
            'acronym'               : 'cerif:Acronym',
            'abstract'              : 'cerif:Abstract',
            'identifier'            : 'cerif:Identifier',
            'team'                  : 'cerif:Team',
        },
        'funding'            : {
            'internal_repository_id': '@id',
            'name'                  : 'cerif:Name',
            'description'           : 'cerif:Description',
            'funder'                : 'cerif:Funder',
            'acronym'               : 'cerif:Acronym',
        },
        'ec_funded_resources': {},
    }

    # a list of cerif fields that are processed -- might be incomplete, check later.
    # this list is used to check if a field is in the item but not in the mapping
    CERIF_RESULT_KEYLIST = {
        'persons'            : ['@id', 'cerif:PersonName', 'cerif:Affiliation', 'cerif:PersonName', 'cerif:Affiliation',
                                'cerif:ORCID', 'cerif:ScopusAuthorID', 'cerif:ScopusAffiliationID',
                                'cerif:ResearcherID', 'cerif:ISNI', 'cerif:CRIS-ID', 'cerif:UUID', 'cerif:URI',
                                'cerif:URL'],
        'orgs'               : ['cerif:Identifier', 'cerif:Type', 'cerif:PartOf', 'cerif:Name', 'cerif:Acronym'],
        'works'              : ['cerif:Keyword', 'cerif:Editors', 'cerif:Subtitle', 'cerif:Publishers', 'cerif:Authors',
                                'cerif:DOI', 'cerif:ISBN', 'cerif:URL', 'cerif:SCP-Number', 'cerif:Title',
                                'cerif:Status', 'cerif:FileLocations', 'cerif:PresentedAt', 'cerif:References',
                                'cerif:Abstract', 'cerif:Language', 'cerif:PublicationDate'],
        'datasets'           : ['cerif:Creators', 'cerif:Name', 'cerif:GeneratedBy', 'cerif:FileLocations',
                                'cerif:Dates', 'cerif:OriginatesFrom', 'cerif:DOI', 'cerif:URL', 'cerif:References',
                                'cerif:Publishers', 'cerif:License', 'cerif:Description'],
        'products'           : [],
        'patents'            : [],
        'projects'           : [],
        'funding'            : [],
        'ec_funded_resources': [],
    }


class PureAuthorCSV():
    '''
    read in a csv file exported from Pure containing author details
    and store the data in MongoDB
    '''

    def __init__(self, filepath: str = 'eemcs_author_details.csv'):
        self.filepath = filepath
        self.mongoclient = MusMongoClient()
        self.collection = self.mongoclient.authors_pure
        self.results = {'total': 0}

    async def run(self):
        pureids = []
        async for item in self.collection.find(projection={'author_pureid': 1}):
            if item['author_pureid'] not in pureids:
                pureids.append(item['author_pureid'])
            else:
                await self.collection.delete_one({'author_pureid': item['author_pureid']})
        async with aiofiles.open(self.filepath, 'r', encoding='utf-8') as f:
            cons.print(f"reading in {self.filepath}")
            async for row in aiocsv.AsyncDictReader(f):
                for key, value in row.items():
                    if 'affl_periods' in key:
                        # data looks like this: '1/01/81 → 1/01/18 | 2/08/01 → 2/08/01'
                        list_affl_periods = [i.strip() for i in value.split('|')]
                        new_value = []
                        for item in list_affl_periods:
                            formatted_dates = [i.strip() for i in item.split('→')]
                            for i, date in enumerate(formatted_dates):
                                if date != '…':
                                    splitted_date = date.split('/')
                                    if len(splitted_date[0]) == 1:
                                        splitted_date[0] = '0' + splitted_date[0]
                                    formatted_dates[i] = datetime.strptime('/'.join(splitted_date), '%d/%m/%y')
                                else:
                                    formatted_dates[i] = None
                            dictform = {'start_date': formatted_dates[0], 'end_date': formatted_dates[1]}
                            new_value.append(dictform)
                        row[key] = new_value
                    elif 'date' in key or 'modified' in key:
                        if row[key]:
                            row[key] = [datetime.strptime(i.strip().split(' ')[0], '%Y-%m-%d') for i in
                                        value.split('|')]
                    elif '|' in value:
                        row[key] = [i.strip() for i in value.split('|')]

                if row['author_pureid'] not in pureids:
                    await self.collection.insert_one(row)
                    self.results['total'] = self.results['total'] + 1
        cons.print(f"finished reading in {self.filepath}")
        return self.results
