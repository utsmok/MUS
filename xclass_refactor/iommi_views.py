from iommi import Form, Table, Column
from xclass_refactor.models import Group, Tag, Work, Author, Authorship, Affiliation, Topic, Source, Location, Grant, DealData, Organization
from django.urls import include, path
from django.shortcuts import get_object_or_404, render
from django.http import HttpResponseNotFound

app_name = 'xclass_refactor'

def view_work(request, pk):
    work = Work.objects.filter(pk=pk)
    if not work.exists():
        return HttpResponseNotFound('No work found with id {}'.format(pk))
    work_table = Table(auto__rows=work).bind(request=request)

    authorships = Table(auto__rows=work.first().authorships.all(),
                        columns__author=Column(attr='author__name'),
                        columns__work__include=False,
                        columns__created__include=False,
                        columns__modified__include=False,
                        columns__affiliations=Column(attr='affiliations', cell__format=lambda value, **_: " | ".join([a.name for a in value.all()]),),                        
                        ).bind(request=request)
    return render(request, 'work.html', context={'work': work_table, 'authorships':authorships})

urlpatterns = [
    path('group-form/', Form.create(auto__model=Group).as_view()),
    path('tag-form/', Form.create(auto__model=Tag).as_view()),
    path('works/<pk>/', view_work, name='work'),
]