from django.db import models, transaction
from django.db.models import Q, Prefetch, Exists, OuterRef, Count, prefetch_related_objects
from collections import defaultdict
from loguru import logger
from .constants import TCSGROUPS, TCSGROUPSABBR, EEGROUPS, EEGROUPSABBR, FACULTYNAMES, CSV_EXPORT_KEYS, CSV_EEMCS_KEYS
from datetime import datetime
from django.apps import apps
import re
from django.conf import settings
import pymongo
from rapidfuzz import process, fuzz, utils
import os
import requests
from io import StringIO
import csv
MONGOURL = getattr(settings, "MONGOURL")
client=pymongo.MongoClient(MONGOURL)
db=client['mus']
pure_cerif_authors = db['pure_cerif_authors']
pure_cerif_works = db['pure_cerif_works']
pure_cerif_journals = db['pure_cerif_journals']
pure_cerif_categories = db['pure_cerif_categories']
pure_org_mapping = db['pure_org_mapping']
pure_full_orgs_mapping = db['pure_full_orgs_mapping']
pure_cerif_ut_authors = db['pure_cerif_ut_authors']

class AuthorManager(models.Manager):
    # possible TODO
    # Deduplicate authors
    # Check if author is UT or not
    # repair/manage utdata
    # repair/manage authorships

    @transaction.atomic
    def fix_avatars(self, download=False):
        UTData = apps.get_model('PureOpenAlex', 'UTData')
        data = UTData.objects.all()
        logger.info(f'adding avatar paths for {data.count()} UTData entries')
        all_paths = []
        urlmapping = {}
        for entry in data:
            try:
                url = entry.avatar.url
                entry.avatar_path = url.replace(r'/https%3A/people.utwente.nl/','author_avatars/').replace(r'/picture','')
                all_paths.append(entry.avatar_path)
                urlmapping[entry.avatar_path] = url
                entry.save()
            except Exception as e:
                logger.warning(f'failed to add avatar path for utdata id {entry.id}: {e}')

        if download:
            if getattr(settings, "DEBUG"):
                root = getattr(settings, "BASE_DIR", None)
                avatardir = 'author_avatars'
                fullpath = os.path.join(root,'static', avatardir)
            else:
                root = getattr(settings, "STATIC_ROOT", None)
                avatardir = 'author_avatars'
                fullpath = os.path.join(root, avatardir)
            logger.info(f'checking which avatars are not yet downloaded to {fullpath}')
            # get list of all avatars in fullpath
            avatars = [f for f in os.listdir(fullpath) if os.path.isfile(os.path.join(fullpath, f))]
            # from all_paths, remove all avatars that are in avatars and get the corresponding urls
            download_avatars = [f for f in all_paths if f.split('/')[-1] not in avatars]
            urls = [urlmapping[f] for f in download_avatars]
            # download all urls to avatardir
            logger.info(f'downloading {len(urls)} avatars to {fullpath}')
            for url in urls:
                r = requests.get(url.replace(r'/https%3A/','https://'))
                avpath = os.path.join(fullpath, url.replace(r'/https%3A/people.utwente.nl/','').replace(r'/picture',''))
                with open(avpath, 'wb') as f:
                    f.write(r.content)

                logger.debug(f'downloaded {url} to {avpath}')

        logger.info('done with author.objects.fix_avatars()')


    def fix_affiliations(self):
        def getorgs(affils):
            Organization = apps.get_model('PureOpenAlex', 'Organization')
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
                except Exception as e:
                    logger.error(f'error adding org, skipping. Error: {e}')
                    pass
                affiliations.append([org, years])
            return affiliations

        authorlist = self.filter(affils__isnull=True).distinct()
        logger.info(f"Adding affils for {len(authorlist)} authors")
        api_responses_authors_openalex = db['api_responses_authors_openalex']
        added=0
        checked=0
        failed=0
        for author in authorlist:
            with transaction.atomic():
                raw_affildata = None
                oa_data = api_responses_authors_openalex.find_one({"id":author.openalex_url})
                try:
                    raw_affildata = oa_data.get('affiliations')
                except Exception:
                    pass
                if not oa_data or not raw_affildata:
                    oa_data = api_responses_authors_openalex.find_one({"id":author.openalex_url})
                try:
                    raw_affildata = oa_data.get('affiliations')
                except Exception:
                    pass
                if not oa_data or not raw_affildata:
                    logger.warning(f"Cannot find data for author {author.openalex_url} | {author.name} in MongoDB")
                    failed+=1
                else:
                    checked+=1
                    affiliations = getorgs(raw_affildata)
                    for aff in affiliations:
                        try:
                            with transaction.atomic():
                                author.affils.add(aff[0],through_defaults={'years':aff[1]})
                                author.save()
                                added+1
                        except Exception as e:
                            logger.error(f'error adding affil for {author.name}: {e}')
        amount = self.filter(affils__isnull=True).distinct().count()
        logger.info(f"{amount} authors still have no affils.")
        DBUpdate = apps.get_model('PureOpenAlex', 'DBUpdate')
        with transaction.atomic():
            dbu = DBUpdate.objects.create(update_source='OpenAlex', update_type='Author.objects.fix_affiliations()', details={'amount_without_affils_after':amount, 'amount_new':added, 'amount_failed':failed, 'amount_checked':checked})
            dbu.save()

    def update_from_cerif(self):
        def process_cerif_data(author, cerif_author_data):
            if cerif_author_data.get('affiliation_details'):
                    for affil in cerif_author_data.get('affiliation_details'):
                        group = None
                        faculty = None
                        if affil.get('name'):
                            group = affil.get('name')
                            start = affil.get('start_date')
                            end = affil.get('end_date')
                            uuid = affil.get('uuid')
                            pureid = affil.get('pureid')
                            details = pure_full_orgs_mapping.find_one({'name':affil.get('name')})
                            if details:
                                faculty = details.get('faculty')
                        if group and faculty:
                            fullgroup = {
                                'name':group,
                                'uuid':uuid,
                                'pureid':pureid,
                                'start_date':start,
                                'end_date':end,
                                'faculty':faculty
                            }

                            utdata = UTData.objects.filter(employee=author).first()
                            if utdata:
                                if utdata.employment_data:
                                    utdata.employment_data = utdata.employment_data.append(fullgroup)
                                else:
                                    utdata.employment_data = [fullgroup]
                                if fullgroup.get('end_date') in ['2', ''] or fullgroup.get('end_date') is None or len(fullgroup.get('end_date')) < 6:
                                    utdata.current_group = group
                                    utdata.current_faculty = faculty
                                utdata.pure_uuid = cerif_author_data.get('id')
                                utdata.save()
                            else:
                                UTData.objects.create(employee=author, employment_data=[fullgroup], pure_uuid=cerif_author_data.get('id'), current_group=group, current_faculty=faculty)
        UTData = apps.get_model('PureOpenAlex', 'UTData')
        count=0
        authors_with_orcid = self.filter(orcid__isnull=False)
        for author in authors_with_orcid:
            orcid = str(author.orcid).replace('http://orcid.org/','').replace('https://orcid.org/','')
            cerif_author_data = pure_cerif_ut_authors.find_one({'orcid':orcid})
            if cerif_author_data:
                process_cerif_data(author, cerif_author_data)
                count += 1

        authors_without_orcid = self.filter(orcid__isnull=True)
        for author in authors_without_orcid:
            name = author.name
            cerif_author_data = pure_cerif_ut_authors.find_one({'name':name})
            if not cerif_author_data:
                known_as = author.known_as
                if known_as:
                    for name in known_as:
                        cerif_author_data = pure_cerif_ut_authors.find_one({'name':name})
                        if cerif_author_data:
                            break
            if cerif_author_data:
                count += 1
                process_cerif_data(author, cerif_author_data)
        print(count)

    def fix_abbrs(self):
        UTData = apps.get_model('PureOpenAlex', 'UTData')
        wrongabbrs = UTData.objects.exclude(current_faculty__in=FACULTYNAMES)
        for data in wrongabbrs:
            if 'Electrical' in data.current_faculty:
                data.current_faculty = 'EEMCS'
            elif 'Behavioral' in data.current_faculty:
                data.current_faculty = 'BMS'
            elif 'Science and Technology' in data.current_faculty:
                data.current_faculty = 'TNW'
            if len(data.current_group) > 6:
                print(data.current_group)
                short = ''.join(re.findall('[A-Z]+',data.current_group))
                print(short)
                conf = input('y/n')
                if conf == 'y':
                    data.current_group = short
                else:
                    new = input('new name: ')
                    data.current_group = new
            data.save()

