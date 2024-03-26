from .models import (
    PureEntry,
    Organization,
    Author,
    DBUpdate,
    UTData
)
from django.db import transaction
import pyalex
from django.db.models import Q
from django.conf import settings
from loguru import logger
from pymongo import MongoClient
from collections import defaultdict
from rich import print
from rapidfuzz import process, fuzz, utils
import pymongo

APIEMAIL = getattr(settings, "APIEMAIL", "no@email.com")
pyalex.config.email = APIEMAIL
MONGOURL = getattr(settings, "MONGOURL")

client=MongoClient(MONGOURL)
db=client['mus']
mongo_dealdata=db['api_responses_journals_dealdata_scraped']
mongo_oa_authors=db['api_responses_authors_openalex']
mongo_orcid=db['api_responses_orcid']
mongo_oa_ut_authors=db['api_responses_UT_authors_openalex']
mongo_peoplepage=db['api_responses_UT_authors_peoplepage']
mongo_oa_journals = db['api_responses_journals_openalex']
mongo_openaire_works = db['api_responses_openaire']
mongo_pureentries = db['api_responses_pure']
mongo_pure_report_start_tcs = db['pure_report_start_tcs']
mongo_pure_report_ee = db['pure_report_ee']


def fixMissingAffils():
    def getorgs(affils):
        affiliations=[]
        for org in affils:
            # get affiliation info into a list of dicts, check for is_ut along the way
            if not org:
                continue
            if org.get('institution'):
                orgsrc = org.get('institution')
            else:
                orgsrc = org

            orgdata = {
                'name':orgsrc.get('display_name'),
                'openalex_url':orgsrc.get('id'),
                'ror':orgsrc.get('ror'),
                'type':orgsrc.get('type'),
                'country_code':orgsrc.get('country_code') if orgsrc.get('country_code') else '',
                'data_source':'openalex'
            }

            if org.get('years'):
                years = org.get('years')
            else:
                years = []

            # if org is already in db, either
            if Organization.objects.filter(Q(ror=orgdata['ror']) & Q(name=orgdata['name']) & Q(openalex_url=orgdata['openalex_url'])).exists():
                found_org  = Organization.objects.filter(Q(ror=orgdata['ror']) & Q(name=orgdata['name']) & Q(openalex_url=orgdata['openalex_url'])).first()
                if found_org.type != orgdata['type'] or found_org.country_code != orgdata['country_code']:
                    #for now, assumed that the new data is better... might be a bad assumption
                    if orgdata['type'] and orgdata['type'] != '':
                        found_org.type = orgdata['type']
                    if orgdata['country_code'] and orgdata['country_code'] != '':
                        found_org.country_code = orgdata['country_code']
                    found_org.save()
                org = found_org
            try:
                if not isinstance(org, Organization):
                    org, created = Organization.objects.get_or_create(**orgdata)
                    if created:
                        org.save()
            except Exception:
                print('error adding org, skipping')
                pass
            affiliations.append([org, years])
        return affiliations

    authorlist = Author.objects.filter(affils__isnull=True).distinct()
    print(f"Adding affils for {len(authorlist)} authors")

    for author in authorlist:
        print("adding affils for author "+str(author.name))
        raw_affildata = None
        oa_data = mongo_oa_ut_authors.find_one({"id":author.openalex_url})
        try:
            raw_affildata = oa_data.get('affiliations')
        except Exception:
            pass
        if not oa_data or not raw_affildata:
            oa_data = mongo_oa_authors.find_one({"id":author.openalex_url})
        try:
            raw_affildata = oa_data.get('affiliations')
        except Exception:
            pass
        if not oa_data or not raw_affildata:
            print(f"Cannot find data for author {author.openalex_url} | {author.name} in MongoDB")
        else:
            affiliations = getorgs(raw_affildata)
            print('processed raw data')
            for aff in affiliations:
                try:
                    with transaction.atomic():
                        author.affils.add(aff[0],through_defaults={'years':aff[1]})
                        author.save()
                except Exception:
                    pass
            print(f"added {len(affiliations)} affils to Mongo for author {author.openalex_url} | {author.name}")
    amount = Author.objects.filter(affils__isnull=True).distinct().count()
    print(f"{amount} authors still have no affils.")

