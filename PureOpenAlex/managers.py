from django.db import models
from django.db.models import Q, Prefetch, Exists, OuterRef, Count
from collections import defaultdict
from loguru import logger
from .constants import TCSGROUPS, TCSGROUPSABBR, EEGROUPS, EEGROUPSABBR, FACULTYNAMES
from datetime import datetime
from django.apps import apps

import re

class PaperQuerySet(models.QuerySet):
    TABLEDEFERFIELDS = ['abstract','keywords','pure_entries',
            'apc_listed_value', 'apc_listed_currency', 'apc_listed_value_eur', 'apc_listed_value_usd',
            'apc_paid_value', 'apc_paid_currency', 'apc_paid_value_eur', 'apc_paid_value_usd',
            'published_print', 'published_online', 'issued', 'published',
            'license', 'citations','pages','pagescount', 'volume','issue']
    
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
        if not user:
            return self
        viewPaper = apps.get_model('PureOpenAlex', 'viewPaper')

        return self.annotate(marked=Exists(viewPaper.objects.filter(displayed_paper=OuterRef("pk"))))
    def filter_by(self, filter: list):
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
    def get_table_data(self, filter: list, user, order='-year'):
        return self.filter_by(filter).annotate_marked(user).get_table_prefetches().defer(*self.TABLEDEFERFIELDS).order_by(order)
    def get_single_paper_data(self, paperid, user):
        return self.filter(id=paperid).annotate_marked(user).select_related().get_detailed_prefetches()
    def get_marked_papers(self, user):
        return self.filter(view_paper__user=user).order_by("-modified")
    def get_author_papers(self, name):
        return self.filter(authors__name=name).distinct().order_by("-year")
    def get_stats(self):
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