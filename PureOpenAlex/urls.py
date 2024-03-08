from django.urls import path
from .views import (
    home,
    single_article,
    faculty,
    removemark,
    addmark,
    searchpaper,
    addarticle,
    author,
    customfilter,
    single_article_pure_view,
    getris,
    dbinfo,
    filtertoolpage,
    single_article_raw_data,
    get_raw_data_json,
    chart
)

app_name = "PureOpenAlex"

urlpatterns = [
    path("", home, name="home"),
    path("article/<int:article_id>/", single_article, name="single_article"),
    path("faculty/<str:name>/", faculty, name="faculty"),
    path("allpapers/", faculty, name="allpapers"),
    path("allpapers/<str:name>/<str:filter>/", faculty, name="papersfiltered"),
    path("removemark/", removemark, name="removeallmarks"),
    path("removemark/<int:id>/", removemark, name="removemark"),
    path("addmark/<int:id>/", addmark, name="addmark"),
    path('search/results/', searchpaper, name='search_results_view'),
    path('addarticle/<path:doi>', addarticle, name='addarticle'),
    path('authorarticles/<str:name>', author, name='authorarticles'),
    path('customfilter/',customfilter, name='customfilter'),
    path('pure_entries/<int:article_id>/', single_article_pure_view, name='pure_entries'),
    path('getris/', getris, name='getris'),
    path('dbinfo/', dbinfo, name='dbinfo'),
    path('filtertools/', filtertoolpage, name='filtertools'),
    path('rawdata/<int:article_id>/', single_article_raw_data, name='rawdata'),
    path('rawjson/<int:article_id>/', get_raw_data_json, name='rawjson'),
    path('chart/', chart, name='chart'),
]
