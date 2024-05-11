from django.db import models
from django_extensions.db.models import TimeStampedModel

class Topic(TimeStampedModel, models.Model):
    description = models.CharField()
    name = models.CharField()
    domain = models.CharField()
    field = models.CharField()
    openalex_id = models.CharField()
    works_count = models.IntegerField()
    keywords = models.JSONField(null=True)
    wikipedia = models.CharField(null=True)
    subfield = models.CharField(null=True)

class Funder(TimeStampedModel, models.Model):
    openalex_id = models.CharField()
    openalex_created_date = models.DateField()
    openalex_updated_date = models.DateField()
    name = models.CharField()
    homepage_url = models.URLField(null=True)
    description = models.CharField(null=True)
    country_code = models.CharField(null=True)
    name_alternatives = models.JSONField(null=True)
    cited_by_count = models.IntegerField()
    counts_by_year = models.JSONField(null=True)
    grants_count = models.IntegerField(null=True)
    crossref_id = models.CharField(null=True)
    doi = models.CharField(null=True)
    ror = models.CharField(null=True)
    wikidata = models.CharField(null=True)
    image_thumbnail_url = models.URLField(null=True)
    image_url = models.URLField(null=True)
    roles = models.JSONField(null=True)
    two_year_mean_citedness = models.FloatField(null=True)
    h_index = models.IntegerField(null=True)
    i10_index = models.IntegerField(null=True)
    works_count = models.IntegerField()

class Grant(TimeStampedModel, models.Model):
    funder = models.ForeignKey('Funder', on_delete=models.DO_NOTHING, related_name="grants")
    works = models.ManyToManyField('Work', related_name="grants")

    award_id = models.CharField(null=True)
    funder_name = models.CharField(null=True)


class Organization(TimeStampedModel, models.Model):
    class OrgTypes(models.TextChoices):
        EDUCATION = 'Education'
        HEALTHCARE = 'Healthcare'
        COMPANY = 'Company'
        ARCHIVE = 'Archive'
        NONPROFIT = 'Nonprofit'
        GOVERNMENT = 'Government'
        FACILITY = 'Facility'
        OTHER = 'Other'


    associated_institutes = models.ManyToManyField('Organization', related_name="associated_institutes", null=True)
    repositories = models.ManyToManyField('Source', related_name="repositories", null=True)
    
    cited_by_count = models.IntegerField(null=True)
    counts_by_year = models.JSONField(null=True)
    openalex_created_date = models.DateField()
    openalex_updated_date = models.DateField()
    openalex_id = models.CharField()
    
    name = models.CharField()
    acronyms = models.JSONField(null=True)
    name_alternatives = models.JSONField(null=True)
    geo_data = models.JSONField(null=True)
    homepage_url = models.URLField(null=True)

    grid_id = models.CharField(null=True)
    ror = models.CharField(null=True)
    wikidata = models.CharField(null=True)
    mag = models.CharField(null=True)
    wikipedia = models.CharField(null=True)

    image_thumbnail_url = models.URLField(null=True)
    image_url = models.URLField(null=True)
    roles = models.JSONField(null=True)

    two_year_mean_citedness = models.FloatField(null=True)
    h_index = models.IntegerField(null=True)
    i10_index = models.IntegerField(null=True)

    org_type = models.CharField(null=True, choices=OrgTypes)
    works_api_url = models.URLField(null=True)
    works_count = models.IntegerField(null=True)
