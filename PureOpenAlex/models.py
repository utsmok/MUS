from django.db import models
from django_extensions.db.models import TimeStampedModel
from .managers import PaperQuerySet, PaperManager, JournalManager, PureEntryManager, AuthorManager, AuthorQuerySet

class Organization(models.Model):
    name = models.CharField(max_length=256)
    country_code = models.CharField(max_length=256)
    ror = models.CharField(max_length=256, blank=True, null=False)
    type = models.CharField(max_length=256, blank=True, null=False)
    data_source = models.CharField(max_length=256, blank=True, null=True)
    openalex_url = models.CharField(max_length=256, blank=True, null=True)

    class Meta:
        ordering = ['country_code', 'name']
        indexes = [
            models.Index(fields=["openalex_url",
                                "name",
                                'country_code',
                                'ror',
                                'type',
                                ]),
        ]

class Author(TimeStampedModel, models.Model):
    name = models.CharField(max_length=256, null=True)
    first_name = models.CharField(max_length=256, blank=True, null=True)
    last_name = models.CharField(max_length=256, blank=True, null=True)
    middle_name = models.CharField(max_length=256, blank=True, null=True)
    initials = models.CharField(max_length=256, blank=True, null=True)
    affils = models.ManyToManyField(
        Organization,through="Affiliation", related_name="authors", blank=True, db_index=True
    )
    orcid = models.CharField(max_length=256, blank=True, null=True)
    is_ut = models.BooleanField()
    openalex_url = models.CharField(max_length=256, blank=True, null=True)
    known_as = models.JSONField(blank=True, null=True)
    scopus_id = models.CharField(max_length=256, unique=True, blank=True, null=True)
    objects = AuthorManager().from_queryset(AuthorQuerySet)()
    class Meta:
        ordering = ['-is_ut', 'last_name']
        indexes = [
            models.Index(fields=["openalex_url",
                                "name",
                                'is_ut',
                                'scopus_id',
                                'orcid',
                                'known_as',
                                ]),
        ]
class Affiliation(models.Model):
    years = models.JSONField(default=dict)
    author = models.ForeignKey(Author, on_delete=models.CASCADE, related_name="affiliations")
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="affiliations")
    class Meta:
        indexes = [
            models.Index(fields=[
                "author",
                'organization',
            ]),
        ]
class UTData(models.Model):
    avatar = models.ImageField(
        upload_to="author_avatars/", blank=True, null=True
    )
    avatar_path = models.CharField(max_length=256, blank=True, null=True)
    current_position = models.CharField(max_length=256)
    current_group = models.CharField(max_length=256, blank=True, null=True)
    current_faculty = models.CharField(max_length=256, blank=True, null=True)
    employment_data = models.JSONField(null=True)
    employee = models.OneToOneField(
        Author, on_delete=models.CASCADE, null=True
    )
    email = models.EmailField(max_length=256)
    pure_uuid = models.UUIDField(unique=True, default=None, null=True)

    class Meta:
        indexes = [
            models.Index(fields=[
                "employee",
                'current_position',
                'current_group',
                'current_faculty',
            ])

        ]
class DealData(TimeStampedModel, models.Model):
    deal_status = models.CharField(max_length=256)
    publisher = models.CharField(max_length=512)
    jb_url = models.CharField(max_length=512)
    oa_type = models.CharField(max_length=256)
    class Meta:
        indexes = [
            models.Index(fields=["deal_status",
                                'publisher',
                                'oa_type',
                                'jb_url',
                                ]),
        ]
class Journal(models.Model):
    name = models.CharField(max_length=512)
    e_issn = models.CharField(max_length=256, blank=True, null=True)
    issn = models.CharField(max_length=256, blank=True, null=True)
    host_org = models.CharField(max_length=5120, blank=True, null=False)
    is_in_doaj = models.BooleanField(null=True)
    is_oa = models.BooleanField(null=True)
    type = models.CharField(max_length=256, blank=True, null=False)
    keywords = models.JSONField(blank=True, null=True)
    publisher = models.CharField(max_length=512, blank=True, null=False)
    openalex_url = models.CharField(max_length=256, blank=True, null=False)
    dealdata = models.ForeignKey(DealData, on_delete=models.SET_NULL, blank=True, null=True)
    objects = JournalManager()
    class Meta:
        indexes = [
            models.Index(fields=["openalex_url",
                                'name',
                                'issn',
                                'e_issn',
                                'publisher',
                                ]),
        ]
