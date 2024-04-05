from loguru import logger
from django.conf import settings
from pymongo import MongoClient
import xmltodict
from rich import print
import csv
from collections import defaultdict
from datetime import datetime
import PureOpenAlex.constants


MONGOURL = getattr(settings, "MONGOURL")

client=MongoClient(MONGOURL)
db=client['mus']
mongo_dblp_raw=db['file_dblp_raw']
mongo_pure_report_start_tcs=db['pure_report_start_tcs']
mongo_pure_report_ee=db['pure_report_ee']
mongo_pure_xmls=db['pure_xmls']
pure_cerif_authors = db['pure_cerif_authors']
pure_cerif_works = db['pure_cerif_works']
pure_cerif_journals = db['pure_cerif_journals']
pure_cerif_categories = db['pure_cerif_categories']
pure_org_mapping = db['pure_org_mapping']

'''
============================================================
IMPORT PURE AUTHOR DATA FROM REPORT CSV EXPORT
============================================================
'''
def import_pure_author_csv(filename='eemcs_author_details.csv'):
    '''
    read in pure report with author details incl org/affil details
    
    '''
    with open(filename, encoding='utf-8') as f:
        data = csv.DictReader(f)
        matched = 0
        nomatch = 0
        total = 0
        for row in data:
            authordict = dict()
            total += 1
            for key, value in row.items():
                if '|' in value:
                    value = value.split('|')
                    value = [v.strip() for v in value]
                    if 'date' in key:
                        value = [datetime.fromisoformat(v).date().strftime('%Y-%m-%d') for v in value]
                    row[key] = value
                # note: splitting by '//' shouldn't be needed; error in pure report export. 
                # make sure to always delimit using '|' instead
                if '//' in value and 'http' not in value:
                    value = value.split('//')
                    value = [v.strip() for v in value]
                    if 'date' in key:
                        value = [datetime.fromisoformat(v).date().strftime('%Y-%m-%d') for v in value]
                    row[key] = value

            authordict['pureid'] = row['author_pureid']
            authordict['id'] = row['author_uuid']
            authordict['name'] = row['author_name']
            authordict['lastname'] = row['author_last_name']
            authordict['firstname'] = row['author_first_names']
            authordict['known_as'] = row['author_known_as_name']
            authordict['default_publishing_name'] = row['author_default_publishing_name']
            authordict['orcid'] = row['author_orcid']
            authordict['isni'] = row['author_isni']
            authordict['scopus_id'] = row['author_scopus_id']
            authordict['links'] = row['author_links']
            authordict['org_names'] = row['org_names']
            orgdata = []
            if isinstance(row['org_uuids'], list) and len(row['org_uuids']) > 1:
                if len(row['org_uuids']) == len(row['org_names']):
                    orgdatazip = zip(row['affl_start_date'], row['affl_end_date'], row['org_names'], row['org_uuids'], row['org_pureids'])
                    for start_date, end_date, orgname, uuid, pureid in orgdatazip:
                        orgdata.append({
                            'start_date': start_date,
                            'end_date': end_date,
                            'uuid': uuid,
                            'pureid': pureid,
                            'name': orgname,
                        })
                else:
                    orgdatazip = zip(row['affl_start_date'], row['affl_end_date'], row['org_uuids'], row['org_pureids'])
                    for start_date, end_date, uuid, pureid in orgdatazip:
                        orgdata.append({
                            'start_date': start_date,
                            'end_date': end_date,
                            'uuid': uuid,
                            'pureid': pureid,
                            'name':None
                        })
            elif (isinstance(row['org_uuids'], list) and len(row['org_uuids']) == 1) or isinstance(row['org_uuids'], str):
                orgdata = [{
                    'start_date': row['affl_start_date'],
                    'end_date': row['affl_end_date'],
                    'uuid': row['org_uuids'],
                    'pureid': row['org_pureids']
                }]
                if (isinstance(row['org_uuids'], list) and isinstance(row['org_names'], list) and len(row['org_uuids']) == len(row['org_names'])) or isinstance(row['org_uuids'], str) and isinstance(row['org_names'], str):
                    orgdata[0]['name'] = row['org_names']
                else:
                    orgdata[0]['name'] = None
            else:
                orgdata = []

            authordict['affiliation_details'] = orgdata
            authordict['faculty'] = row['faculty_name']
            authordict['faculty_uuid']= row['faculty_uuid']
            if pure_cerif_authors.find_one({'id':authordict['id']}):
                pure_cerif_authors.update_one({'id':authordict['id']}, {'$set':authordict})
                matched += 1
            else:
                nomatch +=1
    print(f'Total: {total}, matched: {matched}, nomatch: {nomatch}')

