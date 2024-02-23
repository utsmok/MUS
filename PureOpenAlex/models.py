from django.db import models
from django_extensions.db.models import TimeStampedModel



class Keyword(models.Model):
    keyword = models.CharField(max_length=256)
    score = models.FloatField(null=True)
    data_source = models.CharField(max_length=256, blank=True, null=True)
    indexes = [
        models.Index(fields=["keyword"]),
    ]

class JournalKeyword(models.Model):
    keyword = models.CharField(max_length=256)

class Organization(models.Model):
    name = models.CharField(max_length=256)
    country_code = models.CharField(max_length=256)
    ror = models.CharField(max_length=256, blank=True, null=False)
    type = models.CharField(max_length=256, blank=True, null=False)
    data_source = models.CharField(max_length=256, blank=True, null=True)
    openalex_url = models.CharField(max_length=256, blank=True, null=True)
    
    class Meta:
        indexes = [
            models.Index(fields=["name"]),
            models.Index(fields=["ror"]),
            models.Index(fields=["openalex_url"]),
        ]

class AFASData(TimeStampedModel, models.Model):
    employee_id = models.CharField(max_length=256, blank=True, null=True)
    isni = models.CharField(max_length=256, blank=True, null=True)
    scopus_id = models.CharField(max_length=256, blank=True, null=True)
    digital_author_id = models.CharField(max_length=256, blank=True, null=True)
    orcid = models.CharField(max_length=256, blank=True, null=True)
    name = models.CharField(max_length=256, blank=True, null=True)
    first_name = models.CharField(max_length=256, blank=True, null=True)
    last_name = models.CharField(max_length=256, blank=True, null=True)
    pub_name = models.CharField(max_length=256, blank=True, null=True)
    known_as = models.CharField(max_length=256, blank=True, null=True)
    former_name = models.CharField(max_length=256, blank=True, null=True)
    is_tcs = models.BooleanField(null=True)
    current_org_unit = models.CharField(max_length=256, blank=True, null=True)
    start_year = models.IntegerField(null=True)
    end_year = models.IntegerField(null=True)
    jobs = models.JSONField(blank=True, null=True)
    is_mesa = models.BooleanField(null=True)
    is_dsi = models.BooleanField(null=True)
    is_techmed = models.BooleanField(null=True)

    class Meta:
        indexes = [
            models.Index(fields=["orcid"]),
            models.Index(fields=["is_tcs"]),
            models.Index(fields=["scopus_id"]),
            models.Index(fields=["name"]),
            models.Index(fields=["pub_name"]),
            models.Index(fields=["current_org_unit"]),
            models.Index(fields=["known_as"]),
            models.Index(fields=["start_year"]),
            models.Index(fields=["end_year"]),
            models.Index(fields=["is_mesa"]),
            models.Index(fields=["is_dsi"]),
            models.Index(fields=["is_techmed"]),
        ]


class Author(TimeStampedModel, models.Model):
    name = models.CharField(max_length=256, null=True)
    first_name = models.CharField(max_length=256, blank=True, null=True)
    last_name = models.CharField(max_length=256, blank=True, null=True)
    middle_name = models.CharField(max_length=256, blank=True, null=True)
    initials = models.CharField(max_length=256, blank=True, null=True)
    affiliations = models.ManyToManyField(
        Organization, related_name="authors", db_index=True
    )
    orcid = models.CharField(max_length=256, blank=True, null=True)
    is_ut = models.BooleanField()
    afas_data = models.OneToOneField(
        "AFASData", on_delete=models.SET_NULL, null=True
    )
    openalex_url = models.CharField(max_length=256, blank=True, null=True)
    known_as = models.JSONField(blank=True, null=True)
    scopus_id = models.CharField(max_length=256, unique=True, blank=True, null=True)

    class Meta:
        indexes = [
            models.Index(fields=["name"]),
            models.Index(fields=["is_ut"]),
            models.Index(fields=["orcid"]),
            models.Index(fields=["afas_data"]),
            models.Index(fields=["openalex_url"]),
        ]

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

    class Meta:
        indexes = [
            models.Index(fields=["employee"]),
            models.Index(fields=["avatar"]),
            models.Index(fields=["current_group"]),
            models.Index(fields=["current_faculty"]),
            models.Index(fields=["current_position"]),
        ]


class Journal(models.Model):
    name = models.CharField(max_length=5120)
    e_issn = models.CharField(max_length=256, blank=True, null=True)
    issn = models.CharField(max_length=256, blank=True, null=True)
    host_org = models.CharField(max_length=5120, blank=True, null=False)
    doaj = models.BooleanField(null=True)
    is_oa = models.BooleanField(null=True)
    type = models.CharField(max_length=256, blank=True, null=False)
    keywords = models.ManyToManyField(JournalKeyword)
    publisher = models.CharField(max_length=5120, blank=True, null=False)

    class Meta:
        indexes = [
            models.Index(fields=["name"]),
            models.Index(fields=["doaj"]),
            models.Index(fields=["is_oa"]),
            models.Index(fields=["publisher"]),
        ]


class DealData(TimeStampedModel, models.Model):
    deal_status = models.CharField(max_length=256)
    publisher = models.CharField(max_length=5120)
    jb_url = models.CharField(max_length=5120)
    oa_type = models.CharField(max_length=256)
    journal = models.ManyToManyField(Journal) #flip to fk in journal

    class Meta:
        indexes = [
            models.Index(fields=["publisher"]),
            models.Index(fields=["deal_status"]),
            models.Index(fields=["oa_type"]),
        ]