class Source(TimeStampedModel, models.Model):
    openalex_url = models.CharField(max_length=256)
    homepage_url = models.CharField(max_length=512, blank=True)
    display_name = models.CharField(max_length=512)
    e_issn = models.CharField(max_length=256, blank=True, null=True)
    issn = models.CharField(max_length=256, blank=True, null=True)
    host_org = models.CharField(max_length=512)
    type = models.CharField(max_length=256)
    is_in_doaj = models.BooleanField(null=True)
    class Meta:
        indexes = [
            models.Index(fields=["openalex_url",
                                'homepage_url',
                                'display_name',
                                'issn',
                                'e_issn',
                                'host_org',
                                ]),
        ]
class Location(TimeStampedModel, models.Model):
    is_accepted = models.BooleanField(null=True)
    is_oa = models.BooleanField(null=True)
    is_published = models.BooleanField(null=True)
    license = models.CharField(max_length=256, blank=True, null=False)
    landing_page_url = models.CharField(max_length=512, blank=True, null=False)
    source = models.ForeignKey(Source, on_delete=models.SET_NULL, blank=True, null=True)
    is_primary = models.BooleanField()
    is_best_oa = models.BooleanField()
    pdf_url = models.CharField(max_length=512, blank=True, null=False)
    class Meta:
        indexes = [
            models.Index(fields=["source",
                                'is_oa',
                                'landing_page_url',
                                'pdf_url',
                                ])
        ]
class Paper(TimeStampedModel, models.Model):
    openalex_url = models.CharField(max_length=256)
    title = models.CharField(max_length=1024)
    doi = models.CharField(max_length=256)
    year = models.CharField(max_length=256)
    citations = models.IntegerField(blank=True, null=True)
    primary_link = models.CharField(max_length=1024)
    itemtype = models.CharField(max_length=256)
    date = models.DateField()
    openaccess = models.CharField(max_length=256, blank=True, null=False)
    language = models.CharField(max_length=256, blank=True, null=False)
    abstract = models.TextField()
    pages = models.CharField(max_length=256, blank=True, null=False)
    pagescount = models.IntegerField(blank=True, null=True)
    volume = models.CharField(max_length=256, blank=True, null=False)
    issue = models.CharField(max_length=256, blank=True, null=False)
    is_oa = models.BooleanField(null=True)
    license = models.CharField(max_length=256, blank=True, null=False)
    pdf_link_primary = models.CharField(max_length=1024, blank=True, null=False)
    keywords = models.JSONField(blank=True, null=True)
    journal = models.ForeignKey(
        Journal, on_delete=models.SET_NULL, related_name="papers", blank=True, null=True
    )
    authors = models.ManyToManyField(
        Author, through="Authorship", related_name="papers", db_index=True
    )
    locations = models.ManyToManyField(Location, related_name="papers", db_index=True)
    apc_listed_value = models.IntegerField(blank=True, null=True)
    apc_listed_currency = models.CharField(max_length=256, blank=True, null=False)
    apc_listed_value_usd = models.IntegerField(blank=True, null=True)
    apc_listed_value_eur = models.IntegerField(blank=True, null=True)
    apc_paid_value = models.IntegerField(blank=True, null=True)
    apc_paid_currency = models.CharField(max_length=256, blank=True, null=False)
    apc_paid_value_usd = models.IntegerField(blank=True, null=True)
    apc_paid_value_eur = models.IntegerField(blank=True, null=True)
    is_in_pure = models.BooleanField(null=True)
    has_pure_oai_match = models.BooleanField(null=True)
    has_any_ut_author_year_match = models.BooleanField(null=True)
    published_print = models.DateField(blank=True, null=True)
    published_online = models.DateField(blank=True, null=True)
    published = models.DateField(blank=True, null=True)
    issued = models.DateField(blank=True, null=True)
    ut_keyword_suggestion = models.CharField(max_length=256, blank=True, null=True)
    topics = models.JSONField(blank=True, null=True)
    taverne_date = models.DateField(blank=True, null=True)
    calc_taverne_date = models.DateField(blank=True, null=True)

    objects = PaperManager().from_queryset(PaperQuerySet)()

    def get_oa_links(self):
        urls = []
        bestoa = {'landing_page_url': '', 'pdf_url': ''}
        for loc in self.locations.all():
            if loc.is_best_oa:
                bestoa['landing_page_url'] = loc.landing_page_url
                bestoa['pdf_url'] = loc.pdf_url
            elif loc.is_oa:
                if loc.landing_page_url:
                    if loc.landing_page_url not in urls:
                        urls.append(loc.landing_page_url)
                if loc.pdf_url:
                    if loc.pdf_url not in urls:
                        urls.append(loc.pdf_url)
        else:
            return bestoa, urls

    class Meta:
        ordering = ['-year', 'doi']
        indexes = [
            models.Index(fields=["openalex_url",
                                "doi",
                                "title",
                                'year',
                                "itemtype",
                                'is_oa',
                                'is_in_pure',
                                'has_pure_oai_match',
                                'openaccess',
                                'date'
                                ]),
        ]


