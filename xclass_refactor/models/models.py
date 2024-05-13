from django.db import models
from django.db.models import Q
from django_extensions.db.models import TimeStampedModel
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.fields import GenericForeignKey, GenericRelation
from xclass_refactor.constants import INSTITUTE_GROUPS
'''
Models for xclass_refactor: the 'simple' version.

Models are light and contain the most important info; like name & ids; plus whatever is useful for
sorting and grouping.

The detailed data from the API is not (yet) stored in proper SQL rows; instead the data pulled from
MongoDB is stored as a single JSON as a MongoData entry, which has a many-to-one relationship with 
each other model (each mongodata entry only has a single link, but each model instance can have multiple data sources)

'''

class MongoData(TimeStampedModel, models.Model):
    class MongoCollections(models.TextChoices):
        WORKS_OPENALEX = 'works_openalex'
        AUTHORS_OPENALEX = 'authors_openalex'
        TOPICS_OPENALEX = 'topics_openalex'
        SOURCES_OPENALEX = 'sources_openalex'
        FUNDERS_OPENALEX = 'funders_openalex'
        INSTITUTIONS_OPENALEX = 'institutions_openalex'
        AUTHORS_PURE = 'authors_pure'
        EMPLOYEES_PEOPLEPAGE = 'employees_peoplepage'
        DEALS_JOURNALBROWSER = 'deals_journalbrowser'
        ITEMS_CROSSREF = 'items_crossref'
        ITEMS_DATACITE = 'items_datacite'
        ITEMS_OPENAIRE = 'items_openaire'
        ITEMS_ORCID = 'items_orcid'

    data = models.JSONField()
    source_collection = models.CharField(choices=MongoCollections) # the mongodb collection this data is from
    source_id = models.CharField() # the _id of the doc in the mongodb collection
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey("content_type", "object_id")
    
    class Meta:
        indexes = [
            models.Index(fields=["content_type", "object_id", "source_collection"]),
        ]

class Tag(TimeStampedModel, models.Model):
    class TagTypes(models.TextChoices):
        PEER_REVIEWED = 'PR' # peer-reviewed works (item type grouping)
        ONLY_REPO = 'OR' # work only found in repository -- no matches in other apis
        FOUND_IN_REPOSITORY = 'FR' # work found in repository of primary institute
        REPO_FOUND_IN_OPENALEX = 'RF' # repository of primary institute found in OpenAlex Locations for this work
        INSTITUTE_AUTHOR_MATCH = 'IA' # at least one of the authors of work has affiliation w/ primary instutution in the publication year of the work
        HAS_ERROR = 'HE' # item is tagged as having an error, needs repairs -- details in 'notes' field
        GENERIC = 'GN' # generic tag, not specific to any type -- used as default
        
    tag_type = models.CharField(choices=TagTypes, default=TagTypes.GENERIC, max_length=2)
    notes = models.TextField(default='None')
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey("content_type", "object_id")

    class Meta:
        indexes = [
            models.Index(fields=["content_type", "object_id", "source_collection", "tag_type"]),
        ]

class MusModel(TimeStampedModel, models.Model):
    raw_data = GenericRelation(MongoData)
    tags = GenericRelation(Tag)

'''
Below: all actual models, inheriting from MusModel so they all have the raw_data field + timestamps
'''

class Topic(MusModel):
    class DomainTypes(models.TextChoices):
        PHYSICAL_SCIENCES = 'Physical Sciences'
        SOCIAL_SCIENCES = 'Social Sciences'
        HEALTH_SCIENCES = 'Health Sciences'
        LIFE_SCIENCES = 'Life Sciences'
    class FieldTypes(models.TextChoices):
        MEDICINE = 'Medicine'
        SOCIAL_SCIENCES = 'Social Sciences'
        ENGINEERING = 'Engineering'
        ARTS_AND_HUMANITIES = 'Arts and Humanities'
        COMPUTER_SCIENCE = 'Computer Science'
        BIOCHEMISTRY_GENETICS_AND_MOLECULAR_BIOLOGY = 'Biochemistry, Genetics and Molecular Biology'
        AGRICULTURAL_AND_BIOLOGICAL_SCIENCES = 'Agricultural and Biological Sciences'
        ENVIRONMENTAL_SCIENCES = 'Environmental Sciences'
        PHYSICS_AND_ASTRONOMY = 'Physics and Astronomy'
        BUSINESS_MANAGEMENT_AND_ACCOUNTING = 'Business, Management and Accounting'
        MATERIALS_SCIENCE = 'Materials Science'
        ECONOMICS_ECONOMETRICS_AND_FINANCE = 'Economics, Econometrics and Finance'
        HEALTH_PROFESSIONS = 'Health Professions'
        PSYCHOLOGY = 'Psychology'
        CHEMISTRY = 'Chemistry'
        EARTH_AND_PLANETARY_SCIENCES = 'Earth and Planetary Sciences'
        NEUROSCIENCE = 'Neuroscience'
        MATHEMATICS = 'Mathematics'
        IMMUNOLOGY_AND_MICROBIOLOGY = 'Immunology and Microbiology'
        DECISION_SCIENCES = 'Decision Sciences'
        ENERGY = 'Energy'
        NURSING = 'Nursing'
        PHARMACOLOGY_TOXICOLOGY_AND_PHARMACEUTICALS = 'Pharmacology, Toxicology and Pharmaceutics'
        DENTISTRY = 'Dentistry'
        CHEMICAL_ENGINEERING = 'Chemical Engineering'
    description = models.CharField()
    name = models.CharField()
    domain = models.CharField(choices=DomainTypes.choices)
    field = models.CharField(choices=FieldTypes.choices)
    openalex_id = models.URLField()
    works_count = models.IntegerField()
    keywords = models.JSONField()
    wikipedia = models.URLField()
    subfield = models.CharField()
    subfield_id = models.CharField()

    class Meta:
        indexes = [
            models.Index(fields=["openalex_id"]),
            models.Index(fields=["wikipedia"]),
        ]