def addPureEntryAuthors():
    allentries = PureEntry.objects.all()
    dbauthordata = Author.objects.order_by('last_name','first_name').only('id','openalex_url','name','first_name','last_name','known_as', 'initials')
    matchlist = []
    idnamemapping = defaultdict(set)
    i = 0
    for author in dbauthordata:
        i += 1
        id = author.id
        matchlist.append(author.name)
        idnamemapping[author.name].add(id)
        if author.known_as != {} and author.known_as is not None:
            for name in author.known_as:
                matchlist.append(name)
                idnamemapping[name].add(id)
        for name in [f'{author.first_name} {author.last_name}', f'{author.last_name}, {author.first_name}', f'{author.initials} {author.last_name}', f'{author.last_name}, {author.initials}']:
            matchlist.append(name)
            idnamemapping[name].add(id)
    faillist = []
    donelist = []
    matched = 0
    failed = 0
    total = 0
    for entry in allentries:
        num_authors = entry.authors.count()

        mongodata = mongo_pureentries.find_one({'title':entry.title})
        if not mongodata:
            mongodata = mongo_pureentries.find_one({'identifier':{'ris_file':entry.risutwente}})
        if not mongodata:
            mongodata = mongo_pureentries.find_one({'identifier':{'researchutwente':entry.researchutwente}})
        if not mongodata:
            mongodata = mongo_pureentries.find_one({'identifier':{'doi':entry.doi}})
        if not mongodata:
            logger.error(f'no mongodata found for {entry.id} - {entry.title} - {entry.doi} - {entry.researchutwente} - {entry.risutwente}')
            faillist.append(entry.id)
            continue

        authorlist = []
        if mongodata.get('contributor'):
            if isinstance(mongodata.get('contributor'),list):
                authorlist.extend(mongodata.get('contributor'))
            if isinstance(mongodata.get('contributor'),str):
                authorlist.append(mongodata.get('contributor'))
        if mongodata.get('creator'):
            if isinstance(mongodata.get('creator'),list):
                authorlist.extend(mongodata.get('creator'))
            if isinstance(mongodata.get('creator'),str):
                authorlist.append(mongodata.get('creator'))

        if len(authorlist) == 0:
            logger.error(f'no authors found for {entry.id} - {entry.doi} - {entry.researchutwente} - {entry.risutwente}')
            faillist.append(entry.id)
            continue



        if num_authors == len(authorlist):
            logger.info(f'no missing authors for {entry.id}')
            continue

        total += len(authorlist) - len(authorlist)
        logger.info(f'{num_authors - len(authorlist)} new authors found for {entry.id}')


        for author in authorlist:

            matches = process.extract(author,matchlist, processor=utils.default_process, scorer=fuzz.QRatio, score_cutoff=90)
            if len(matches) == 0 or not matches:
                failed += 1
                logger.warning(f'no matches for {author}')
            else:
                matchname=matches[0][0]
                authorid=idnamemapping[matchname]
                if isinstance(authorid, set):
                    matched += 1
                    id = max(authorid)
                    authorobj = Author.objects.get(id=id)
                    if authorobj:
                        logger.debug(f'match: {author} == {authorobj.name} ({authorobj.id}) | score {matches[0][1]}')
                        if authorobj not in entry.authors.all():
                            entry.authors.add(authorobj)
                            entry.save()
                        else:
                            logger.info(f'{authorobj.name} already linked with entry')
                else:
                    failed += 1
                    logger.error(f'failed to process matches for {author}')

        donelist.append(entry.id)

    details = {
        'failed_pureentry_ids':faillist,
        'success_pureentry_ids':donelist,
        'new_matches':matched,
        'failed_to_match':failed,
        'total_checked_names':total
    }
    logger.info(f'Authors: new matches: {matched} | failed to match: {failed} | total checked: {total}')
    logger.info(f'{len(faillist)} pureentries failed  | {len(donelist)} pureentries successfully checked')
    dbu = DBUpdate.objects.create(details=details,update_source='OpenAlex', update_type='addpureentryauthors')
    dbu.save()

def matchPurePilotWithPureEntry():

    mongocols = [ mongo_pure_report_ee] # also add mongo_pure_report_start_tcs
    addlist = []
    for group in mongocols:
        h=0
        i=0
        j=0
        z=0
        k=0
        for item in group.find().sort('year', pymongo.DESCENDING):
            i=i+1
            if item.get('pure_entry_id'):
                #already matched
                k=k+1
                continue
            if not item.get('dois'):
                z=z+1
                mongo_pure_report_start_tcs.update_one({'pureid': item['pureid']}, {'$set': {'pure_entry_id': None}})
                continue

            doi = item.get('dois')
            if isinstance(doi, list):
                print(item['title'], item['pureid'])
                print(doi)
                print("note: more than 1 doi? picked first in list.")
                doi=doi[0]
            if isinstance(doi, str):
                if doi.startswith('https://doi.org/'):
                    pass
                else:
                    doi = 'https://doi.org/' + doi

            pureentry = PureEntry.objects.filter(doi=doi)
            if not pureentry:
                pureentry = PureEntry.objects.filter(doi=doi.lower())
            if not pureentry:
                if item.get('other_links'):
                    if isinstance(item['other_links'], list):
                        for link in item['other_links']:
                            if 'scopus' in link:
                                scopuslink = link
                    elif isinstance(item['other_links'], str):
                        if 'scopus' in item['other_links']:
                            scopuslink = item['other_links']

                    if scopuslink:
                        pureentry = PureEntry.objects.filter(scopus=scopuslink)
            if not pureentry:
                pureid = item.get('pureid')
                pureentry = PureEntry.objects.filter(risutwente__icontains=pureid)
            if pureentry.count()>0:
                if pureentry.count == 1:
                    pure_entry_id = pureentry[0].id
                    mongo_pure_report_start_tcs.update_one({'pureid': item['pureid']}, {'$set': {'pure_entry_id': pure_entry_id}})
                else:
                    pure_entry_ids=[]
                    for pureentry in pureentry:
                        pure_entry_ids.append(pureentry.id)
                    mongo_pure_report_start_tcs.update_one({'pureid': item['pureid']}, {'$set': {'pure_entry_id': pure_entry_ids}})
                j=j+1
            else:
                h=h+1
                mongo_pure_report_start_tcs.update_one({'pureid': item['pureid']}, {'$set': {'pure_entry_id': None}})


        print(f'total:                  {i}')
        print(f'    already matched:    {k}')
        print(f'        matched:        {j}/{i-k}')
        print(f'        no doi:         {z}/{i-k}')
        print(f'        no match:       {h}/{i-k}')

def fixavatars():
    data = UTData.objects.all()

    for entry in data:
        url = entry.avatar.url
        entry.avatar_path = url.replace('https://people.utwente.nl/','author_avatars/')
        entry.save()