class Authorship(models.Model):
    author = models.ForeignKey(
        Author, on_delete=models.CASCADE, related_name="authorships"
    )
    paper = models.ForeignKey(
        Paper, on_delete=models.CASCADE, related_name="authorships"
    )
    position = models.CharField(max_length=256, blank=True, null=False)
    corresponding = models.BooleanField(null=True)
    ut_author_year_match = models.BooleanField(null=True)
    class Meta:
        indexes = [
            models.Index(fields=["author",
                                "paper",
                                ]),
        ]

class viewPaper(TimeStampedModel, models.Model):
    from django.conf import settings
    displayed_paper = models.ForeignKey(
        Paper, on_delete=models.CASCADE, related_name="view_paper"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="view_paper",
        null=True,
    )
    class Meta:
        ordering = ['-user']

class MUSPDF(TimeStampedModel, models.Model):
    paper = models.ForeignKey(
        Paper, on_delete=models.DO_NOTHING, related_name="pdfs"
    )
    location = models.ForeignKey(
        Location, on_delete=models.DO_NOTHING, related_name="pdfs"
    )
    doi = models.CharField(max_length=256, blank=True, null=False)
    openalex_url = models.CharField(max_length=256, blank=True, null=False)
    url = models.CharField(max_length=256, blank=True, null=False)
    is_oa = models.BooleanField(null=True)
    from_pure = models.BooleanField(null=True)
    year = models.CharField(max_length=256, blank=True, null=False)
    filename = models.CharField(max_length=256, blank=True, null=False)

    class Meta:
        indexes = [
            models.Index(fields=["paper",
                                "location",
                                ]),
        ]

class PilotPureData(models.Model):
    pureid = models.IntegerField()
    title = models.CharField(max_length=1024)
    all_authors = models.JSONField()
    orgs = models.JSONField()
    doi = models.CharField(max_length=512)
    other_links = models.URLField(max_length=512, null=True)
    apc_paid_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True)
    file_names = models.JSONField()
    article_number = models.CharField(max_length=256, blank=True)
    item_type = models.CharField(max_length=256)
    year = models.IntegerField()
    open_access = models.CharField(max_length=256, blank=True)
    keywords = models.JSONField()
    ut_keyword = models.CharField(max_length=512, blank=True)
    import_source = models.CharField(max_length=256, blank=True)
    journal_title = models.CharField(max_length=512, blank=True)
    issn = models.CharField(max_length=256)
    is_doaj = models.BooleanField()
    publisher_journal = models.CharField(max_length=512, blank=True)
    ut_authors = models.JSONField()
    date_earliest_published = models.DateField(null=True)
    date_published = models.DateField(null=True)
    date_eprint_first_online = models.DateField(null=True)
    pure_entry_created = models.DateField()
    pure_entry_last_modified = models.DateField()
    pagescount = models.IntegerField(null=True)
    pages = models.CharField(max_length=256, blank=True)
    event = models.CharField(max_length=512, blank=True)
    publisher_other = models.CharField(max_length=512, blank=True)
    class Meta:
        ordering = ['-year', 'pureid']
        indexes = [
            models.Index(fields=[
                "pureid",
                'title',
                'doi',
                'year',
            ])
        ]