class Source(TimeStampedModel, models.Model):
    openalex_url = models.CharField(max_length=256)
    homepage_url = models.CharField(max_length=5120, blank=True)
    display_name = models.CharField(max_length=5120)
    e_issn = models.CharField(max_length=256, blank=True, null=True)
    issn = models.CharField(max_length=256, blank=True, null=True)
    host_org = models.CharField(max_length=5120)
    type = models.CharField(max_length=256)
    is_in_doaj = models.BooleanField(null=True)

    class Meta:
        indexes = [
            models.Index(fields=["display_name"]),
            models.Index(fields=["host_org"]),
            models.Index(fields=["type"]),
            models.Index(fields=["is_in_doaj"]),
            models.Index(fields=["issn"]),
            models.Index(fields=["e_issn"]),
            models.Index(fields=["openalex_url"]),

        ]


class Location(TimeStampedModel, models.Model):
    is_accepted = models.BooleanField(null=True)
    is_oa = models.BooleanField(null=True)
    is_published = models.BooleanField(null=True)
    license = models.CharField(max_length=256, blank=True, null=False)
    landing_page_url = models.CharField(max_length=5120, blank=True, null=False)
    source = models.ForeignKey(Source, on_delete=models.SET_NULL, null=True)
    is_primary = models.BooleanField()
    is_best_oa = models.BooleanField()
    pdf_url = models.CharField(max_length=5120, blank=True, null=False)
    
    class Meta:
        indexes = [
            models.Index(fields=["source"]),
            models.Index(fields=["is_primary"]),
            models.Index(fields=["is_best_oa"]),
            models.Index(fields=["is_oa"]),
        ]


class Paper(TimeStampedModel, models.Model):
    openalex_url = models.CharField(max_length=256)
    title = models.CharField(max_length=5120)
    doi = models.CharField(max_length=256)
    year = models.CharField(max_length=256)
    citations = models.IntegerField(blank=True, null=True)
    primary_link = models.CharField(max_length=5120)
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
    pdf_link_primary = models.CharField(max_length=5120, blank=True, null=False)
    keywords = models.ManyToManyField(Keyword, related_name="papers", db_index=True)
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

    class Meta:
        indexes = [
            models.Index(fields=["doi"]),
            models.Index(fields=["title"]),
            models.Index(fields=["is_in_pure"]),
            models.Index(fields=["has_pure_oai_match"]),
            models.Index(fields=["year"]),
            models.Index(fields=["is_oa"]),
            models.Index(fields=["openaccess"]),
            models.Index(fields=["taverne_date"]),
            models.Index(fields=["itemtype"]),
            models.Index(fields=["license"]),
            models.Index(fields=["ut_keyword_suggestion"]),
            models.Index(fields=["id"]),
            models.Index(fields=["openalex_url"]),

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
    # TODO these fields need to be filled by using crossref data for this article -- trying to get the displayed name and affiliation
    author_article_name = models.CharField(max_length=256, blank=True, null=True)
    author_article_affiliation = models.CharField(max_length=256, blank=True, null=True)

    class Meta:
        indexes = [
            models.Index(fields=["author"]),
            models.Index(fields=["paper"]),
            models.Index(fields=["corresponding"]),
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
        indexes = [
            models.Index(fields=["displayed_paper"]),
            models.Index(fields=["user"]),
        ]

class PureAuthor(TimeStampedModel, models.Model):
    name = models.CharField(max_length=256)
    author = models.ForeignKey(
        Author, on_delete=models.SET_NULL, related_name="pure_authors", null=True
    )
    class Meta:
        indexes = [
            models.Index(fields=["name"]),
            models.Index(fields=["author"]),
        ]

class PureEntry(TimeStampedModel, models.Model):
    title = models.CharField(max_length=5120, blank=True, null=False)
    paper = models.ForeignKey(
        Paper, on_delete=models.SET_NULL, related_name="pure_entries", null=True
    )
    contributors = models.ManyToManyField(PureAuthor, related_name="pure_entries")
    creators = models.ManyToManyField(PureAuthor, related_name="pure_creators")
    authors = models.ManyToManyField(Author, related_name="pure_entries")
    language = models.CharField(max_length=256, blank=True, null=False)
    date = models.CharField(max_length=256, blank=True, null=False)
    year = models.CharField(max_length=256, blank=True, null=False)
    rights = models.CharField(max_length=5120, blank=True, null=False)
    format = models.CharField(max_length=256, blank=True, null=False)
    itemtype = models.CharField(max_length=256, blank=True, null=False)
    abstract = models.TextField(blank=True, null=False)
    source = models.TextField(blank=True, null=False)
    publisher = models.CharField(max_length=5120, blank=True, null=False)
    ut_keyword = models.CharField(max_length=256, blank=True, null=True)
    doi = models.CharField(max_length=256, blank=True, null=True)
    isbn = models.CharField(max_length=256, blank=True, null=True)
    researchutwente = models.CharField(max_length=256, blank=True, null=True)
    risutwente = models.CharField(max_length=256, blank=True, null=True)
    scopus = models.CharField(max_length=256, blank=True, null=True)
    other_links = models.JSONField(blank=True, null=True)
    duplicate_ids = models.JSONField(blank=True, null=True)
    class Meta:
        indexes = [
            models.Index(fields=["title"]),
            models.Index(fields=["paper"]),
            models.Index(fields=["year"]),
            models.Index(fields=["ut_keyword"]),
            models.Index(fields=["itemtype"]),
        ]


