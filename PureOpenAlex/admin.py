'''from django.contrib import admin

# Register your models here.
from inspect import isclass, getmembers
import PureOpenAlex.models as A
from django_extensions.db.models import TimeStampedModel
from django.core.files.storage import FileSystemStorage
from django.db.models.manager import Manager

for name, obj in getmembers(A):
    if isclass(obj):
        if obj != TimeStampedModel and obj != FileSystemStorage and obj != Manager:
            admin.site.register(obj)
'''