'''
========================================
IMPORT CERIF XML
========================================
'''
# export pure CERIF xml, use importpurexml to import
# when done it calls process_data_from_pure_xmls() and then process_pure_uuids()
def importpurexml(file='eemcs_output_2023_2024q1cerif.xml', replace=False):
    '''
    this reads in a pure cerif xml export file containing research products
    '''
    logger.info(f'importing from cerif xml file {file}')

    with open(file, encoding='utf-8') as f:
        xmldict = xmltodict.parse(f.read())
    recordlist = xmldict.get('OAI-PMH').get('ListRecords').get('record')
    recordlist = [entry['metadata'] for entry in recordlist]
    logger.info(f'found {len(recordlist)} records in {file}, sorting by type')
    products = [entry.get('cerif:Product') for entry in recordlist if entry.get('cerif:Product')]
    patents = [entry.get('cerif:Patent') for entry in recordlist if entry.get('cerif:Patent')]
    publications = [entry.get('cerif:Publication') for entry in recordlist if entry.get('cerif:Publication')]
    if not replace:
        logger.info('removing already imported records')
        ids=[]
        for item in mongo_pure_xmls.find({'@id':True}):
            ids.append(item.get('@id'))
        products = [p for p in products if p.get('@id') not in ids]
        patents = [p for p in patents if p.get('@id') not in ids]
        publications = [p for p in publications if p.get('@id') not in ids]
        logger.info(f'after removing duplicates: importing {len(products)} products, {len(patents)} patents, {len(publications)} publications to collection pure_xmls')
    else:
        logger.info('replace=True: removing records from collection if @id matches with @id in recordlist')
        ids = [p.get('@id') for p in recordlist]
        logger.info(f'found {len(ids)} ids in recordlist, removing from collection if present')
        for item in mongo_pure_xmls.find({'@id':True}):
            if item.get('@id') in ids:
                try:
                    mongo_pure_xmls.delete_one({'@id':item.get('@id')})
                except Exception as e:
                    logger.warning(f'error removing {item.get("@id")} from collection: {e}')

    mongo_pure_xmls.insert_many(products) if products else None
    mongo_pure_xmls.insert_many(patents) if patents else None
    mongo_pure_xmls.insert_many(publications) if publications else None
    if any([products, patents, publications]):
        process_data_from_pure_xmls()

