from django.db import models
from django_extensions.db.models import TimeStampedModel
from .models import Organization
from django.core.serializers.json import DjangoJSONEncoder
class AuthorOpenAlexData(TimeStampedModel, models.Model):
    
    cited_by_count = models.IntegerField(null=True)
    counts_by_year = models.JSONField(null=True)

    openalex_created_date = models.DateTimeField()
    openalex_updated_date = models.DateTimeField()

    name = models.CharField()
    name_alternatives = models.JSONField(null=True)
    openalex_id = models.CharField()
    orcid = models.CharField(null=True)
    scopus = models.CharField(null=True)
    twitter = models.CharField(null=True)
    wikipedia = models.CharField(null=True)

    impact_factor = models.FloatField(null=True)
    h_index = models.IntegerField(null=True)
    i10_index = models.IntegerField(null=True)

    works_api_url = models.URLField()
    works_count = models.IntegerField()
class AuthorPureData(TimeStampedModel, models.Model):
    name=models.CharField()
    last_name=models.CharField()
    first_names=models.CharField()
    orcid=models.CharField(null=True)
    isni=models.CharField(null=True)
    scopus_id=models.CharField(null=True)
    links=models.JSONField(null=True)
    default_publishing_name=models.CharField(null=True)
    known_as_name= models.CharField(null=True)
    affl_start_date= models.JSONField(null=True, encoder=DjangoJSONEncoder)
    affl_end_date= models.JSONField(null=True, encoder=DjangoJSONEncoder)
    uuid= models.UUIDField()
    pureid=models.CharField()
    last_modified= models.DateTimeField()
    affl_periods=models.JSONField(null=True, encoder=DjangoJSONEncoder)
    org_names= models.JSONField(null=True)
    org_uuids= models.JSONField(null=True)
    org_pureids= models.JSONField(null=True)
    faculty_name=models.JSONField(null=True)
    faculty_pureid=models.JSONField(null=True)
    
class AuthorOtherData(TimeStampedModel, models.Model):
    ...

class AuthorEmployeeData(TimeStampedModel, models.Model):
    class EmploymentTypes(models.TextChoices):
        RESEARCH_STAFF = 'wp'
        PROFESSOR = 'professor'
        OTHER = 'misc'
        SUPPORT_STAFF = 'obp'
    employment_type = models.CharField(choices=EmploymentTypes)
    position = models.CharField()

    profile_url = models.URLField()
    research_url = models.URLField()
    avatar_url = models.URLField()
    email = models.EmailField()
    first_name = models.CharField()
    fullname = models.CharField()
    name = models.CharField()
    name_alternatives = models.JSONField()

    grouplist = models.JSONField()

    # name_searched_for: the name from openalex used to find this data
    # name_found: the matching name found in people pages
    # similarity: how similar the names are, calculated by fuzzymatcher
    name_searched_for = models.CharField()
    name_found = models.CharField()
    similarity = models.FloatField()


class Author(TimeStampedModel, models.Model):
    employee_data = models.OneToOneField(AuthorEmployeeData, on_delete=models.CASCADE, null=True, default=None)
    openalex_data = models.OneToOneField(AuthorOpenAlexData, on_delete=models.CASCADE, null=True, default=None)
    pure_data = models.OneToOneField(AuthorPureData, on_delete=models.CASCADE, null=True, default=None)
    other_data = models.OneToOneField(AuthorOtherData, on_delete=models.CASCADE, null=True, default=None)

    name = models.CharField()   # full name of author in standard formatting (TBD!)
    title_prefix = models.CharField(null=True)
    title_suffix = models.CharField(null=True)
    first_name = models.CharField()
    last_name = models.CharField()
    initials = models.CharField()
    alternative_names = models.JSONField(null=True)

    openalex_id = models.CharField(null=True)
    orcid = models.CharField(null=True)
    pure_id = models.CharField(null=True)
    isni = models.CharField(null=True)
    scopus_id = models.CharField(null=True)

    employee = models.BooleanField()        #  make generated field maybe?
    affiliations = models.ManyToManyField(Organization, related_name="authors", through="Affiliation")


class Affiliation(TimeStampedModel, models.Model):
    author = models.ForeignKey(Author, on_delete=models.CASCADE, related_name="affils")
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="affiliated_authors")
    years = models.JSONField(null=True)