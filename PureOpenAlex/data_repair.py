from .models import (
    PureEntry,
    Organization,
    Author,
    Paper,
    Journal,
    DealData,
    DBUpdate
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

def migrate_department_data():
    from PureOpenAlex.models import UTData
    from collections import defaultdict
    from django.db import transaction

    utdatalist=UTData.objects.all().only("departments").prefetch_related("departments")
    facultylist = ['EEMCS', 'BMS', 'ET', 'ITC', 'TNW']
    savelist=[]
    i=0
    j=0
    for data in utdatalist:
        depts=list(data.departments.all())
        i=i+1
        data.employment_data = defaultdict(list)
        if not depts:
            data.current_faculty=""
            data.current_group=""
            data.employment_data['employment'].append({})
        elif len(depts)==1:
            j=j+1
            data.current_faculty=depts[0].faculty
            data.current_group=depts[0].name
            data.employment_data['employment'].append({'faculty':depts[0].faculty,'group':depts[0].name})
        else:
            current=False
            for dept in depts:
                j=j+1
                if not current:
                    if dept.faculty in facultylist:
                        data.current_faculty=dept.faculty
                        data.current_group=dept.name
                        current=True
                data.employment_data['employment'].append({'faculty':dept.faculty,'group':dept.name})
            if not current:
                data.current_faculty=data.employment_data['employment'][0]['faculty']
                data.current_group=data.employment_data['employment'][0]['group']
        savelist.append(data)
        if i%100==0 or i==len(utdatalist):
            logger.debug(f'{i} UTData entries with {j} related Departments processed')
            with transaction.atomic():
                UTData.objects.bulk_update(savelist, ['current_faculty', 'current_group', 'employment_data'])
            savelist=[]

def removeDuplicates():
    """
    Removes duplicates from the database.
    Currently implemented for Organizations, PureEntries and Papers.

    """
    return False
    # TODO: fix for new db structure
    # Organizations
    # Clean wrong UT entries
    organizations_to_delete = Organization.objects.filter(
        Q(name__in=TWENTENAMES), Q(ror__isnull=True) | Q(ror="")
    )
    if len(organizations_to_delete) == 0:
        logger.debug("No wrong UT orgs found to delete")
    else:
        logger.info("deleting these wrong UT orgs:")
        for org in organizations_to_delete:
            logger.info(org.name)
        with transaction.atomic():
            organizations_to_delete.delete()
    # clean all detected duplicate entries
    clean_duplicate_organizations()

    # Papers
    duplicates = (
        Paper.objects.values("doi")
        .annotate(title_count=Count("id"))
        .filter(title_count__gt=1)
    )
    for duplicate in duplicates:
        papers_to_check = Paper.objects.filter(title=duplicate["title"]).annotate(
            row_number=Window(
                expression=RowNumber(),
                partition_by=[F("title")],
                order_by=F("id").asc(),
            )
        )
        with transaction.atomic():
            papers_to_check.filter(row_number__gt=1).delete()
        logger.info("Deleted duplicate papers for title: %s", duplicate["title"])

    # Pureentries
    duplicates = (
        PureEntry.objects.values("title", "itemtype", "source", "format")
        .annotate(count=Count("id"))
        .filter(count__gt=1)
    )
    for duplicate in duplicates:
        entries_to_check = PureEntry.objects.filter(
            title=duplicate["title"],
            itemtype=duplicate["itemtype"],
            source=duplicate["source"],
            format=duplicate["format"],
        ).annotate(
            row_number=Window(
                expression=RowNumber(),
                partition_by=[F("title"), F("itemtype"), F("source"), F("format")],
                order_by=F("id").asc(),
            )
        )
        with transaction.atomic():
            entries_to_check.filter(row_number__gt=1).delete()
        logger.info("Deleted duplicates for pureentry: %s", duplicate["title"])

    # Authors
    duplicates = (
        Author.objects.values("name").annotate(count=Count("id")).filter(count__gt=1)
    )
    for duplicate in duplicates:
        authors_to_check = Author.objects.filter(name=duplicate["name"]).annotate(
            row_number=Window(
                expression=RowNumber(),
                partition_by=[F("name")],
                order_by=F("id").desc(),
            )
        )
        with transaction.atomic():
            authors_to_check.filter(row_number__gt=1).delete()
        logger.info("Deleted duplicates for author: %s", duplicate["name"])

def clean_duplicate_organizations():
    """
    Companion function for removeDuplicates().
    """
    return False
    # TODO: fix for new db structure
    duplicates = (
        Organization.objects.values("name")
        .annotate(name_count=Count("id"), min_id=Min("id"))
        .filter(name_count__gt=1)
    )
    logger.debug("found %s duplicate orgs, fixing.", len(duplicates))
    for duplicate in duplicates:
        organizations = (
            Organization.objects.filter(name=duplicate["name"])
            .annotate(ror_exists=Max("ror"))
            .order_by("-ror_exists", "id")
        )
        keeper = organizations.first()
        logger.debug(
            "found %s orgs with name %s", len(organizations), duplicate["name"]
        )
        for org in organizations:
            with transaction.atomic():
                if org == keeper:
                    continue
                if org.country_code == keeper.country_code:
                    if not org.ror:
                        logger.debug(
                            "deleting no ror entry %s, with country code %s and ror %s",
                            org.name,
                            org.country_code,
                            org.ror,
                        )
                        org.delete()
                    else:
                        if (
                            org.name == keeper.name
                            and org.country_code == keeper.country_code
                            and org.ror == keeper.ror
                        ):
                            logger.debug(
                                "deleting old entry %s, %s, %s",
                                org.name,
                                org.country_code,
                                org.ror,
                            )
                            org.delete()
                else:
                    org.name = f"{org.name}_{org.id}"
                    logger.debug("renaming %s to %s", keeper.name, org.name)
                    org.save()
'''
def matchAFASwithAuthor():
    allAFAS = AFASData.objects.filter(authors__isnull=True)
    authorlist = []
    matchdata=[]
    for afas in allAFAS:
        author = Author.objects.filter(name=afas.name).first()
        if author:
            author.afas_data=afas
            authorlist.append(author)
            matchdata.append([author.name,afas.name])
            continue
        author = Author.objects.filter(orcid=afas.orcid).first()
        if author:
            author.afas_data=afas
            authorlist.append(author)
            matchdata.append([author.orcid,afas.orcid])
            continue
        author = Author.objects.filter(first_name=afas.first_name, last_name=afas.last_name).first()
        if author:
            author.afas_data=afas
            authorlist.append(author)
            matchdata.append([author.first_name+" "+author.last_name,afas.first_name+" "+afas.last_name])
            continue

    print(matchdata)
    print(len(authorlist))
    with transaction.atomic():
        Author.objects.bulk_update(authorlist, ['afas_data'])
    from .namematcher import NameMatcher

    from pyalex import Authors
    from nameparser import HumanName
    name_matcher = NameMatcher()

    results=[]
    if allAFAS.count() > 0:
        allAFAS = AFASData.objects.filter(authors__isnull=True)

        for data in allAFAS:
            print("=====================")
            origname=HumanName(data.name)
            if data.pub_name!="":
                searchname=data.pub_name
            else:
                searchname=origname.first + " " + origname.last
            print("searching for",searchname)
            query=Authors().filter(affiliations={"institution":{"ror": "https://ror.org/006hf6230"}}).filter(display_name={"search":searchname}).get()
            if len(query)==0:
                name=HumanName(data.first_name+" "+data.last_name)
                searchname=name.initials()+" "+data.last_name
                print("retrying with initials:",searchname)
                query=Authors().filter(affiliations={"institution":{"ror": "https://ror.org/006hf6230"}}).filter(display_name={"search":searchname}).get()
            if len(query)==0:
                searchname=data.last_name
                print("retrying with last name only:",searchname)
                query=Authors().filter(affiliations={"institution":{"ror": "https://ror.org/006hf6230"}}).filter(display_name={"search":searchname}).get()
            if len(query)>0:
                print("got "+str(len(query))+" results.")
                if len(query)==1:
                    results.append([query[0],1,origname,query[0]['display_name']])
                    print("adding data belonging to primary display name "+str(query[0]['display_name'])+" as a match for "+str(origname))
                    continue
                tmpresults={}
                namelist=[]
                for entry in query:
                    print(entry['display_name'], entry['display_name_alternatives'])
                    tmpresults[entry['display_name']]=entry
                    namelist.append(entry['display_name'])
                score=0
                hitname=""

                for procname in namelist:
                    templist=tmpresults[procname]['display_name_alternatives']
                    templist.append(procname)
                    templist=[HumanName(x) for x in templist]
                    for tname in templist:
                        newscore = name_matcher.match_names(
                        origname.first + " " + origname.last,
                        tname.first + " " + tname.last,
                        )


                        if newscore > score:
                            matchtname=tname
                            score=newscore
                            hitname=procname

                print("Highest matching score "+str(score)+" for name: "+str(matchtname))
                print("adding data belonging to primary display name "+str(hitname)+" as a match for "+str(origname))
                results.append([tmpresults[hitname],score,origname,hitname])
            else:
                print("No results found.")

    print(str(len(results))+" openalex matches of "+str(allAFAS.count())+" missing in total")
    return results
'''