class AuthorQuerySet(models.QuerySet):
    # simplify getting names/name combinations
    # filter by group/faculty/affil/authorship data/etc
    def get_affiliations(self, author_id):
        author = self.filter(id=author_id).prefetch_related('affiliations').first()
        return author.affiliations.all().prefetch_related('organization').all().order_by('-years__-1')
    def get_ut_groups(self, grouplist=None, unique=True):
        '''
        Returns all UT groups for the authors in the queryset
        parameter grouplist: return only groups in this list
        '''
        groups=[]
        UTData = apps.get_model('PureOpenAlex', 'UTData')
        allutdata = UTData.objects.filter(employee__in=self.all())
        for utdata in allutdata:
            tmpgroups=[]
            tmpgroups.append(utdata.current_group)
            if utdata.employment_data:
                for entry in utdata.employment_data:
                    tmpgroups.append(entry.get('group'))
            if grouplist:
                for group in tmpgroups:
                    if group in grouplist:
                        groups.append(group)
        if unique:
            return list(set(groups))
        return groups
    def get_ut_corresponding_authors(self, paper):
        utauthors = self.filter(utdata__isnull=False).distinct()
        returnlist = []
        for authorship in paper.authorships.all():
            if authorship.corresponding:
                if authorship.author in utauthors:
                    returnlist.append(authorship.author)
        return returnlist
class PureEntryManager(models.Manager):

    def add_authors(self):
        entries_with_no_authors = self.filter(authors__isnull=True)
        Author = apps.get_model('PureOpenAlex', 'Author')
        dbauthordata = Author.objects.order_by('last_name','first_name').only('id','openalex_url','name','first_name','last_name','known_as', 'initials')
        matchlist = []
        idnamemapping = defaultdict(set)
        i = 0
        api_responses_pure = db['api_responses_pure']
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
        for entry in entries_with_no_authors:
            num_authors = entry.authors.count()
            mongodata = api_responses_pure.find_one({'title':entry.title})

            if not mongodata:
                mongodata = api_responses_pure.find_one({'identifier':{'ris_file':entry.risutwente}})
            if not mongodata:
                mongodata = api_responses_pure.find_one({'identifier':{'researchutwente':entry.researchutwente}})
            if not mongodata:
                mongodata = api_responses_pure.find_one({'identifier':{'doi':entry.doi}})
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
                continue

            total += len(authorlist) - len(authorlist)

            with transaction.atomic():
                for author in authorlist:
                    matches = process.extract(author,matchlist, processor=utils.default_process, scorer=fuzz.QRatio, score_cutoff=90)
                    if len(matches) == 0 or not matches:
                        failed += 1
                    else:
                        matchname=matches[0][0]
                        authorid=idnamemapping[matchname]
                        if isinstance(authorid, set):
                            matched += 1
                            id = max(authorid)
                            authorobj = Author.objects.get(id=id)
                            if authorobj:
                                if authorobj not in entry.authors.all():
                                    logger.debug(f'match: {author} == {authorobj.name} ({authorobj.id}) | score {matches[0][1]}')
                                    entry.authors.add(authorobj)
                                    entry.save()
                                else:
                                    ...
                                    #logger.info(f'{authorobj.name} already linked with entry')
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
        DBUpdate = apps.get_model('PureOpenAlex', 'DBUpdate')
        dbu = DBUpdate.objects.create(details=details,update_source='OpenAlex', update_type='PureEntry.objects.add_authors()')
        dbu.save()
    def link_with_mongo_pure_reports(self):
        mongocols = [db['pure_report_ee'], db['pure_report_start_tcs']]
        resultdict={}
        logger.info(f'Linking these mongodb pure report collections with PureEntries: {[x.name for x in mongocols]}')
        for group in mongocols:
            resultdict[group.name]={'items_checked':0,'new_matches':0,'no_doi':0,'already_matched':0,'no_match_other':0, 'matched_pure_entry_ids':[]}
            logger.info(f'Checking {group.count_documents({})} items in {group.name}')
            for item in group.find().sort('year', pymongo.DESCENDING):
                resultdict[group.name]['items_checked']+=1
                if item.get('pure_entry_id'):
                    resultdict[group.name]['already_matched']=resultdict[group.name]['already_matched']+1
                    continue
                if not item.get('dois'):
                    resultdict[group.name]['no_doi']+=1
                    group.update_one({'pureid': item['pureid']}, {'$set': {'pure_entry_id': None}})
                    continue
                doi = item.get('dois')
                if isinstance(doi, list):
                    logger.warning(f"more than 1 doi found while matching {item['title']}/{item['pureid']}, picked first in list. List: {doi}")
                    doi=doi[0]
                if isinstance(doi, str):
                    if doi.startswith('https://doi.org/'):
                        pass
                    else:
                        doi = 'https://doi.org/' + doi
                pureentry = self.filter(doi=doi)
                if not pureentry:
                    pureentry = self.filter(doi=doi.lower())
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
                            pureentry = self.filter(scopus=scopuslink)
                if not pureentry:
                    pureid = item.get('pureid')
                    pureentry = self.filter(risutwente__icontains=pureid)
                if pureentry.count()>0:

                    if pureentry.count == 1:
                        pure_entry_id = pureentry[0].id
                        group.update_one({'pureid': item['pureid']}, {'$set': {'pure_entry_id': pure_entry_id}})
                        resultdict[group.name]['new_matches']+=1
                        resultdict[group.name]['matched_pure_entry_ids'].append(pure_entry_id)
                    else:
                        pure_entry_ids=[]
                        for pureentry in pureentry:
                            pure_entry_ids.append(pureentry.id)
                            resultdict[group.name]['matched_pure_entry_ids'].append(pureentry.id)
                            resultdict[group.name]['new_matches']+=1
                        group.update_one({'pureid': item['pureid']}, {'$set': {'pure_entry_id': pure_entry_ids}})
                else:
                    resultdict[group.name]['no_match_other']+=1
                    group.update_one({'pureid': item['pureid']}, {'$set': {'pure_entry_id': None}})


        DBUpdate = apps.get_model('PureOpenAlex', 'DBUpdate')
        with transaction.atomic():
            dbu = DBUpdate.objects.create(update_source='PureReportsMongoDB', update_type='PureEntry.objects.link_with_mongo_pure_reports()', details=resultdict)
            dbu.save()
        logger.info(f"Done matching. Results: {resultdict}")

    def link_with_postgres_pure_reports(self):
        PilotPureData = apps.get_model('PureOpenAlex', 'PilotPureData')
        mongocols = [db['pure_report_ee'], db['pure_report_start_tcs']]
        resultdict={}
        logger.info(f'Linking PilotPureData entries to PureEntries using data from these mongodb collections: {[x.name for x in mongocols]}')
        for group in mongocols:
            resultdict[group.name]={'items_checked':0,'with_pure_entry_id':0,'new_matches':0}
            logger.info(f'Checking {group.count_documents({})} items in {group.name}')
            for item in group.find().sort('year', pymongo.DESCENDING):
                resultdict[group.name]['items_checked']+=1
                if item.get('pure_entry_id'):
                    resultdict[group.name]['with_pure_entry_id']=resultdict[group.name]['with_pure_entry_id']+1
                    if isinstance(item.get('pure_entry_id'), list):
                        for id in item.get('pure_entry_id'):
                            pureentry = self.get(id=id)
                            if not pureentry.pilot_pure_data:
                                pilotdata = PilotPureData.objects.get(pureid=item.get('pureid'))
                                with transaction.atomic():
                                    pureentry.pilot_pure_data = pilotdata
                                    pureentry.save()
                                    resultdict[group.name]['new_matches']=resultdict[group.name]['new_matches']+1
                    elif isinstance(item.get('pure_entry_id'), str):
                        pureentry = self.get(id=int(item.get('pure_entry_id')))
                        if not pureentry.pilot_pure_data:
                            pilotdata = PilotPureData.objects.get(pureid=item.get('pureid'))
                            with transaction.atomic():
                                pureentry.pilot_pure_data = pilotdata
                                pureentry.save()
                                resultdict[group.name]['new_matches']=resultdict[group.name]['new_matches']+1

        DBUpdate = apps.get_model('PureOpenAlex', 'DBUpdate')
        with transaction.atomic():
            dbu = DBUpdate.objects.create(update_source='PureReportsMongoDB', update_type='PureEntry.objects.link_with_postgres_pure_reports()', details=resultdict)
            dbu.save()
        logger.info(f"Done matching. Results: {resultdict}")

    def link_papers(self, advanced = True):
        """
        For every PureEntry, try to find a matching paper in the database and mark them as such.
        """
        paperlist = []
        entrylist = []
        checked = []
        checkedentries=0
        Paper = apps.get_model('PureOpenAlex', 'Paper')

        allentries = self.filter(Q(paper__isnull=True) & Q(checked_for_match=False))
        paperpreload = Paper.objects.all().only("doi","title",'locations','id').prefetch_related('locations')
        logger.info('Trying to find matches for ' + str(allentries.count()) + ' PureEntries in ' + str(paperpreload.count()) + 'unmatched papers')
        for entry in allentries:
            if checkedentries % 1000  == 0:
                logger.info(f'matched {len(entrylist)}/{checkedentries} entries to {len(paperlist)} papers. {len(allentries)-checkedentries} entries left to check.')

            checkedentries=checkedentries+1
            found=False
            paper = None
            if entry.paper is not None or entry.paper == "":
                found=True
                logger.warning(f'entry {entry.id} already has match; should not be in the list')
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
            entry.checked_for_match = True
            checked.append(entry)
            if paper:
                with transaction.atomic():
                    entry.paper = paper
                    paper.has_pure_oai_match = True
                paperlist.append(paper)
                entrylist.append(entry)
                if not found:
                    logger.debug(f"found first paper for entry {entry.id}")
                else:
                    logger.debug(f"added extra paper for entry {entry.id}")
            else:

                ... #no match found

        with transaction.atomic():
            Paper.objects.bulk_update(paperlist, fields=["has_pure_oai_match"])
            self.bulk_update(entrylist, fields=["paper"])
            self.bulk_update(checked, fields=["checked_for_match"])

        logger.info(f"Linked {len(paperlist)} papers with {len(entrylist)} PureEntries after checking {checkedentries} PureEntries")

        DBUpdate = apps.get_model('PureOpenAlex', 'DBUpdate')
        dbu = DBUpdate.objects.create(update_source='PureEntries', update_type='PureEntry.objects.link_papers()', details={'new_linked_papers':[x.id for x in paperlist],'linked_to_entries':[x.id for x in entrylist],'amount_checked':checkedentries})
        dbu.save()

