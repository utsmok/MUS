'''
This script reads in data from files, lightly processes it if necessary, and
stores it into mongoDB. The data can then be used to create the main entries
in the django SQL database.

Example files:
worldcat kbart
pure reports

'''
from loguru import logger
from django.conf import settings
from pymongo import MongoClient
import xmltodict
import re
from gzip import GzipFile
from rich import print
import csv
from time import time
from PureOpenAlex.models import DBUpdate
from collections import defaultdict
MONGOURL = getattr(settings, "MONGOURL")
APIEMAIL = getattr(settings, "APIEMAIL", "no@email.com")
client=MongoClient(MONGOURL)
db=client['mus']
mongo_dblp_raw=db['file_dblp_raw']
mongo_pure_report_start_tcs=db['pure_report_start_tcs']
mongo_pure_report_ee=db['pure_report_ee']
mongo_pure_xmls=db['pure_xmls']
global added
global processed
added = 0
processed = 0

def getdblp():

    def handle_dblp(_, item):
        global added
        global processed
        processed += 1
        if item.get('year'):
            if item.get('year') >= '2018':
                mongo_dblp_raw.insert_one(item)
                added += 1
        if added % 1000 == 0:
            msg=f"{processed} processed dblp items, added {added}"
            logger.debug(msg)
        return True

    xmltodict.parse(GzipFile('dblp.xml.gz'),
                    item_depth=2, item_callback=handle_dblp)

def getfrompurereport(group):
    result={'pureids':[], 'total':0}
    filename=f'pure_report_{group}'
    if group == 'ee':
        mongocoll=mongo_pure_report_ee
    elif group == 'tcs':
        mongocoll=mongo_pure_report_start_tcs
    start = time()
    i=0
    final = []
    datasetkeys = ['linked_dataset_title','linked_dataset_pureid','linked_dataset_doi', 'linked_dataset_url']
    datekeys = ['date_created', 'last_modified', 'date_earliest_published','date_published','date_eprint_first_online']
    itemkeys= ['date_created','last_modified']
    date_pattern = re.compile(r'^\d{4}-\d{2}-\d{2}$')

    with open(f"{filename}.csv", encoding='utf-8') as f:
        data = csv.DictReader(f)
        for item in data:
            itemdict={}
            tmp_utauthors={}
            tmp_dataset={}
            tmp_pubdates={}
            tmp_itemdates={}
            i=i+1
            for key, value in item.items():
                if value=='Not set' or value=='0.0':
                    value=''
                if '|' in value:
                    value = value.split('|')
                    value=[i.strip() for i in value]
                else:
                    value=value.strip()

                if key == 'ut_authors' or key == 'author_pureids':
                    tmp_utauthors[key]=value
                elif key in datekeys:
                    if isinstance(value, str) and value:
                        if len(value)>=10:
                            if not date_pattern.match(value):
                                if date_pattern.match(value[0:10]):
                                    value=value[0:10]
                                else: # no match
                                    value=''
                        else:
                            value=''

                    if value!='':
                        if key in itemkeys:
                            tmp_itemdates[key]=value
                        else:
                            tmp_pubdates[key]=value

                elif key in datasetkeys:
                    if value!='':
                        tmp_dataset[key]=value
                else:
                    itemdict[key] = value


            if 'ut_authors' in tmp_utauthors.keys() and 'author_pureids' in tmp_utauthors.keys():
                if isinstance(tmp_utauthors['ut_authors'], str):
                    itemdict['ut_authors']=[{'name:':tmp_utauthors['ut_authors'], 'pureid':tmp_utauthors['author_pureids']}]
                elif isinstance(tmp_utauthors['ut_authors'], list) and len(tmp_utauthors['ut_authors'])==len(tmp_utauthors['author_pureids']):
                    combinedlist = zip(tmp_utauthors['ut_authors'], tmp_utauthors['author_pureids'])
                    ut_authors = []
                    for entry in combinedlist:
                        ut_authors.append({
                            'name': entry[0],
                            'pureid': entry[1]
                        })
                    itemdict['ut_authors']= ut_authors
                else:
                    itemdict['ut_authors']=tmp_utauthors['ut_authors']
                    itemdict['author_pureids']=tmp_utauthors['author_pureids']

            if tmp_dataset!={}:
                itemdict['dataset']=tmp_dataset
            if tmp_pubdates!={}:
                itemdict['publication_dates']=tmp_pubdates
            if tmp_itemdates!={}:
                itemdict['pure_entry_dates']=tmp_itemdates
            final.append(itemdict)
    elapsed = time() - start
    h=0
    msg=f"in {elapsed:.1f}s: Processed {i} records from Pure Report {filename}.csv"
    logger.info(msg)

    addlist=[]
    for item in final:
        if mongocoll.find_one({"pureid":item['pureid']}):
            continue
        else:
            addlist.append(item)
            result['total']+=1
            result['pureids'].append(item['pureid'])
    if addlist:
        mongocoll.insert_many(addlist)

    return result if result['total']>0 else None


def importpurexml(file='eemcs_output_2023_2024q1cerif.xml', replace=False):
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
        process_data_from_xmls()
def process_data_from_xmls():
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
    pure_cerif_authors = db['pure_cerif_authors']
    pure_cerif_works = db['pure_cerif_works']
    pure_cerif_journals = db['pure_cerif_journals']
    pure_cerif_categories = db['pure_cerif_categories']

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


        

def addfromfiles():
    result = getfrompurereport('ee')
    if result:
        dbupdate=DBUpdate.objects.create(update_source="Pure EE Report", update_type="manualmongo", details = result)
        dbupdate.save()
    '''result = getfrompurereport('tcs')
    if result:
        dbupdate=DBUpdate.objects.create(update_source="Pure TCS Report", update_type="manualmongo", details = result)
        dbupdate.save()'''