def process_data_from_pure_xmls():
    '''
    Read in the import raw xml data and process it to create formatted data.
    Data will be used to:
    1. export cerif xml files back into pure
    2. match authors / works in musdb to pure
    3. improve metadata in mus, especially utdata

    '''

    '''
    Here are the fields that hold ids, categories, and schemes in the docs in the xml collection:
    Note: all [n] fields are lists; but if there is only one entry it won't be used: the dict is directly accessed.

    ids:
    ['@id']: work
    ['cerif:Creators']['cerif:Creator'][n]['cerif:Person']['@id']: author/researcher
    ['cerif:Creators']['cerif:Creator'][n]['cerif:Affiliation'][n]['cerif:OrgUnit']['@id']: research group
    same fields for Authors/Author instead of Creators/Creator

    ['cerif:PublishedIn']['cerif:Publication']['@id']: journal

    categories/schemes:
    ['pubt:type']['@pure:publicationCategory']: publication category atira
    ['pubt:type']['#text']: publication category purl
    ['cerif:PartOf']['cerif:Publication']['pubt:type']: publication category purl
    ['cerif:ISBN'][n]['@medium']: isbn medium
    ['cerif:License']['@scheme']: licence scheme atira
    ['cerif:Status']['@scheme']: publication status atira
    ['ar:Access']: access rights purl
    ['cerif:FileLocations'][n]['cerif:Medium']['cerif:Type']['@scheme']: publication type scheme atira
    ['cerif:FileLocations'][n]['cerif:Medium'] -> also has ['cerif:License']['@scheme'], ['ar:Access'], ['cerif:MimeType']
    '''


    def process_authors(item:dict)->list[dict]:
        authors = []
        authorrawlist = []
        if item.get('cerif:Creators'):
            if isinstance(item.get('cerif:Creators').get('cerif:Creator'), list):
                for author in item.get('cerif:Creators').get('cerif:Creator'):
                    authorrawlist.append(author)
            elif isinstance(item.get('cerif:Creators').get('cerif:Creator'), dict):
                authorrawlist.append(item.get('cerif:Creators').get('cerif:Creator'))
        if item.get('cerif:Authors'):
            if isinstance(item.get('cerif:Authors').get('cerif:Author'), list):
                for author in item.get('cerif:Authors').get('cerif:Author'):
                    authorrawlist.append(author)
            elif isinstance(item.get('cerif:Authors').get('cerif:Author'), dict):
                authorrawlist.append(item.get('cerif:Authors').get('cerif:Author'))
        for author in authorrawlist:

            authorid = author.get('cerif:Person').get('@id') if author.get('cerif:Person') else None
            if not authorid:
                continue
            authorfirstnames = author.get('cerif:Person').get('cerif:PersonName').get('cerif:FirstNames')
            authorlastnames = author.get('cerif:Person').get('cerif:PersonName').get('cerif:FamilyNames')
            authoraffiliations = []
            if author.get('cerif:Affiliation'):
                if isinstance(author.get('cerif:Affiliation'), list):
                    for affiliation in author.get('cerif:Affiliation'):
                        affiliation = affiliation.get('cerif:OrgUnit')
                        authoraffiliations.append({
                            'id': affiliation.get('@id'),
                            'name': affiliation.get('cerif:Name').get('#text'),
                        })

                elif isinstance(author.get('cerif:Affiliation'), dict):
                        affiliation = author.get('cerif:Affiliation').get('cerif:OrgUnit')
                        authoraffiliations.append({
                            'id': affiliation.get('@id'),
                            'name': affiliation.get('cerif:Name').get('#text'),
                        })
            authors.append({
                'id': authorid,
                'first_names': authorfirstnames,
                'last_names': authorlastnames,
                'affiliations': authoraffiliations
            })

        for author in authors:
            if pure_cerif_authors.find_one({'id':author['id']}):
                pure_cerif_authors.update_one({'id':author['id']}, {'$set': author})
            else:
                pure_cerif_authors.insert_one(author)

        return authors
    def process_journal(item: dict) -> list[dict]:

        results = []
        if not item.get('cerif:PublishedIn'):
            return results
        result = defaultdict()
        journalsraw = []
        result['ISSN'] = []
        if item.get('cerif:ISSN'):
            if isinstance(item.get('cerif:ISSN'), list):
                for issn in item.get('cerif:ISSN'):
                    result['ISSN'].append({issn.get('@medium', '#unknown').split('#')[1]:issn.get('#text')})
        if item.get('cerif:PublishedIn'):
            if item.get('cerif:PublishedIn').get('cerif:Publication'):
                if isinstance(item.get('cerif:PublishedIn').get('cerif:Publication'), list):
                    for publication in item.get('cerif:PublishedIn').get('cerif:Publication'):
                        journalsraw.append(publication)
                elif isinstance(item.get('cerif:PublishedIn').get('cerif:Publication'), dict):
                    process_journal(item.get('cerif:PublishedIn').get('cerif:Publication'))
                else:
                    logger.warning(f'unknown type of item in cerif:PublishedIn. Contents: {item.get("cerif:PublishedIn")}')
        for i in journalsraw:
            result['id'] = i.get('@id')
            result['type'] = i.get('pubt:Type')
            result['title'] = i.get('cerif:Title').get('#text')
            if pure_cerif_journals.find_one({'id':result['id']}):
                pure_cerif_journals.update_one({'id':result['id']}, {'$set': result})
            else:
                pure_cerif_journals.insert_one(result)

            results.append(result)

        return results

    def process_categories(item:dict) -> dict:
        result = defaultdict()
        result['id'] = item.get('@id')
        if item.get('pubt:Type'):
            result['category'] = item.get('pubt:Type').get('@pure:publicationCategory')
            result['type'] = item.get('pubt:Type').get('#text')
        elif item.get('prot:Type'):
            result['category'] = item.get('prot:Type').get('@pure:publicationCategory')
            result['type'] = item.get('prot:Type').get('#text')
        if item.get('cerif:License'):
            if isinstance(item.get('cerif:License'), list):
                result['license'] = [{lic['@scheme']:lic['#text']} for lic in item.get('cerif:License')]
            else:
                result['license'] = {item['cerif:License']['@scheme']:item['cerif:License']['#text']}
        else:
            result['license'] = None
        result['status'] = {item.get('cerif:Status').get('@scheme'):item.get('cerif:Status').get('#text')} if item.get('cerif:Status') else None
        result['access'] = item.get('ar:Access') if item.get('ar:Access') else None
        result['locations']=[]
        if item.get('cerif:FileLocations'):
            if isinstance(item.get('cerif:FileLocations').get('cerif:Medium'), list):
                for location in item.get('cerif:FileLocations').get('cerif:Medium'):
                    ltype = {location['cerif:Type']['@scheme']:location['cerif:Type']['#text']} if location.get('cerif:Type') else None
                    access = location['ar:Access'] if location.get('ar:Access') else None
                    mimetype = location['cerif:MimeType'] if location.get('cerif:MimeType') else None
                    if location.get('cerif:License'):
                        if isinstance(location.get('cerif:License'), list):
                            license = [{lic['@scheme']:lic['#text']} for lic in location.get('cerif:License')]
                        else:
                            license = {location['cerif:License']['@scheme']:location['cerif:License']['#text']}
                    else:
                        license = None
                    result['locations'].append({
                        'type': ltype,
                        'license': license,
                        'access': access,
                        'mimetype': mimetype
                    })
            elif isinstance(item.get('cerif:FileLocations').get('cerif:Medium'), dict):
                    location = item.get('cerif:FileLocations').get('cerif:Medium')
                    ltype = location['cerif:Type']['@scheme'] if location.get('cerif:Type') else None
                    if location.get('cerif:License'):
                        if isinstance(location.get('cerif:License'), list):
                            license = [{lic['@scheme']:lic['#text']} for lic in location.get('cerif:License')]
                        else:
                            license = {location['cerif:License']['@scheme']:location['cerif:License']['#text']}
                    else:
                        license = None
                    access = location['ar:Access'] if location.get('ar:Access') else None
                    mimetype = location['cerif:MimeType'] if location.get('cerif:MimeType') else None
                    result['locations'].append({
                        'type': ltype,
                        'license': license,
                        'access': access,
                        'mimetype': mimetype
                    })
        result['funding']=[]
        if item.get('cerif:OriginatesFrom'):
            if isinstance(item.get('cerif:OriginatesFrom'), list):
                for funding in item.get('cerif:OriginatesFrom'):
                    funding = funding.get('cerif:Funding') if funding.get('cerif:Funding') else None
                    if funding:
                        ftype = funding.get('funt:Type') if funding.get('funt:Type') else None
                        if isinstance(funding.get('cerif:Identifier'), list):
                            fid = [{ident.get('@type'):ident.get('#text')} for ident in funding.get('cerif:Identifier')] if funding.get('cerif:Identifier') else None
                        else:
                            fid = {funding.get('cerif:Identifier').get('@type'):funding.get('cerif:Identifier').get('#text')} if funding.get('cerif:Identifier') else None
                        description = funding.get('cerif:Description').get('#text') if funding.get('cerif:Description') else None
                        if funding.get('cerif:Funder'):
                            funder ={
                                'id': funding.get('cerif:Funder').get('cerif:OrgUnit').get('@id'),
                                'acronym': funding.get('cerif:Funder').get('cerif:OrgUnit').get('cerif:Acronym'),
                                'name': funding.get('cerif:Funder').get('cerif:OrgUnit').get('cerif:Name').get('#text')
                            }
                        else:
                            funder = None

                        result['funding'].append({
                            'type': ftype,
                            'id': fid,
                            'description': description,
                            'funder': funder
                        })
            elif isinstance(item.get('cerif:OriginatesFrom'), dict):
                    funding = item.get('cerif:OriginatesFrom').get('cerif:Funding') if item.get('cerif:OriginatesFrom').get('cerif:Funding') else None
                    if funding:
                        ftype = funding.get('funt:Type') if funding.get('funt:Type') else None
                        if isinstance(funding.get('cerif:Identifier'), list):
                            fid = [{ident.get('@type'):ident.get('#text')} for ident in funding.get('cerif:Identifier')] if funding.get('cerif:Identifier') else None
                        else:
                            fid = {funding.get('cerif:Identifier').get('@type'):funding.get('cerif:Identifier').get('#text')} if funding.get('cerif:Identifier') else None
                        description = funding.get('cerif:Description') if funding.get('cerif:Description') else None

                        if funding.get('cerif:Funder'):
                            funder ={
                                'id': funding.get('cerif:Funder').get('cerif:OrgUnit').get('@id'),
                                'acronym': funding.get('cerif:Funder').get('cerif:OrgUnit').get('cerif:Acronym'),
                                'name': funding.get('cerif:Funder').get('cerif:OrgUnit').get('cerif:Name').get('#text')
                            }
                        else:
                            funder = None

                        result['funding'].append({
                            'type': ftype,
                            'id': fid,
                            'description': description,
                            'funder': funder
                        })


        if pure_cerif_categories.find_one({'id':result['id']}):
            pure_cerif_categories.update_one({'id':result['id']}, {'$set':result})
        else:
            pure_cerif_categories.insert_one(result)

        return result

    def process_work(item:dict):
        try:
            categories = process_categories(item)
        except Exception as e:
            categories = None
            logger.error(f'[{item.get("id")}] Error processing categories: {e}', exc_info=True)
        try:
            authors = process_authors(item)
        except Exception as e:
            authors = None
            logger.error(f'[{item.get("id")}] Error processing authors: {e}', exc_info=True)
        try:
            journals = process_journal(item)
        except Exception as e:
            journals = None
            logger.error(f'[{item.get("id")}] Error processing journal: {e}', exc_info=True)
        result = defaultdict()
        result['id'] = item.get('@id')

        result['doi']=item.get('cerif:DOI') if item.get('cerif:DOI') else None
        if isinstance(item.get('cerif:Title'),list):
            result['title']=[ti.get('#text') for ti in item.get('cerif:Title')]
        else:
            result['title']=item.get('cerif:Title').get('#text') if item.get('cerif:Title') else None
        result['date']=item.get('cerif:PublicationDate') if item.get('cerif:PublicationDate') else None
        if item.get('cerif:ISBN'):
            if isinstance(item.get('cerif:ISBN'), list):
                result['isbn']=[{isbn.get('@medium').split('#')[1]:isbn.get('#text')} for isbn in item.get('cerif:ISBN')]
            else:
                result['isbn']={item.get('cerif:ISBN').get('@medium').split('#')[1]:item.get('cerif:ISBN').get('#text')}
        result['language']=item.get('cerif:Language') if item.get('cerif:Language') else None
        result['volume']=item.get('cerif:Volume') if item.get('cerif:Volume') else None
        result['startpage']=item.get('cerif:StartPage') if item.get('cerif:StartPage') else None
        result['endpage']=item.get('cerif:EndPage') if item.get('cerif:EndPage') else None
        result['scopus']=item.get('cerif:SCP-Number') if item.get('cerif:SCP-Number') else None

        publisher = ''
        if item.get('cerif:Publishers'):
            if isinstance(item.get('cerif:Publishers'), list):
                for pub in item.get('cerif:Publishers'):
                    if publisher == '':
                        publisher = pub.get('cerif:Publisher').get('cerif:OrgUnit').get('cerif:Name').get('#text')
                    else:
                        publisher = publisher + ', ' + pub.get('cerif:Publisher').get('cerif:OrgUnit').get('cerif:Name').get('#text')
            elif isinstance(item.get('cerif:Publishers'), dict):
                publisher = item.get('cerif:Publishers').get('cerif:Publisher').get('cerif:OrgUnit').get('cerif:Name').get('#text')
        result['publisher'] = publisher if publisher!='' else None
        if isinstance(item.get('cerif:License'), list):
            result['license'] = [lic.get('#text') for lic in item.get('cerif:License')]
        else:
            result['license'] = item.get('cerif:License').get('#text') if item.get('cerif:License') else None
        result['status'] = item.get('cerif:Status').get('#text') if item.get('cerif:Status') else None
        result['categories'] = categories
        result['authors'] = authors
        result['journals'] = journals
        result['abstract']=item.get('cerif:Abstract').get('#text') if item.get('cerif:Abstract') else None
        result['url']=item.get('cerif:URL') if item.get('cerif:URL') else None

        if pure_cerif_works.find_one({'id':result['id']}):
            pure_cerif_works.update_one({'id':result['id']}, {'$set':result})
        else:
            pure_cerif_works.insert_one(result)

    #main loop
    for item in mongo_pure_xmls.find():
        logger.info(f'processing item with @id {item.get("@id")}')

        try:
            process_work(item)
        except Exception as e:
            logger.error(f'error for itemid {item.get("@id")}: {e}', exc_info=True)
    
    process_pure_uuids()