class Funder(MusModel):
    as_orgs = models.ManyToManyField('Organization', related_name="as_funders")
    as_other_funders = models.ManyToManyField('Funder', related_name="other_funders_entries")

    openalex_id = models.URLField()
    name = models.CharField()
    alternate_names = models.JSONField(null=True)
    country_code = models.CharField()
    counts_by_year = models.JSONField()
    openalex_created_date = models.DateTimeField()
    openalex_updated_date = models.DateTimeField()
    grants_count = models.IntegerField()
    description = models.CharField(null=True)
    homepage_url = models.URLField(null=True)
    ror = models.URLField(null=True)
    wikidata = models.URLField(null=True)
    crossref = models.CharField(null=True)
    doi = models.URLField(null=True)
    image_thumbnail_url = models.URLField(null=True)
    image_url = models.URLField(null=True)

    impact_factor = models.FloatField()
    h_index = models.IntegerField()
    i10_index = models.IntegerField()
    works_count = models.IntegerField()
    cited_by_count = models.IntegerField()

    class Meta:
        indexes = [
            models.Index(fields=["openalex_id"]),
            models.Index(fields=["doi"]),
            models.Index(fields=["ror"]),
            models.Index(fields=["crossref"]),
            models.Index(fields=["country_code"]),
            models.Index(fields=["image_url"]),
            models.Index(fields=["image_thumbnail_url"]),
            models.Index(fields=["wikidata"]),
        ]

class Grant(MusModel):
    funder = models.ForeignKey('Funder', on_delete=models.CASCADE, related_name="grants")
    award_id = models.CharField(null=True)
    funder_name = models.CharField()
    works = models.ManyToManyField('Work', related_name="grants")
    openalex_id = models.URLField()

    class Meta:
        indexes = [
            models.Index(fields=["openalex_id"]),
            models.Index(fields=["award_id"]),
        ]

class Organization(MusModel):

    topics = models.ManyToManyField('Topic', related_name="organizations")
    repositories = models.ManyToManyField('Source', related_name="repositories")
    lineage = models.ManyToManyField('Organization', related_name="children")

    # this is the type of this institution instance + all related institutions
    # note: double check for accidental duplicates when going through the list of related items!!
    # maybe change this to use tags instead of this list of bools?
    type_education = models.BooleanField(default=False)
    type_funder = models.BooleanField(default=False)
    type_healthcare = models.BooleanField(default=False)
    type_company = models.BooleanField(default=False)
    type_archive = models.BooleanField(default=False)
    type_nonprofit = models.BooleanField(default=False)
    type_government = models.BooleanField(default=False)
    type_facility = models.BooleanField(default=False)
    type_other = models.BooleanField(default=False)

    name = models.CharField()
    name_acronyms = models.JSONField(null=True)
    name_alternatives = models.JSONField(null=True)

    ror = models.CharField(null=True)
    openalex_id = models.URLField()
    wikipedia = models.URLField(null=True)
    wikidata = models.URLField(null=True)
    openalex_created_date = models.DateTimeField()
    openalex_updated_date = models.DateTimeField()
    country_code = models.CharField(null=True)

    works_count = models.IntegerField(null=True)
    cited_by_count = models.IntegerField(null=True)
    impact_score = models.FloatField(null=True)
    h_index = models.IntegerField(null=True)
    i10_index = models.IntegerField(null=True)
    
    image_thumbnail_url = models.URLField(null=True)
    image_url = models.URLField(null=True)

    class Meta:
        indexes = [
            models.Index(fields=["openalex_id"]),
            models.Index(fields=["ror"]),
            models.Index(fields=["wikipedia"]),
            models.Index(fields=["wikidata"]),
            models.Index(fields=["country_code"]),
            models.Index(fields=["image_url"]),
            models.Index(fields=["image_thumbnail_url"]),
        ]
