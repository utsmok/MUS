from django.db import models, transaction
from django.db.models import Q, Prefetch, Exists, OuterRef, Count
from collections import defaultdict
from loguru import logger
from .constants import TCSGROUPS, TCSGROUPSABBR, EEGROUPS, EEGROUPSABBR, FACULTYNAMES
from datetime import datetime
from django.apps import apps
import re
from django.conf import settings
import pymongo

MONGOURL = getattr(settings, "MONGOURL")
client=pymongo.MongoClient(MONGOURL)
db=client['mus']


class AuthorManager(models.Manager):
    # Deduplicate authors
    # Check if author is UT or not
    # repair/manage affiliations & utdata
    # repair/manage authorships
    # repair/manage avatars (now in utdata)

    # TODO more data_repair.fixavatars and data_repair.fixMissingAffils here

    ...
class AuthorQuerySet(models.QuerySet):
    # simplify getting names/name combinations
    # filter by group/faculty/affil/authorship data/etc
    def get_affiliations(self, author_id):
        author = self.filter(id=author_id).prefetch_related('affiliations').first()
        return author.affiliations.all().prefetch_related('organization').all().order_by('-years__-1')


class PureEntryManager(models.Manager):
    # TODO: move data_repair.matchPurePilotWithPureEntry and data_repair.addPureEntryAuthors here

    def link_papers(self, advanced = True):
        """
        For every PureEntry, try to find a matching paper in the database and mark them as such.
        """

        def update(paperlist,entrylist):
            Paper = apps.get_model('PureOpenAlex', 'Paper')
            PureEntry = apps.get_model('PureOpenAlex', 'PureEntry')
            with transaction.atomic():
                Paper.objects.bulk_update(paperlist, fields=["has_pure_oai_match"])
                PureEntry.objects.bulk_update(entrylist, fields=["paper"])
            logger.info(str(len(paperlist)), "papers linked, total amount of new linked papers: ", str(len(paperlist)))

        paperlist = []
        entrylist = []
        i=0
        checkedentries=0
        Paper = apps.get_model('PureOpenAlex', 'Paper')

        allentries = self.filter(Q(paper__isnull=True)).only("doi","title",'researchutwente', 'risutwente', 'other_links', 'duplicate_ids')
        paperpreload = Paper.objects.all().only("doi","title",'locations','id').prefetch_related('locations')
        logger.info('Trying to find matches for ' + str(allentries.count()) + ' PureEntries in ' + str(paperpreload.count()) + 'unmatched papers')
        for entry in allentries:
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
            if paper:
                with transaction.atomic():
                    entry.paper = paper
                    paper.has_pure_oai_match = True
                paperlist.append(paper)
                entrylist.append(entry)
                if not found:
                    logger.debug("found initial paper for entry %s", entry.id)
                else:
                    logger.debug("found new paper for entry %s", entry.id)
            else:
                logger.debug("no paper found for entry %s", entry.id) #no match or no new match


        update(paperlist, entrylist)
        logger.info(f"Linked {len(paperlist)} papers with {len(entrylist)} PureEntries after checking {checkedentries} PureEntries")


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
            logger.error(f'no data received, returning None')
            return None, None
        if self.filter(openalex_url=data.get('id')).exists():
            logger.info(f'journal {data.get("id")} already exists in mus db, updating & returning it')
            journal = self.objects.filter(openalex_url=data.get('id')).first()
            host_org = data.get('host_organization_lineage_names','')
            if isinstance(host_org, list) and len(host_org) > 0:
                host_org = host_org[0]
            if host_org != '' and journal.host_org != host_org:
                journal.host_org = host_org
                journal.save()
            if not journal.dealdata:
                dealdata, keywords, publisher = get_deal_data(journal.openalex_url)
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

        dealdata, keywords, publisher = get_deal_data(journaldata['openalex_url'])
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
                            journal, created = Journal.objects.get_or_make_from_api_data(item, data.get('primary_location'))
                if not journal:
                    for loc in data.get('locations'):
                        if loc.get('source'):
                            if loc.get('source').get('type') == 'journal':
                                journal, created = Journal.objects.get_or_make_from_api_data(item, loc)
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
        return self.select_related('journal').prefetch_related(location_prefetch, authors_prefetch)
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
            logger.debug("[filter] {} [value] {}", filter, value)
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
                author = Author.objects.get(name = value)
                finalfilters['authors'].append(Q(
                    authorships__author=author
                ))
            if filter == 'group':
                group = value
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
                itemtype = value
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
                faculty=value
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