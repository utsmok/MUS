from django.http import HttpResponseNotFound
from django.shortcuts import render
from django.urls import path
from iommi import Form, Table

from mus_wizard.models import Group, Tag, Work

app_name = 'mus_wizard'


def view_work(request, pk):
    work = Work.objects.filter(pk=pk)
    if not work.exists():
        return HttpResponseNotFound('No work found with id {}'.format(pk))
    work_table = Table(auto__rows=work).bind(request=request)
    authorships = Table(auto__rows=work.first().authorships.all(),
                        columns__created__include=False,
                        columns__modified__include=False,
                        columns__work__include=False
                        ).bind(request=request)
    return render(request, 'work.html', context={'work': work_table, 'authorships': authorships})


urlpatterns = [
    path('group-form/', Form.create(auto__model=Group).as_view()),
    path('tag-form/', Form.create(auto__model=Tag).as_view()),
    path('works/<pk>/', view_work, name='work'),
]
