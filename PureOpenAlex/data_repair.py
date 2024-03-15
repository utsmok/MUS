from .models import (
    PureEntry,
    Organization,
    Author,
    Paper,
    Journal,
    DealData,
    DBUpdate,
    UTData
)
from django.db import transaction
from .data_helpers import TWENTENAMES
import pyalex
from django.db.models import Q, Count, Window, F, Min, Max
from django.db.models.functions import RowNumber
from django.conf import settings
from loguru import logger
import pickle
from pymongo import MongoClient
from collections import defaultdict
from rich import print
from rapidfuzz import process, fuzz, utils

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

'''
TODO: add fix<...> function for important classes, eg:
    - paper
    - author
    - utdata
'''

@transaction.atomic
def addJournalsToPapers():
    '''
    queryset: all papers in the db without a journal

    subquerysets: itemtype = journal article; and the rest


    grab the api response for each paper from mongodb

        if apiresponse primary location -> source -> type == 'journal':
                add/find that journal in postgres
                add it to the paper
        else:
            for loc in apiresponse locations
                if loc -> source -> type == 'journal':
                    add/find that journal in postgres
                    add it to the paper
        if itemtype is article and still no journal:
            warning
    '''
    def get_deal_data(openalex_id):
        dealdatacontents = mongo_dealdata.find_one({"id":openalex_id})
        if dealdatacontents:
            dealdata = {
                'deal_status':dealdatacontents.get('APCDeal'),
                'publisher': dealdatacontents.get('publisher'),
                'jb_url': dealdatacontents.get('journal_browser_url'),
                'oa_type': dealdatacontents.get('oa_type'),
            }
            return dealdata, dealdatacontents.get('keywords'), dealdatacontents.get('publisher')
        else:
            return None, None, None

    def getjournal(paper, locdata):
            createnum=0
            data=locdata.get('source')
            if Journal.objects.filter(openalex_url=data.get('id')).exists():
                journal = Journal.objects.filter(openalex_url=data.get('id')).first()
                host_org = data.get('host_organization_lineage_names','')
                if isinstance(host_org, list) and len(host_org) > 0:
                    host_org = host_org[0]
                if host_org != '' and journal.host_org != host_org:
                    journal.host_org = host_org
                    journal.save()
                if not journal.dealdata:
                    dealdata, keywords, publisher = get_deal_data(journal.openalex_url)
                    if dealdata:
                        deal, created = DealData.objects.get_or_create(**dealdata)
                        if created:
                            deal.save()
                        journal.dealdata = deal
                        journal.keywords = keywords
                        journal.publisher = publisher
                        journal.save()
                return journal, createnum
            issn=data.get('issn_l')
            issnlist=data.get('issn')
            eissn=""
            if isinstance(issnlist, list):
                for nissn in issnlist:
                    if nissn != issn:
                        eissn = nissn
                        break
            host_org = data.get('host_organization_lineage_names','')
            if isinstance(host_org, list) and len(host_org) > 0:
                host_org = host_org[0]
            publisher = ''
            split = str(data.get('host_organization')).split('.org/')
            if len(split) > 1:
                if split[1].startswith('P'):
                    publisher = data.get('host_organization_name')
            journaldata = {
                'name':data.get('display_name'),
                'e_issn':eissn,
                'issn':issn,
                'host_org':host_org,
                'is_in_doaj':data.get('is_in_doaj'),
                'is_oa':locdata.get('is_oa'),
                'type':data.get('type'),
                'publisher':publisher,
                'openalex_url': data.get('id'),
            }

            dealdata, keywords, publisher = get_deal_data(journaldata['openalex_url'])
            journaldata['keywords']=keywords
            journaldata['publisher']=publisher if publisher else ""
            journal, created = Journal.objects.get_or_create(**journaldata)
            if created:
                journal.save()
                createnum = 1
            if dealdata and not journal.dealdata:
                deal, created = DealData.objects.get_or_create(**dealdata)
                if created:
                    deal.save()
                journal.dealdata=deal
                journal.save()
            return journal, createnum

    api_responses_openalex = db["api_responses_works_openalex"]
    missingjournals = Paper.objects.filter(journal__isnull=True)
    articles = missingjournals.filter(itemtype='journal-article')
    others = missingjournals.exclude(itemtype='journal-article')
    print(f"Total number of items missing journals: {missingjournals.count()}")
    print(f"Of which articles: {articles.count()}")
    print(f"Others: {others.count()}")
    added=0
    checked=0
    numcreated=0
    checklist = 0
    missingarticles=0
    otherjournal=0
    paperlist=[]
    for grouping in [articles, others]:
        checklist +=1
        if checklist == 1:
            itype = 'article'
        else:
            itype = ''
        for item in grouping:
            checked+=1
            created = False
            journal = None
            data = api_responses_openalex.find_one({'id':item.openalex_url})
            if itype == '':
                itype = item.itemtype
            ident = f'[id] {item.id} [type] {itype}'
            if not data:
                cat = '[Warning] [Skipped]'
                msg = 'No OpenAlex URL for paper'
                print(f"{cat:<20} {msg:^30} {ident:>20}")
                continue
            if data.get('primary_location'):
                if data.get('primary_location').get('source'):
                    if data.get('primary_location').get('source').get('type') == 'journal':
                        journal, created = getjournal(item, data.get('primary_location'))
            if not journal:
                for loc in data.get('locations'):
                    if loc.get('source'):
                        if loc.get('source').get('type') == 'journal':
                            journal, created = getjournal(item, loc)
                            if journal:
                                cat = '[Info]'
                                msg = 'Journal found in loc but not in primary loc.'
                                print(f"{cat:<20} {msg:^30} {ident:>20}")
            if journal:
                item.journal = journal
                item.save()
                added+=1
                paperlist.append(item.openalex_url)
                if created:
                    numcreated+=1
                if checklist == 2:
                    cat = '[Info]'
                    msg = 'Journal found for non-article'
                    print(f"{cat:<20} {msg:^30} {ident:>20}")
                    otherjournal+=1
            elif checklist == 1:
                cat = '[Warning]'
                msg = 'No journal found for article'
                print(f"{cat:<20} {msg:^30} {ident:>20}")
                missingarticles+=1

    print(f"{added} journals added to {checked} articles.")
    print(f'Created {numcreated} new journals.')
    print(f'{missingarticles} articles missing journals.')
    print(f'{otherjournal} non-article items linked with journals.')
    detaildict={
        'journals_added_to_papers':added,
        'journals_added_to_non_articles':otherjournal,
        'newly_created_journals':numcreated,
        'changed_papers':paperlist
    }
    dbupd=DBUpdate.objects.create(update_source="OpenAlex", update_type="repairjournals", details = detaildict)
    dbupd.save()
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
def matchPureEntryWithPaper():
    """
    For every PureEntry, try to find a matching paper in the database and mark them as such.
    """

    def update(i,paperlist,entrylist):
            with transaction.atomic():
                Paper.objects.bulk_update(paperlist, fields=["has_pure_oai_match"])
                PureEntry.objects.bulk_update(entrylist, fields=["paper"])
            i=i+len(paperlist)
            print("+",str(len(paperlist)), "total:", str(i))
            return i

    paperlist = []
    entrylist = []
    i=0
    j=0
    skiplist = []
    advanced = True

    allentries = PureEntry.objects.filter(Q(paper__isnull=True) & ~Q(id__in=skiplist)).only("doi","title",'researchutwente', 'risutwente', 'other_links', 'duplicate_ids')
    paperpreload = Paper.objects.filter(has_pure_oai_match__isnull=True).only("doi","title",'locations','id').prefetch_related('locations')
    print('matching ' + str(allentries.count()) + ' entries with ' + str(paperpreload.count()) + ' papers')
    for entry in allentries:
        logger.debug('matching for entry %s with advanced = %s', entry.id, advanced)
        j=j+1
        print(j)
        found=False
        paper = None
        if entry.paper is not None or entry.paper == "":
            found=True
            print(f'entry {entry.id} already has match')
        if entry.doi:
            doi = entry.doi
            try:
                doichecklist = [doi, doi.lower(), doi.replace('https://doi.org/', ''),doi.replace('https://doi.org/', '').lower()]
            except Exception:
                try:
                    doichecklist = [doi, doi.lower()]
                except Exception:
                    doichecklist = [doi]

            paper = paperpreload.filter(doi__in=doichecklist).first()
        if advanced:
            if not paper and entry.risutwente:
                paper = paperpreload.filter(locations__pdf_url__icontains=entry.risutwente).first()
            if not paper and entry.researchutwente:
                paper = paperpreload.filter(locations__pdf_url__icontains=entry.researchutwente).first()
            if not paper and entry.risutwente:
                paper = paperpreload.filter(locations__landing_page_url__icontains=entry.risutwente).first()
            if not paper and entry.researchutwente:
                paper = paperpreload.filter(locations__landing_page_url__icontains=entry.researchutwente).first()
            if not paper:
                paper = paperpreload.filter(title__icontains=entry.title).first()
            if not paper and entry.duplicate_ids:
                for key, value in entry.duplicate_ids.items():
                    if not paper:
                        if key == 'doi':
                            for doi in value:
                                if not paper:
                                    paper = paperpreload.filter(doi=doi).first()
                        if key == 'risutwente' or key == 'researchutwente':
                            for url in value:
                                if not paper:
                                    paper = paperpreload.filter(locations__pdf_url__icontains=url).first()
                                    paper = paperpreload.filter(locations__landing_page_url__icontains=url).first()
            if not paper and entry.other_links:
                if isinstance(entry.other_links, dict):
                    if 'other' in entry.other_links:
                        for value in entry.other_links['other']:
                            if not paper:
                                value = value.replace('https://ezproxy2.utwente.nl/login?url=', '')
                                paper = paperpreload.filter(locations__pdf_url__icontains=value).first()
                                paper = paperpreload.filter(locations__landing_page_url__icontains=value).first()
                if isinstance(entry.other_links, str):
                    link = entry.other_links.replace('https://ezproxy2.utwente.nl/login?url=', '')
                    paper = paperpreload.filter(locations__pdf_url__icontains=link).first()
                    paper = paperpreload.filter(locations__landing_page_url__icontains=link).first()


        if paper:
            entry.paper = paper
            paper.has_pure_oai_match = True
            paperlist.append(paper)
            entrylist.append(entry)
            if not found:
                logger.debug("found initial paper for entry %s", entry.id)
            else:
                logger.debug("found new paper for entry %s", entry.id)
        else:
            skiplist.append(entry.id)
            logger.debug("no paper found for entry %s", entry.id) #no match or no new match

        if j == 500:
            with open('skiplist.pickle', 'wb') as f:
                pickle.dump(skiplist, f)
            print("skiplist.pickle updated -- total added this session is " + str(len(skiplist)) + " entries")
            i=update(i, paperlist, entrylist)
            print(f"{paperlist=}")
            print(f"{entrylist=}")
            paperlist=[]
            entrylist=[]
            j=0

    update(i, paperlist, entrylist)
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
def fixavatars():
    data = UTData.objects.all()

    for entry in data:
        url = entry.avatar.url
        entry.avatar_path = url.replace('https://people.utwente.nl/','author_avatars/')
        entry.save()