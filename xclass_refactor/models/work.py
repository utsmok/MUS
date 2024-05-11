from django.db import models
from django_extensions.db.models import TimeStampedModel
from xclass_refactor.models.models import Grant

class MUSTypes(models.TextChoices):
    ...


class PureTypes(models.TextChoices):
    ...
    
class OpenAlexTypes(models.TextChoices):
    ARTICLE = 'article'
    BOOK_CHAPTER = 'book-chapter'
    DISSERTATION = 'dissertation'
    PREPRINT = 'preprint'
    DATASET = 'dataset'
    BOOK = 'book'
    PARATEXT = 'paratext'
    OTHER = 'other'
    REFERENCE_ENTRY = 'reference-entry'
    REVIEW = 'review'
    REPORT = 'report'
    PEER_REVIEW = 'peer-review'
    STANDARD = 'standard'
    EDITORIAL = 'editorial'
    ERRATUM = 'erratum'
    GRANT = 'grant'
    LETTER = 'letter'
    SUPPLEMENTARY_MATERIALS = 'supplementary-materials'

class CrossrefTypes(models.TextChoices):
    BOOK = 'book'
    BOOK_SECTION = 'book-section'
    BOOK_SERIES = 'book-series'
    EDITED_BOOK = 'edited-book'
    BOOK_TRACK = 'book-track'
    BOOK_PART = 'book-part'
    BOOK_SET = 'book-set'
    BOOK_CHAPTER = 'book-chapter'
    REFERENCE_BOOK = 'reference-book'
    PROCEEDINGS = 'proceedings'
    PROCEEDINGS_SERIES = 'proceedings-series'
    PROCEEDINGS_ARTICLE = 'proceedings-article'
    JOURNAL = 'journal'
    JOURNAL_ISSUE = 'journal-issue'
    JOURNAL_ARTICLE = 'journal-article'
    REPORT = 'report'
    REPORT_SERIES = 'report-series'
    REPORT_COMPONENT = 'report-component'
    DATABASE = 'database'
    DATASET = 'dataset'
    GRANT = 'grant'
    DISSERTATION = 'dissertation'
    MONOGRAPH = 'monograph'
    REFERENCE_ENTRY = 'reference-entry'
    POSTED_CONTENT = 'posted-content'
    STANDARD = 'standard'
    COMPONENT = 'component'
    PEER_REVIEW = 'peer-review'
    OTHER = 'other'

class OAStatus(models.TextChoices):
    GOLD = 'gold'
    GREEN = 'green'
    HYBRID = 'hybrid'
    BRONZE = 'bronze'
    CLOSED = 'closed'
    UNKNOWN = 'unknown'

class Abstract(models.Model):
    abstract = models.TextField()

class WorkPureData(TimeStampedModel, models.Model):
    # data for a work grabbed from pure
    abstract = models.OneToOneField(Abstract, on_delete=models.CASCADE, null=True, default=None)
    grants = models.ManyToManyField(Grant, related_name="openalex_works")
    authors = models.ManyToManyField('Author', through='Authorship', related_name="openalex_works")

    # ---- more fields needed here

class WorkOpenAlexData(TimeStampedModel, models.Model):
    # data for a work grabbed from openalex

    abstract = models.OneToOneField(Abstract, on_delete=models.CASCADE, null=True, default=None)
    authors = models.ManyToManyField('Author', through='Authorship', related_name="openalex_works")
    topics = models.ManyToManyField('Topic', related_name="openalex_works")
    journal = models.ForeignKey('Source', on_delete=models.CASCADE, related_name="openalex_works", null=True, default=None)
    # the following relations are defined from the other models:
    # locations - foreign key to Work
    # grants - many to many to Work
    

    openalex_id = models.CharField()
    openalex_created_date = models.DateField()
    openalex_updated_date = models.DateField()
    
    publication_date = models.DateField()
    publication_year = models.IntegerField()

    itemtype = models.CharField(choices=OpenAlexTypes)
    itemtype_crossref = models.CharField(choice=CrossrefTypes)
    language = models.CharField()
    
    is_paratext = models.BooleanField()
    is_retracted = models.BooleanField()
    is_oa = models.BooleanField()
    is_also_green = models.BooleanField()
    primary_location_is_oa = models.BooleanField(null=True)

    citations = models.IntegerField()
    cited_by_api_url = models.URLField()
    counts_per_year = models.JSONField()

    referenced_works = models.JSONField(null=True)
    related_works = models.JSONField(null=True)
    sustainable_development_goals = models.JSONField(null=True)

    license = models.CharField(null=True)
    apc_listed = models.JSONField(null=True)
    apc_paid = models.JSONField(null=True)
    oa_status = models.CharField(choices=OAStatus)
    oa_url = models.URLField(null=True)

    primary_location_landing_page = models.URLField(null=True)
    primary_location_pdf = models.URLField(null=True)
    primary_location_source_name = models.CharField(null=True)

    volume = models.CharField(null=True)
    issue = models.CharField(null=True)
    first_page = models.CharField(null=True)
    last_page = models.CharField(null=True)

    mag_id = models.IntegerField(null=True)
    pmid = models.CharField(null=True)
    pmcid = models.CharField(null=True)
    mesh = models.JSONField(null=True)
    indexed_in = models.JSONField(null=True)

    corresponding_author_ids = models.JSONField(null=True)
    corresponding_instutution_ids = models.JSONField(null=True)
    
    primary_topic = models.CharField(null=True)
    keywords = models.JSONField(null=True)

class WorkOtherData(TimeStampedModel, models.Model):
    ...

class Work(TimeStampedModel, models.Model):
    openalex_data = models.OneToOneField(WorkOpenAlexData, on_delete=models.CASCADE, null=True, default=None)
    pure_data = models.OneToOneField(WorkPureData, on_delete=models.CASCADE, null=True, default=None)
    other_data = models.OneToOneField(WorkOtherData, on_delete=models.CASCADE, null=True, default=None)
    
    doi = models.CharField(null=True)
    isbn = models.CharField(null=True)
    title = models.CharField()
    year = models.IntegerField()
    date = models.DateField(null=True)
    is_oa = models.BooleanField()
    oa_type = models.CharField(choices=OAStatus)
    itemtype = models.CharField(choices=MUSTypes)
    abstract = models.TextField(null=True)
    primary_link = models.URLField(null=True)
    best_oa_link = models.URLField(null=True)

class Authorship(TimeStampedModel, models.Model):
    class AuthorPosition(models.TextChoices):
        FIRST_AUTHOR = 'first'
        MIDDLE_AUTHOR = 'middle'
        LAST_AUTHOR = 'last'
    work = models.ForeignKey('Work', on_delete=models.CASCADE, related_name="authorships")
    author = models.ForeignKey('Author', on_delete=models.CASCADE, related_name="authorships")
    author_position = models.CharField(choices=AuthorPosition)
    is_corresponding = models.BooleanField(null=True)
    author_institutions = models.JSONField(null=True)
    raw_affiliation_strings = models.JSONField(null=True)
    raw_author_name = models.CharField(null=True)