class JournalManager(models.Manager):
    api_responses_journals_dealdata_scraped = db["api_responses_journals_dealdata_scraped"]
    api_responses_journals_openalex = db["api_responses_journals_openalex"]

    @transaction.atomic
    def get_or_make_from_api_data(self, locdata):
        def get_deal_data(self, openalex_id):
            dealdatacontents = self.api_responses_journals_dealdata_scraped.find_one({"id":openalex_id})
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
        created = False
        DealData=apps.get_model('PureOpenAlex', 'DealData')
        data=locdata.get('source')
        if not data:
            logger.error('no data received, returning None')
            return None, None
        if self.filter(openalex_url=data.get('id')).exists():
            logger.info(f'journal {data.get("id")} already exists in mus db, updating & returning it')
            journal = self.filter(openalex_url=data.get('id')).first()
            host_org = data.get('host_organization_lineage_names','')
            if isinstance(host_org, list) and len(host_org) > 0:
                host_org = host_org[0]
            if host_org != '' and journal.host_org != host_org:
                journal.host_org = host_org
                journal.save()
            if not journal.dealdata:
                dealdata, keywords, publisher = get_deal_data(self, journal.openalex_url)
                if dealdata:
                    deal, ddcreated = DealData.objects.get_or_create(**dealdata)
                    if ddcreated:
                        deal.save()
                    journal.dealdata = deal
                    journal.keywords = keywords
                    journal.publisher = publisher
                    journal.save()
            return journal, created
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

        dealdata, keywords, publisher = get_deal_data(self, journaldata['openalex_url'])
        journaldata['keywords']=keywords
        journaldata['publisher']=publisher if publisher else ""
        journal, created = self.get_or_create(**journaldata)
        if created:
            journal.save()
            logger.info(f'journal {journal.name} / {journal.openalex_url} created in mus db')
        if dealdata and not journal.dealdata:
            deal, ddcreated = DealData.objects.get_or_create(**dealdata)
            if ddcreated:
                deal.save()
            journal.dealdata=deal
            logger.info(f'dealdata for journal {journal.name} / {journal.openalex_url} added in mus db')
            journal.save()



        return journal, created