class Group(models.Model):
    '''
    simple class to hold data for author's group (+ faculty) -- only use for main institution authors
    '''
    def get_groups():
        GroupList = models.TextChoices('GroupList', INSTITUTE_GROUPS)
        return GroupList
    
    class Faculties(models.TextChoices):
        EEMCS = 'EEMCS'
        BMS = 'BMS'
        ET = 'ET'
        ITC = 'ITC'
        TNW = 'TNW'
        OTHER = 'OTHER'

    name = models.CharField(choices=get_groups)
    faculty = models.CharField(choices=Faculties)
    class Meta:
        indexes = [
            models.Index(fields=["name"]),
            models.Index(fields=["faculty"]),
        ]

class Author(MusModel):
    affiliations = models.ManyToManyField(Organization,through='Affiliation', related_name="authors")
    # rest of fields
    
    name = models.CharField()
    openalex_id = models.URLField(null=True)

    class Meta:
        indexes = [
            models.Index(fields=["openalex_id"]),
        ]

class Affiliation(MusModel):
    author = models.ForeignKey(Author, on_delete=models.CASCADE, related_name="affiliations", db_index=True)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="affiliated_authors", db_index=True)
    years = models.JSONField(null=True)
    position = models.CharField(blank=True, default='')
    groups = models.ManyToManyField(Group, related_name="affiliations")

    class Meta:
        indexes = [
            models.Index(fields=["author", "organization"]),
            models.Index(fields=["organization", "author"]),
            models.Index(fields=["years"]),
        ]

class Source(MusModel):
    lineage = models.ManyToManyField('Organization', related_name="children")
    # rest of fields

class DealData(MusModel):
    publisher = models.ForeignKey(Source, on_delete=models.CASCADE, related_name="deals", db_index=True)
    # rest of fields

class Location(MusModel):
    work = models.ForeignKey('Work', on_delete=models.CASCADE, related_name="locations", db_index=True)
    source = models.ForeignKey('Source', on_delete=models.CASCADE, related_name="locations", db_index=True)
    # rest of fields

class Abstract(MusModel):
    text = models.TextField()

class Work(MusModel):
    class OAStatus(models.TextChoices):
        GOLD = 'gold'
        BRONZE = 'bronze'
        GREEN = 'green'
        HYBRID = 'hybrid'
        CLOSED = 'closed'
        NOT_SET = 'not_set'
    class MUSTypes(models.TextChoices):
        BOOK = 'book'
        CONFERENCE_PROCEEDING = 'conference_proceeding'
        JOURNAL_ARTICLE = 'journal_article'
        DISSERTATION = 'dissertation'
        REPORT = 'report'
        OTHER = 'other'
        NOT_SET = 'not_set'
        # add more types and map to pure, openalex & crossref types
        # store this mapping somewhere to be viewed by users in the UI as well

    authors = models.ManyToManyField(Author, through='Authorship', related_name="works")
    topics = models.ManyToManyField(Topic, related_name="works")
    abstract = models.OneToOneField(Abstract, on_delete=models.CASCADE, null=True, default=None)
    
    # fk to source? (--journal)

    openalex_id = models.URLField(null=True)
    doi = models.CharField(null=True)
    title = models.CharField()
    publication_year = models.IntegerField()
    publication_date = models.DateField()

    is_oa = models.BooleanField(default=False)
    oa_type = models.CharField(choices=OAStatus, default=OAStatus.NOT_SET)
    itemtype = models.CharField(choices=MUSTypes, default=MUSTypes.NOT_SET)

    class Meta:
        indexes = [
            models.Index(fields=["openalex_id"]),
            models.Index(fields=["doi"]),
            models.Index(fields=["publication_date"]),
            models.Index(fields=["publication_year"]),
            models.Index(fields=["oa_type"]),
            models.Index(fields=["itemtype"]),
        ]
        
class Authorship(MusModel):
    class PositionTypes(models.TextChoices):
        FIRST = 'first'
        MIDDLE = 'middle'
        LAST = 'last'
        UNKNOWN = '-'
    author = models.ForeignKey(Author, on_delete=models.CASCADE, related_name="authorships")
    work = models.ForeignKey(Work, on_delete=models.CASCADE, related_name="authorships")
    position = models.CharField(choices=PositionTypes, default=PositionTypes.UNKNOWN)
    is_corresponding = models.BooleanField(default=False)

    class Meta:
        indexes = [
            models.Index(fields=["author", "work"]),
            models.Index(fields=["work", "author"]),
            models.Index(fields=["is_corresponding"], condition=Q(is_corresponding=True)),
        ]
