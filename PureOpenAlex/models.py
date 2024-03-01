from django.db import models
from django_extensions.db.models import TimeStampedModel

class Organization(models.Model):
    name = models.CharField(max_length=256)
    country_code = models.CharField(max_length=256)
    ror = models.CharField(max_length=256, blank=True, null=False)
    type = models.CharField(max_length=256, blank=True, null=False)
    data_source = models.CharField(max_length=256, blank=True, null=True)
    openalex_url = models.CharField(max_length=256, blank=True, null=True)

    class Meta:
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
    class Meta:
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

class UTData(models.Model):
    avatar = models.ImageField(
        upload_to="author_avatars/", blank=True, null=True
    )
    current_position = models.CharField(max_length=256)
    current_group = models.CharField(max_length=256, blank=True, null=True)
    current_faculty = models.CharField(max_length=256, blank=True, null=True)
    employment_data = models.JSONField(null=True)
    employee = models.OneToOneField(
        Author, on_delete=models.CASCADE, null=True
    )
    email = models.EmailField(max_length=256)

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
    dealdata = models.ForeignKey(DealData, on_delete=models.SET_NULL, null=True)
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
                                ]),
        ]

class Location(TimeStampedModel, models.Model):
    is_accepted = models.BooleanField(null=True)
    is_oa = models.BooleanField(null=True)
    is_published = models.BooleanField(null=True)
    license = models.CharField(max_length=256, blank=True, null=False)
    landing_page_url = models.CharField(max_length=512, blank=True, null=False)
    source = models.ForeignKey(Source, on_delete=models.SET_NULL, null=True)
    is_primary = models.BooleanField()
    is_best_oa = models.BooleanField()
    pdf_url = models.CharField(max_length=512, blank=True, null=False)

class Paper(TimeStampedModel, models.Model):
    openalex_url = models.CharField(max_length=256)
    title = models.CharField(max_length=512)
    doi = models.CharField(max_length=256)
    year = models.CharField(max_length=256)
    citations = models.IntegerField(blank=True, null=True)
    primary_link = models.CharField(max_length=512)
    itemtype = models.CharField(max_length=256)
    date = models.CharField(max_length=256)
    openaccess = models.CharField(max_length=256, blank=True, null=False)
    language = models.CharField(max_length=256, blank=True, null=False)
    abstract = models.TextField()
    pages = models.CharField(max_length=256, blank=True, null=False)
    pagescount = models.IntegerField(blank=True, null=True)
    volume = models.CharField(max_length=256, blank=True, null=False)
    issue = models.CharField(max_length=256, blank=True, null=False)
    is_oa = models.BooleanField(null=True)
    license = models.CharField(max_length=256, blank=True, null=False)
    pdf_link_primary = models.CharField(max_length=512, blank=True, null=False)
    keywords = models.JSONField(blank=True, null=True)
    journal = models.ForeignKey(
        Journal, on_delete=models.SET_NULL, related_name="papers", null=True
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
    published_print = models.DateField(blank=True, null=True)
    published_online = models.DateField(blank=True, null=True)
    published = models.DateField(blank=True, null=True)
    issued = models.DateField(blank=True, null=True)
    taverne_date = models.DateField(blank=True, null=True)
    ut_keyword_suggestion = models.CharField(max_length=256, blank=True, null=True)
    topics = models.JSONField(blank=True, null=True)
    class Meta:
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


class PureEntry(TimeStampedModel, models.Model):
    title = models.CharField(max_length=512, blank=True, null=False)
    paper = models.ForeignKey(
        Paper, on_delete=models.SET_NULL, related_name="pure_entries", null=True
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
        Journal, on_delete=models.DO_NOTHING, related_name="pure_entries", null=True
    )
    keywords = models.JSONField(blank=True, null=True)