class PureEntry(TimeStampedModel, models.Model):
    title = models.CharField(max_length=1024, blank=True, null=False)
    paper = models.ForeignKey(
        Paper, on_delete=models.SET_NULL, related_name="pure_entries", blank=True, null=True
    )
    authors = models.ManyToManyField(Author, related_name="pure_entries")
    language = models.CharField(max_length=256, blank=True, null=False)
    date = models.CharField(max_length=256, blank=True, null=False)
    year = models.CharField(max_length=256, blank=True, null=False)
    rights = models.CharField(max_length=512, blank=True, null=False)
    format = models.CharField(max_length=256, blank=True, null=False)
    itemtype = models.CharField(max_length=256, blank=True, null=False)
    abstract = models.TextField(blank=True, null=False)
    source = models.TextField(blank=True, null=False)
    publisher = models.CharField(max_length=512, blank=True, null=False)
    ut_keyword = models.CharField(max_length=256, blank=True, null=True)
    doi = models.CharField(max_length=256, blank=True, null=True)
    isbn = models.CharField(max_length=256, blank=True, null=True)
    researchutwente = models.CharField(max_length=256, blank=True, null=True)
    risutwente = models.CharField(max_length=256, blank=True, null=True)
    scopus = models.CharField(max_length=256, blank=True, null=True)
    other_links = models.JSONField(blank=True, null=True)
    duplicate_ids = models.JSONField(blank=True, null=True)
    journal = models.ForeignKey(
        Journal, on_delete=models.DO_NOTHING, related_name="pure_entries", blank=True, null=True
    )
    keywords = models.JSONField(blank=True, null=True)
    pilot_pure_data = models.ForeignKey(PilotPureData, on_delete=models.DO_NOTHING, related_name="pure_entries", blank=True, null=True)
    checked_for_match = models.BooleanField(default=False)
    objects = PureEntryManager()
    class Meta:
        ordering = ['-year', 'doi']
        indexes = [
            models.Index(fields=["title",
                                'doi',
                                'isbn',
                                'researchutwente',
                                'risutwente',
                                'scopus',
                                'publisher',
                                'date',
                                'paper',
                                'journal',
                                ]),
        ]


class Dataset(TimeStampedModel, models.Model):
    doi = models.CharField(max_length=256, blank=True, null=True)
    title = models.CharField(max_length=1024, blank=True, null=False)
    authors = models.ManyToManyField(Author, related_name="datasets")
    related_papers = models.ManyToManyField(Paper, related_name="datasets")
    publisher = models.CharField(max_length=256, blank=True, null=True)
    url = models.CharField(max_length=256, blank=True, null=True)
    itemtype = models.CharField(max_length=256, blank=True, null=False)
    detailed_itemtype = models.JSONField(blank=True, null=True)
    related_ids = models.JSONField(blank=True, null=True)
    license_info = models.JSONField(blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    source = models.CharField(max_length=256, blank=True, null=True)
    created_source_date = models.DateField(blank=True, null=True)
    last_modified_source_date = models.DateField(blank=True, null=True)

    class Meta:
        ordering = ['-created']
        indexes = [
            models.Index(fields=["doi",
                                'title',
                                'itemtype',
                                'source',
                                ]),
        ]


class DBUpdate(TimeStampedModel, models.Model):
    details = models.JSONField() #     result = {'unique_id (e.g. list of dois or openalex_urls)':[], 'total (count)':0}
    update_source = models.CharField(max_length=256, blank=True, null=False) #e.g. openaire, openalex, etc
    update_type = models.CharField(max_length=256, blank=True, null=False) #manual, automatic, scheduled, ...

    class Meta:
        ordering = ['-created']
        indexes = [
            models.Index(fields=["update_source",
                                'update_type',
                                ]),
        ]