class PaperManager(models.Manager):
    api_responses_works_openalex = db["api_responses_works_openalex"]
    api_responses_journals_openalex = db["api_responses_journals_openalex"]

    def remove_duplicates(self):
        # for django object Paper, remove all duplicates from the database (based on openalex_url)
        Paper = apps.get_model('PureOpenAlex', 'Paper')
        duplicate_papers_doi = (
            Paper.objects.values("doi")
            .annotate(title_count=Count("id"))
            .filter(title_count__gt=1)
        )
        duplicate_dois = duplicate_papers_doi.values_list('doi', flat=True)
        duplicate_papers_oa = (
            Paper.objects.values("openalex_url")
            .annotate(title_count=Count("id"))
            .filter(title_count__gt=1)
        )
        duplicate_openalex_urls = duplicate_papers_oa.values_list('openalex_url', flat=True)
        logger.info(f'Found {duplicate_papers_doi.count()+duplicate_papers_oa.count()} duplicate papers with {len(duplicate_dois)} duplicate dois {len(duplicate_openalex_urls)} duplicate openalex_urls')
        c = 0
        if len(duplicate_openalex_urls) > 0:
            logger.warning('function will run, but it is not implemented yet so it wont delete anything')
        for url in duplicate_openalex_urls:
            c+=1
            papers = Paper.objects.filter(openalex_url=url).order_by('-modified')
            logger.debug(f'Removing dupes with OA url {url}')
            i=0
            for paper in papers:
                if paper.pure_entries.count() > 0:
                    i+=1
                    for entry in paper.pure_entries.all():
                        print(entry.id)

            if papers.filter(pure_entries_isnull=True).count() == papers.count():
                keep_paper = papers.latest('modified')
                if not i == 0:
                    logger.warning(f'Possible error while running paper.remove_duplicates() with paper {paper.id}')
            elif papers.filter(pure_entries__isnull=False).count() == 1:
                keep_paper = papers.filter(pure_entries__isnull=False).first()

                if not i == 1:
                    logger.warning(f'Possible error while running paper.remove_duplicates() with paper {paper.id}')
            else:
                keep_paper = papers.annotate(num_pure_entries=Count('pure_entries')).order_by('-num_pure_entries', '-modified').first()
                if not i > 1:
                    logger.warning(f'Possible error while running paper.remove_duplicates() with paper {paper.id}')
            #papers.exclude(id=keep_paper.id).delete()
            logger.info(f'Keeping: {keep_paper.id}. Deleting: {[paper.id for paper in papers.exclude(id=keep_paper.id).all()]}')
            logger.warning('Not implemented: so not actually deleting anything.')
            if c == 5:
                break


    def link_journals(self):
        articles_with_missing_journals = self.get_queryset().get_all_without_journal().get_articles()
        other_items_with_missing_journals = self.get_queryset().get_all_without_journal().get_other_itemtypes()
        DBUpdate = apps.get_model('PureOpenAlex', 'DBUpdate')
        Journal = apps.get_model('PureOpenAlex', 'Journal')
        added, checked, numcreated, checklist, missingarticles, otherjournal, paperlist = 0, 0, 0, 0, 0, 0, []
        for grouping in [articles_with_missing_journals, other_items_with_missing_journals]:
            checklist +=1
            if checklist == 1:
                itype = 'article'
            else:
                itype = ''
            for item in grouping:
                checked+=1
                created = False
                journal = None
                data = self.api_responses_works_openalex.find_one({'id':item.openalex_url})
                if itype == '':
                    itype = item.itemtype
                ident = f'[id] {item.id} [type] {itype}'
                if not data:
                    cat = '[Warning] [Skipped]'
                    msg = 'No OpenAlex URL for paper'
                    logger.warning(f"{cat:<20} {msg:^30} {ident:>20}")
                    continue
                if data.get('primary_location'):
                    if data.get('primary_location').get('source'):
                        if data.get('primary_location').get('source').get('type') == 'journal':
                            journal, created = Journal.objects.get_or_make_from_api_data(data.get('primary_location'))
                if not journal:
                    for loc in data.get('locations'):
                        if loc.get('source'):
                            if loc.get('source').get('type') == 'journal':
                                journal, created = Journal.objects.get_or_make_from_api_data(loc)
                                if journal:
                                    cat = '[Info]'
                                    msg = 'Journal found in loc but not in primary loc.'
                                    logger.info(f"{cat:<20} {msg:^30} {ident:>20}")
                if journal:
                    with transaction.atomic():
                        item.journal = journal
                        item.save()
                    added+=1
                    paperlist.append(item.openalex_url)
                    if created:
                        numcreated+=1
                    if checklist == 2:
                        cat = '[Info]'
                        msg = 'Journal found for non-article'
                        logger.info(f"{cat:<20} {msg:^30} {ident:>20}")
                        otherjournal+=1
                elif checklist == 1:
                    cat = '[Warning]'
                    msg = 'No journal found for article'
                    logger.warning(f"{cat:<20} {msg:^30} {ident:>20}")
                    missingarticles+=1
        detaildict={
            'journals_added_to_papers':added,
            'journals_added_to_non_articles':otherjournal,
            'newly_created_journals':numcreated,
            'changed_papers':paperlist
        }
        with transaction.atomic():
            dbupd=DBUpdate.objects.create(update_source="OpenAlex", update_type="repairjournals", details = detaildict)
            dbupd.save()
        logger.info(f"Paper.objects.link_journals() finished. Results: {detaildict}")
        return detaildict