def process_pure_uuids():
    # import uuid fields from authors, works
    faculties = {}
    orgid_to_name = {}
    names_to_orgid = {}


    iorg = []

    for item in pure_cerif_authors.find({'pureid': {'$exists': True}}):
        ifac = {}
        if item.get('affiliations'):
            for affl in item.get('affiliations'):
                if affl.get('name').lower() in PureOpenAlex.constants.UTRESEARCHGROUPS_FLAT:
                    uuid = affl.get('id')
                    name = affl.get('name')
                    if isinstance(name, set) or isinstance(name, list):
                        name = list(name)[0]
                    facname = PureOpenAlex.constants.FACULTYABBRMAPPING[PureOpenAlex.constants.UTRESEARCHGROUPS_FLAT[name.lower()]]
                    adddict = {'name':name, 'uuid':uuid, 'faculty':facname}
                    iorg.append(adddict)
                    print(f'Hit: {adddict}')
                    if not orgid_to_name.get(uuid):
                        orgid_to_name[uuid] = {name}
                    else:
                        orgid_to_name[uuid].add(name)
                    if not names_to_orgid.get(name):
                        names_to_orgid[name] = {name}
                    else:
                        names_to_orgid[name].add(uuid)
        if item.get('faculty_uuid'):
            if not isinstance(item.get('faculty_uuid'), list):
                if item.get('faculty_uuid') not in faculties.keys():
                    faculties[item.get('faculty_uuid')] = item.get('faculty')
            else:
                for faculty_uuid in item.get('faculty_uuid'):
                    if faculty_uuid not in faculties.keys():
                        faculties[faculty_uuid] = item.get('faculty')
        if item.get('affiliation_details'):
            for affl in item.get('affiliation_details'):
                uuid = affl.get('uuid')
                name = affl.get('name')
                
                if not name:
                    for org in item.get('affiliations'):
                        if org.get('id') == uuid:
                            name = org.get('name')
                if name:
                    try:
                        facname = PureOpenAlex.constants.FACULTYABBRMAPPING[PureOpenAlex.constants.UTRESEARCHGROUPS_FLAT[name.lower()]]
                    except KeyError:
                        facname = None
                else:
                    facname = None
                if not name and uuid not in orgid_to_name.keys():
                    orgid_to_name[uuid] = None
                elif name:
                    if not orgid_to_name.get(uuid):
                        orgid_to_name[uuid] = {name}
                    else:
                        orgid_to_name[uuid].add(name)
                    if not names_to_orgid.get(name):
                        names_to_orgid[name] = {name}
                    else:
                        names_to_orgid[name].add(uuid)
                iorg.append({'name':name, 'uuid':uuid, 'faculty':facname})

    print(len(iorg))
    for item in iorg:
        if not item.get('name'):
            if orgid_to_name.get(item.get('uuid')):
                item['name'] = orgid_to_name[item.get('uuid')]

    uniqueorgs = list({item['uuid']:item for item in iorg if item.get('name')}.values())
    print(len(uniqueorgs))
    input('...')

    for org in uniqueorgs:
        if isinstance(org.get('name'), set):
            org['name'] = list(org.get('name'))
        print(org)
        if pure_org_mapping.find_one({'uuid':org.get('uuid')}):
            pure_org_mapping.update_one({'uuid':org.get('uuid')}, {'$set':org})
        else:
            pure_org_mapping.insert_one(org)