class PaperQuerySet(models.QuerySet):
    # list of fields that are not returned when calling get_table_data
    TABLEDEFERFIELDS = ['abstract','keywords','pure_entries',
            'apc_listed_value', 'apc_listed_currency', 'apc_listed_value_eur', 'apc_listed_value_usd',
            'apc_paid_value', 'apc_paid_currency', 'apc_paid_value_eur', 'apc_paid_value_usd',
            'published_print', 'published_online', 'issued', 'published',
            'license', 'citations','pages','pagescount', 'volume','issue']

    # convenience functions to get sets of papers based on foreign key fields, itemtype, etc
    def get_all_without_pure_entry(self):
        return self.filter(pure_entries__isnull=True)
    def get_all_with_pure_entry(self):
        return self.filter(pure_entries__isnull=False)
    def get_all_with_journal(self):
        return self.filter(journal__isnull=False)
    def get_all_without_journal(self):
        return self.filter(journal__isnull=True)
    def get_articles(self):
        return self.filter(itemtype='journal-article')
    def get_proceedings(self):
        return self.filter(itemtype='proceedings')
    def get_articles_and_proceedings(self):
        return self.filter(itemtype__in=['journal-article', 'proceedings'])
    def get_other_itemtypes(self):
        return self.exclude(itemtype__in=['journal-article', 'proceedings'])

    # prefetching functions
    def get_table_prefetches(self):
        Location = apps.get_model('PureOpenAlex', 'Location')
        Author = apps.get_model('PureOpenAlex', 'Author')
        PureEntry = apps.get_model('PureOpenAlex', 'PureEntry')
        location_prefetch = Prefetch(
            "locations",
            queryset=Location.objects.filter(papers__in=self.all()).select_related('source'),
            to_attr="pref_locations",
        )
        authors_prefetch =Prefetch(
            'authors',
            queryset=Author.objects.filter(authorships__paper__in=self.all()).distinct().select_related('utdata'),
            to_attr="pref_authors",
        )
        pureentry_prefetch = Prefetch(
            'pure_entries',
            queryset=PureEntry.objects.filter(paper__in=self.all()).select_related('pilot_pure_data'),
            to_attr="pref_pure_entries",
        )
        return self.select_related().prefetch_related(location_prefetch, authors_prefetch, pureentry_prefetch)
    def get_detailed_prefetches(self):
        Location = apps.get_model('PureOpenAlex', 'Location')
        Author = apps.get_model('PureOpenAlex', 'Author')
        Authorship = apps.get_model('PureOpenAlex', 'Authorship')

        authorships_prefetch = Prefetch(
            "authorships",
            queryset=Authorship.objects.filter(paper__in=self.model.objects.all()).select_related(
                "author"
            ),
            to_attr="preloaded_authorships",
        )
        location_prefetch = Prefetch(
            "locations",
            queryset=Location.objects.filter(papers__in=self.model.objects.all()).select_related("source"),
            to_attr="preloaded_locations",
        )
        authors_and_affiliation_prefetch =Prefetch(
            'authors',
            queryset=Author.objects.filter(authorships__paper__in=self.model.objects.all()).distinct()
            .prefetch_related('affils').select_related('utdata'),
            to_attr="preloaded_authors",
        )
        return self.select_related('journal').prefetch_related(location_prefetch, authorships_prefetch, authors_and_affiliation_prefetch)


    def annotate_marked(self, user):
        # return all bookmarks for a user
        if not user:
            return self
        viewPaper = apps.get_model('PureOpenAlex', 'viewPaper')

        return self.annotate(marked=Exists(viewPaper.objects.filter(displayed_paper=OuterRef("pk"))))

    # these functons use multiple functions of this querymanager to return filtered, ordered, annotated, and prefetched lists of papers
    def get_table_data(self, filter: list, user, order='-year'):
        # for all the views that show a table of papers
        return self.filter_by(filter).annotate_marked(user).get_table_prefetches().defer(*self.TABLEDEFERFIELDS).order_by(order)
    def get_single_paper_data(self, paperid, user):
        # for the single_article view
        return self.filter(id=paperid).annotate_marked(user).select_related().get_detailed_prefetches()
    def get_marked_papers(self, user):
        # for the bookmarks view
        return self.filter(view_paper__user=user).order_by("-modified")
    def get_author_papers(self, name):
        # for a list of papers by author
        return self.filter(authors__name=name).distinct().order_by("-year")

    # get all pure entries linked to single paper & prefetch author data
    def get_pure_entries(self, article_id):
        Author = apps.get_model('PureOpenAlex', 'Author')
        article=self.get(pk=article_id)
        pure_entries = article.pure_entries.all()
        author_prefetch=Prefetch(
                'authors',
                queryset=Author.objects.filter(pure_entries__in=pure_entries).distinct()
                .prefetch_related('affiliations').select_related('utdata'),
            )
        pure_entries=pure_entries.prefetch_related(author_prefetch)
        return article, pure_entries
    def filter_by(self, filter: list):
        '''
        the main filtering function for papers
        'filter' is a list with lists/tuples
        each entry contains [filter, value]
        filter is a string that is used to filter the queryset
        value is the value that is used to filter the queryset, often optional

        list of filters:
            Filter name      | Values         | Default
            -----------------|----------------|------------
            'pure_match'     | 'yes','no'     | 'yes'
            'no_pure_match'  | -              | -
            'has_pure_link'  | 'yes','no'     | 'yes'
            'no_pure_link'   | -              | -
            'hasUTKeyword'   | -              | -
            'hasUTKeywordNLA'| -              | -
            'openaccess'     | 'yes','no'     | 'yes'
            'apc'            | -              | -
            'TCS'            | -              | -
            'EE'             | -              | -
            'author'         | author name    | -
            'group'          | group name     | -
            'start_date'     | date           | -
            'end_date'       | date           | -
            'type'           | itemtype       | -
            'faculty'        | faculty name   | -
            'taverne_passed' | -              | -
        '''

        Author = apps.get_model('PureOpenAlex', 'Author')
        if len(filter) == 0:
            return self
        if len(filter) == 1:
            if filter[0][0] == 'all':
                return self

        finalfilters = defaultdict(list)
        for item in filter:
            filter=item[0]
            value=item[1]
            if filter == "pure_match" and value in ['yes', '']:
                finalfilters['bools'].append(Q(has_pure_oai_match=True) )
            if filter == "no_pure_match" or (filter == "pure_match" and value == 'no'):
                finalfilters['bools'].append((Q(
                    has_pure_oai_match=False
                ) | Q(has_pure_oai_match__isnull=True)))
            if filter == "has_pure_link" and value in ['yes', '']:
                finalfilters['bools'].append(Q(is_in_pure=True))
            if filter == "no_pure_link" or (filter == "has_pure_link" and value == 'no'):
                finalfilters['bools'].append((Q(is_in_pure=False) | Q(is_in_pure__isnull=True)))
            if filter == "hasUTKeyword":
                finalfilters['bools'].append(Q(
                pure_entries__ut_keyword__gt=''
                ))
            if filter == "hasUTKeywordNLA":
                finalfilters['bools'].append(Q(pure_entries__ut_keyword="NLA"))
            if filter == 'openaccess':
                if value in ['yes', '', 'true', 'True', True]:
                    finalfilters['bools'].append(Q(is_oa=True))
                if value in ['no', 'false', 'False', False]:
                    finalfilters['bools'].append(Q(is_oa=False))
            if filter == 'apc':
                finalfilters['bools'].append((Q(apc_listed_value__isnull=False) & ~Q(apc_listed_value='')))
            if filter == 'TCS' or filter == 'EE':
                # get all papers where at least one of the authors has a linked AFASData entry that has 'is_tcs'=true
                # also get all papers where at least one of the authors has a linked UTData entry where current_group is in TCSGROUPS or TCSGROUPSABBR
                if filter == 'TCS':
                    grouplist = TCSGROUPS + TCSGROUPSABBR
                elif filter == 'EE':
                    grouplist = EEGROUPS + EEGROUPSABBR
                q_expressions = Q()
                for group_abbr in grouplist:
                    q_expressions |= (
                            Q(
                                authorships__author__utdata__employment_data__contains={'group': group_abbr}
                            )
                        &
                            Q(
                                authorships__author__utdata__employment_data__contains={'faculty':'EEMCS'}
                            )
                    )

                finalfilters['groups'].append(((Q(authorships__author__utdata__current_group__in=grouplist) | q_expressions)) & Q(
                        authorships__author__utdata__current_faculty='EEMCS'
                    ))

            if filter == 'author':
                if isinstance(value, str):
                    value = [value]
                for item in value:
                    author = Author.objects.get(name = item)
                    finalfilters['authors'].append(Q(
                        authorships__author=author
                    ))
            if filter == 'group':
                if isinstance(value, str):
                    value = [value]
                for item in value:
                    group = item
                    finalfilters['groups'].append(Q(
                        authorships__author__utdata__current_group=group
                    ))

            if filter == 'start_date':
                start_date = value
                # should be str in format YYYY-MM-DD
                datefmt=re.compile(r"^\d{4}-\d{2}-\d{2}$")
                if datefmt.match(start_date):
                    finalfilters['dates'].append(Q(
                        date__gte=start_date
                    ))
                else:
                    raise ValueError("Invalid start_date format")

            if filter == 'end_date':
                end_date = value

                # should be str in format YYYY-MM-DD
                datefmt=re.compile(r"^\d{4}-\d{2}-\d{2}$")
                if datefmt.match(end_date):
                    finalfilters['dates'].append(Q(
                        date__lte=end_date
                    ))
                else:
                    raise ValueError("Invalid end_date format")

            if filter == 'type':
                if isinstance(value, str):
                    value = [value]
                for item in value:
                    itemtype = item
                    ITEMTYPES = ['journal-article', 'proceedings', 'proceedings-article','book', 'book-chapter']
                    if itemtype != 'other':
                        if itemtype == 'book' or itemtype == 'book-chapter':
                            finalfilters['types'].append(Q(Q(itemtype='book')|Q(itemtype='book-chapter')))
                        else:
                            finalfilters['types'].append(Q(itemtype=itemtype))
                    else:
                        finalfilters['types'].append(~Q(
                            itemtype__in=ITEMTYPES
                        ))

            if filter == 'faculty':
                if isinstance(value, str):
                    value = [value]
                for item in value:
                    faculty=item
                    if faculty in FACULTYNAMES:
                        faculty = faculty.upper()
                        finalfilters['faculties'].append(Q(
                            authorships__author__utdata__current_faculty=faculty
                        ))
                    else:
                        authors = Author.objects.filter(utdata__isnull=False).filter(~Q(utdata__current_faculty__in=FACULTYNAMES)).select_related('utdata')
                        finalfilters['faculties'].append(Q(authorships__author__in=authors))

            if filter == 'taverne_passed':
                date = datetime.today().strftime('%Y-%m-%d')
                finalfilters['bools'].append(Q(
                    taverne_date__lt=date
                ))
        boolfilter = Q()
        groupfilter = Q()
        facultyfilter= Q()
        typefilter = Q()
        datefilter = Q()
        authorfilter = Q()

        for qfilt in finalfilters['bools']:
            boolfilter = boolfilter & qfilt
        for qfilt in finalfilters['types']:
            typefilter = typefilter | qfilt
        for qfilt in finalfilters['groups']:
            groupfilter = groupfilter | qfilt
        for qfilt in finalfilters['faculties']:
            facultyfilter = facultyfilter | qfilt
        for qfilt in finalfilters['dates']:
            datefilter = datefilter & qfilt
        for qfilt in finalfilters['authors']:
            authorfilter = authorfilter | qfilt

        finalfilter = boolfilter & typefilter & groupfilter & facultyfilter & datefilter & authorfilter

        return self.filter(finalfilter)

    def get_stats(self):
        # returns a dict with stats for the papers in the current queryset
        # currently only used for the 'dbinfo' view
        stats = self.aggregate(
            num=Count("id"),
            numoa=Count("id", filter=Q(is_oa=True)),
            numpure=Count("id", filter=Q(is_in_pure=True)),
            numpurematch=Count("id", filter=Q(has_pure_oai_match=True)),
            numarticles=Count("id", filter=Q(itemtype="journal-article")),
            articlesinpure=Count(
                "id", filter=Q(is_in_pure=True, itemtype="journal-article")
            ),
            articlesinpurematch=Count(
                "id", filter=Q(has_pure_oai_match=True, itemtype="journal-article")
            ),
            numarticlesoa=Count("id", filter=Q(is_oa=True, itemtype="journal-article")),
        )

        stats["oa_percent"] = (
            round((stats["numoa"] / stats["num"]) * 100, 2) if stats["num"] else 0
        )
        stats["numpure_percent"] = (
            round((stats["numpure"] / stats["num"]) * 100, 2) if stats["num"] else 0
        )
        stats["oa_percent_articles"] = (
            round((stats["numarticlesoa"] / stats["numarticles"]) * 100, 2)
            if stats["numarticles"]
            else 0
        )
        stats["articlesinpure_percent"] = (
            round((stats["articlesinpure"] / stats["numarticles"]) * 100, 2)
            if stats["numarticles"]
            else 0
        )
        stats["numpurematch_percent"] = (
            round((stats["numpurematch"] / stats["num"]) * 100, 2)
            if stats["num"]
            else 0
        )
        stats["articlesinpurematch_percent"] = (
            round((stats["articlesinpurematch"] / stats["numarticles"]) * 100, 2)
            if stats["numarticles"]
            else 0
        )
        return stats

    def get_csv(self, filters=[], papers=None, use_api=False):
        if filters:
            logger.info(f'Getting csv data using filters: {filters}')
        else:
            logger.info(f'Getting csv data for {papers.count()} papers')

        if not papers:
            papers =  self.filter_by(filters)
        else:
            papers = papers.filter_by(filters)
        papers=papers.distinct()
        grouplist=[]
        is_eemcs = False
        if filters:
            for filter in filters:
                if filter[0] == 'EE':
                    grouplist.extend(EEGROUPSABBR)
                    is_eemcs = True
                if filter[0] == 'TCS':
                    grouplist.extend(TCSGROUPSABBR)
                    is_eemcs = True
                if filter[0] == 'group':
                    grouplist.append(filter[1])
        if is_eemcs:
            keys = CSV_EEMCS_KEYS
        else:
            keys = CSV_EXPORT_KEYS

        grouplist=list(set(grouplist))
        if use_api:
            from PureOpenAlex.serializers import serialize_as_list_of_dicts
            papers = papers.prefetch_related('locations', 'locations__source','journal', 'journal__dealdata', 'pure_entries', 'authors', 'authors__utdata', 'authors__affils')
            raw_data = serialize_as_list_of_dicts(papers)
            keys = raw_data[0].keys()
        else:
            raw_data=papers.create_csv(grouplist, keys)

        content = StringIO()
        with content as f:
            writer = csv.DictWriter(f, fieldnames=keys)
            writer.writeheader()
            writer.writerows(raw_data)
            return content.getvalue()

    def create_csv(self, groups=None, keys=[]):
        '''
        Returns a list containing a dict with data for each paper in the current queryset.
        Not only data from the paper object -- also from related tables like authors, pure entries, etc.
        Param:
        groups: filter the groups included in the 'ut_groups' column. Defaults to 'None': all ut groups are shown.
        '''
        from rich import print, inspect
        data=[]
        Journal = apps.get_model('PureOpenAlex', 'Journal')
        Authorship = apps.get_model('PureOpenAlex', 'Authorship')
        Author = apps.get_model('PureOpenAlex', 'Author')
        PureEntry = apps.get_model('PureOpenAlex', 'PureEntry')
        PilotPureData = apps.get_model('PureOpenAlex', 'PilotPureData')
        UTData = apps.get_model('PureOpenAlex', 'UTData')

        mus_url = 'https://openalex.samuelmok.cc/'
        mus_api_url = 'https://openalex.samuelmok.cc/api/'
        logger.info(f'Creating list with data for CSV for {self.count()} papers')
        paperlist = self.all().distinct().prefetch_related('journal', 'authorships','authorships__author', 'authors', 'authors__utdata','pure_entries', 'pure_entries__pilot_pure_data', 'locations')
        for paper in paperlist:
            authors = paper.authors.all()
            pure_entries = paper.pure_entries.all()
            journal = paper.journal if paper.journal else ''
            utauthors = [a for a in authors if hasattr(a,'utdata')]
            authorgroups = [author.utdata.current_group for author in utauthors]
            corresponding_authors = [authorship.author for authorship in paper.authorships.all()]
            ut_corresponding_author = ' | '.join([author.name for author in corresponding_authors if hasattr(author,'utdata')])
            best_oa, oa_list = paper.get_oa_links()
            mapping = {}
            for keyname in keys:
                    if keyname == 'title':
                        mapping[keyname] = paper.title
                    if keyname == 'doi':
                        mapping[keyname] = paper.doi
                    if keyname == 'year':
                        mapping[keyname] = paper.year
                    if keyname == 'itemtype':
                        mapping[keyname] = paper.itemtype
                    if keyname == 'isbn':
                        mapping[keyname] = pure_entries[0].isbn if pure_entries else ''
                    if keyname == 'topics':
                        mapping[keyname] = ' | '.join([topic.get('display_name') for topic in paper.topics]) if paper.topics else ''
                    if keyname == 'Authorinfo ->':
                        mapping[keyname] = ''
                    if keyname == 'ut_authors':
                        mapping[keyname] = ' | '.join([author.name for author in utauthors])
                    if keyname == 'ut_groups':
                        mapping[keyname] = ' | '.join(authorgroups) if authorgroups else ''
                    '''
                    if keyname == 'is_eemcs?':
                        mapping[keyname] = paperauthors.filter(Q(utdata__current_faculty__iexact='EEMCS') | Q(utdata__employment_data__contains=[{'faculty':'EEMCS'}])).exists()
                    if keyname == 'is_ee?':
                        mapping[keyname] = paperauthors.filter(Q(utdata__current_group__in=EEGROUPSABBR)).exists() ,
                    if keyname == 'is_tcs?':
                        mapping[keyname] = paperauthors.filter(Q(utdata__current_group__in=TCSGROUPSABBR)).exists(),
                    '''
                    if keyname == 'ut_corresponding_author':
                        mapping[keyname] = ut_corresponding_author if ut_corresponding_author != [] else ''
                    if keyname == 'all_authors':
                        mapping[keyname] = ' | '.join([author.name for author in authors])
                    if keyname == 'Openaccessinfo ->':
                        mapping[keyname] = ''
                    if keyname == 'is_openaccess':
                        mapping[keyname] = paper.is_oa
                    if keyname == 'openaccess_type':
                        mapping[keyname] = paper.openaccess
                    if keyname == 'found_as_green':
                        mapping[keyname] = paper.is_in_pure
                    if keyname == 'present_in_pure':
                        mapping[keyname] = paper.has_pure_oai_match
                    if keyname == 'license':
                        mapping[keyname] = paper.license
                    if keyname == 'URLs ->':
                        mapping[keyname] = ''
                    if keyname == 'primary_link':
                        mapping[keyname] = paper.primary_link
                    if keyname == 'pdf_link_primary':
                        mapping[keyname] = paper.pdf_link_primary
                    if keyname == 'best_oa_link':
                        mapping[keyname] = best_oa['landing_page_url']
                    if keyname == 'pdf_link_best_oa':
                        mapping[keyname] = best_oa['pdf_url']
                    if keyname == 'other_oa_links':
                        mapping[keyname] = ' | '.join(oa_list) if oa_list else ''
                    if keyname == 'openalex_url':
                        mapping[keyname] = paper.openalex_url
                    if keyname == 'pure_page_link':
                        mapping[keyname] = pure_entries[0].researchutwente if pure_entries else ''
                    if keyname == 'pure_file_link':
                        mapping[keyname] = pure_entries[0].risutwente if pure_entries else ''
                    if keyname == 'scopus_link':
                        mapping[keyname] = pure_entries[0].scopus if pure_entries else ''
                    if keyname == 'Journalinfo ->':
                        mapping[keyname] = ''
                    if keyname == 'journal':
                        mapping[keyname] = journal.name if journal else ''
                    if keyname == 'journal_issn':
                        mapping[keyname] = journal.issn if journal else ''
                    if keyname == 'journal_e_issn':
                        mapping[keyname] = journal.e_issn if journal else ''
                    if keyname == 'journal_publisher':
                        mapping[keyname] = journal.publisher if journal else ''
                    if keyname == 'volume':
                        mapping[keyname] = paper.volume
                    if keyname == 'issue':
                        mapping[keyname] = paper.issue
                    if keyname == 'pages':
                        mapping[keyname] = paper.pages
                    if keyname == 'pagescount':
                        mapping[keyname] = paper.pagescount
                    if keyname == 'MUS links ->':
                        mapping[keyname] = ''
                    if keyname == 'mus_paper_details':
                        mapping[keyname] = mus_url+'article/'+str(paper.id)
                    if keyname == 'mus_api_url_paper':
                        mapping[keyname] = mus_api_url+'paper/'+str(paper.id)

            pureentrylist=''
            pilotpuredatalist=''
            if pure_entries:
                for pure_entry in pure_entries:
                    if pureentrylist != '':
                        pureentrylist = ' | '.join([pureentrylist, mus_api_url+'pureentry/'+str(pure_entry.id)])
                    else:
                        pureentrylist = mus_api_url+'pureentry/'+str(pure_entry.id)
                    if 'pilot_pure_data' in pure_entry.__dict__:
                        if pilotpuredatalist != '':
                            pilotpuredatalist = ' | '.join([pilotpuredatalist, mus_api_url+'pilotpure/'+str(pure_entry.pilot_pure_data.id)])
                        else:
                            pilotpuredatalist = mus_api_url+'pilotpure/'+str(pure_entry.pilot_pure_data.id)

            mapping['mus_api_url_pure_entry']=pureentrylist
            mapping['mus_api_url_pure_report_details']=pilotpuredatalist
            data.append(mapping)



        return data

    def exportris(self):
        '''
        this is how the ris fields are imported in Pure
        mapping_ris_to_pure = {
            'T1': 'Title',
            'T2': 'Subtitle or Event name',
            'AU': 'Contributor',
            'N1': 'Bibliographic Note',
            'PY': 'Publication Date',
            'Y1': 'Publication Date',
            'Y2': 'Event Date',
            'AB': 'Abstract',
            'N2': 'Abstract',
            'KW': 'Keyword',
            'UR': 'Other Links',
            'U2': 'DOI',
            'DO': 'DOI',
            'M3': 'Research Output Type',
            'AN': 'Publication Import ID',
            'VL': 'Volume',
            'JO': 'Journal name',
            'JF': 'Journal name',
            'SN': 'ISSN or ISBN',
            'IS': 'Issue',
            'M1': 'Article Number',
            'SP': 'Pages (begin)',
            'EP': 'Pages (end)',
            'BT': 'Host Publication',
            'CY': 'Place of Publication',
        }
        this is the mus data that is used to build the ris file
        mapping_ris_to_mus = {
            "TY",itemtypekey[paper.itemtype],
            "TI",paper.title,
            "AU",[(author.last_name+', '+author.first_name) for author in paper.authors.all().only('last_name','first_name').values()],
            "PY",paper.date,
            "Y1",paper.year,
            'N2',paper.abstract,
            'N1',paper.abstract,
            'KW',[keyword.get('keyword') for keyword in paper.keywords] if paper.keywords else '',
            'UR',[link.landing_page_url for link in paper.locations.all()],
            'U2',paper.doi.replace('https://doi.org/',''),
            'DO',paper.doi.replace('https://doi.org/',''),
            'M3',paper.itemtype,
            'VL',paper.volume,
            'JO',paper.journal.name,
            'JF',paper.journal.name,
            'SN',paper.journal.issn,
            'IS',paper.issue,
            'M1',paper.pages,
            'SP',paper.pages.split('-')[0],
            'EP',paper.pages.split('-')[1],
            #'BT', get host publication name from locations -> is primary -> source -> name or something; or from journal name?
        }'''

        itemtypekey = {
            'journal-article':'JOUR',
            'posted-content':'GEN',
            'dissertation':'THES',
            'monograph':'SER',
            'reference-entry':'GEN',
            'proceedings-article':'CONF',
            'report':'RPRT',
            'book':'BOOK',
            'dataset':'DATA',
            'reference-book':'GEN',
            'journal-issue':'JOUR',
            'peer-review':'GEN',
            'report-series':'SER',
            'proceedings':'CONF',
            'other':'GEN',
            'book-chapter':'CHAP',
        }
        fullrisdata = []
        for paper in self.all().distinct():
            risdata =[
                ["TY",itemtypekey[paper.itemtype]],
                ["T1",paper.title]
            ]

            for author in paper.authors.all():
                risdata.append(['AU',author.last_name+', '+author.first_name])
            risdata.append(["PY",paper.date])
            risdata.append(["Y1",paper.year])
            if paper.abstract:
                risdata.append(["N2",paper.abstract])
                risdata.append(["AB",paper.abstract])

            if paper.keywords != []:
                for keyword in paper.keywords:
                    risdata.append(['KW',keyword.get('keyword')])

            for location in paper.locations.all():
                if location.landing_page_url and location.landing_page_url != '':
                    risdata.append(['UR',location.landing_page_url])
                if location.is_primary:
                    if location.source:
                        if location.source.host_org:
                            publisherloc=location.source.host_org

            risdata.append(["U2",paper.doi.replace('https://doi.org/', '')])
            risdata.append(["DO",paper.doi.replace('https://doi.org/', '')])
            risdata.append(["M3",paper.itemtype])
            if paper.journal:
                risdata.append(["JO",paper.journal.name])
                risdata.append(["JF",paper.journal.name])
                if paper.journal.issn:
                    risdata.append(["SN",paper.journal.issn])
                if paper.volume:
                    risdata.append(["VL",paper.volume])
                if paper.issue:
                    risdata.append(["IS",paper.issue])
                if paper.journal.publisher:
                    publisherjournal=paper.journal.publisher
                if paper.journal.host_org:
                    hostorgjournal=paper.journal.host_org

            if paper.pages:
                if '-' in paper.pages:
                    pages = paper.pages.split('-')
                    if len(pages) == 2:
                        if pages[0] != pages[1]:
                            risdata.append(["SP",pages[0]])
                            risdata.append(["EP",pages[1]])
                        else:
                            risdata.append(["M1",pages[0]])
                    else:
                        risdata.append(["M1",pages[0]])
                else:
                    risdata.append(["M1",paper.pages])

            if publisherjournal:
                risdata.append(["BT",publisherjournal])
            elif hostorgjournal:
                risdata.append(["BT",hostorgjournal])
            elif publisherloc:
                risdata.append(["BT",publisherloc])

            risdata.append(["ER",'\n'])
            fullrisdata.append(risdata)

        content = StringIO()
        with content as f:
            for risentry in fullrisdata:
                for item in risentry:
                    f.write(str(item[0])+'  - '+str(item[1])+'\n')
            return content.getvalue()

    def exportxmldata(self)-> list[dict]:
        '''
        returns a list with dicts containing all the info to export a CERIF xml file
        result is handled by export_paper_data_to_cerif_xml in PureOpenAlex.data_export
        List of fields for xml:
'pubt:Type': {
        '@xmlns:pure': 'https://pure.elsevier.com/schema/extensions/oai_cerif_openaire', # keep this
        '@pure:peerReviewed': 'true' or 'false',depends on itemtype (?)
        '@pure:publicationCategory': '/dk/atira/pure/researchoutput/category/academic', # change this
        '#text': 'http://purl.org/coar/resource_type/c_6501' for journal, see https://vocabularies.coar-repositories.org/resource_types/
    },
    'cerif:Language': 'en', #change if needed
    'cerif:Title': {
        '@xml:lang': 'en',#change if needed
        '#text': paper.title
    },

    'cerif:PublishedIn': {
        'cerif:Publication': {
            '@id': '8e6e6598-5be4-4568-96c7-b881ab45994c', # process all ids from pure to make lookup list for ids like these, and use that data to fill this
            'pubt:Type': 'http://purl.org/coar/resource_type/c_0640',
            'cerif:Title': [
                {
                    '@xml:lang': 'en',
                    '#text': 'Computers & mathematics with applications'
                },
                {
                    '@xml:lang': 'en',
                    '#text': 'Computers and Mathematics with Applications'
                }
            ]
        }
    },
    'cerif:PublicationDate': paper.date, YYYY-MM-DD
    'cerif:Volume': str(paper.volume),
    'cerif:Issue': str(paper.issue),
    'cerif:StartPage': paper.pages.split('-')[0],
    'cerif:EndPage': paper.pages.split('-')[1],
    'cerif:DOI': paper.doi.replace('https://doi.org/', ''),
    'cerif:SCP-Number': for pureentry in paper.pure_entries.all(): if pureentry.scopus: return str(pureentry.scopus).split('scp=')[1].split('&')[0]
    'cerif:ISSN': [  # also look up just like publishedIn
        {
            '@medium': 'http://issn.org/vocabularies/Medium#Print',
            '#text': '0898-1221'
        },
        {
            '@medium': 'http://issn.org/vocabularies/Medium#Online',
            '#text': '1873-7668'
        }
    ],
    'cerif:URL': 'https://research.utwente.nl/en/publications/c99a1b0d-3070-4f77-bf45-a78e294fbeda', #only include if pure_entry exists
    'cerif:Authors': { # same as publishedIn: make list of all authors with this data and look em up
        'cerif:Author': [
            {
                'cerif:Person': {
                    '@id': 'd267d6ad-e0a2-40f9-84e6-3e2df54f3f21',
                    'cerif:PersonName': {
                        'cerif:FamilyNames': 'Anderson',
                        'cerif:FirstNames': 'Thomas G.'
                    }
                },
                'cerif:Affiliation': {
                    'cerif:OrgUnit': {
                        '@id': 'f518c321-5d73-47e8-a6a5-736560731c28',
                        'cerif:Name': {
                            '@xml:lang': 'en',
                            '#text': 'Rice University'
                        }
                    }
                }
            },
            {
                'cerif:Person': {
                    '@id': '9de34bd3-f13d-4a35-9cf3-d4440a890234',
                    'cerif:PersonName': {
                        'cerif:FamilyNames': 'Bonnet',
                        'cerif:FirstNames': 'Marc'
                    }
                },
                'cerif:Affiliation': {
                    'cerif:OrgUnit': {
                        '@id': '6d252b57-6116-4a64-a97f-0f5313600b9b',
                        'cerif:Name': {
                            '@xml:lang': 'en',
                            '#text': 'INRIA Institut National de Recherche en Informatique et en Automatique'
                        }
                    }
                }
            },
            # etc
        ]
    },
    'cerif:Publishers': { #look this up as well? seems a bit weird with the orgunit field
        'cerif:Publisher': {
            'cerif:OrgUnit': {
                'cerif:Name': {
                    '@xml:lang': 'en',
                    '#text': 'Elsevier'
                }
            }
        }
    },
    'cerif:License': { # use paper.license and look up atira scheme
        '@scheme': '/dk/atira/pure/core/document/licenses',
        '#text': 'taverne'
    },
    'cerif:Keyword': { #skip this
        '@xml:lang': 'en',
        '#text': '2024 OA procedure'
    },
    'cerif:Abstract': {
        '@xml:lang': 'en',
        '#text': paper.abstract
    },
    'cerif:Status': { # take a better look at this field
        '@scheme': '/dk/atira/pure/researchoutput/status',
        '#text': 'epub'
    },
    'ar:Access': 'http://purl.org/coar/access_right/c_f1cf', #check this field
    'cerif:FileLocations': { #use paper.locations.all()
        'cerif:Medium': {
            'cerif:Type': {
                '@scheme': '/dk/atira/pure/researchoutput/electronicversion/versiontype',
                '#text': 'publishersversion'
            },
            'cerif:Title': {
                '@xml:lang': 'en',
                '#text': '1-s2.0-S0898122124000907-main.pdf'
            },
            'cerif:URI': 'https://research.utwente.nl/files/359113971/1-s2.0-S0898122124000907-main.pdf',
            'cerif:MimeType': 'application/pdf',
            'cerif:Size': '555738',
            'ar:Access': 'http://purl.org/coar/access_right/c_f1cf',
            'cerif:License': {
                '@scheme': '/dk/atira/pure/core/document/licenses',
                '#text': 'taverne'
            }
        }
    }
}
        '''

        result=[]
        for paper in self.all().distinct():
            # first check type
            if paper.itemtype in ['other','posted-content','reference-entry','monograph','dataset']:
                logger.warning(f'skipping {paper.id} as it is of type {paper.itemtype}')
                continue
            filldict = {}

            paperdict = {'cerif:Publication':filldict}
            result.append(paperdict)

        return result

