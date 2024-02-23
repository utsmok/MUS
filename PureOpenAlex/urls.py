from django.urls import path
from .views import (
    home,
    single_article,
    delete_duplicates,
    faculty,
    removemark,
    addmark,
    facultypaginator,
    searchpaper,
    addarticle,
    author,
    customfilter,
    single_article_pure_view,
)

app_name = "PureOpenAlex"

urlpatterns = [
    path("", home, name="home"),
    path("article/<int:article_id>/", single_article, name="single_article"),
    path("delete_duplicates/", delete_duplicates, name="delete_duplicates"),
    path("faculty/<str:name>/", faculty, name="faculty"),
    path("allpapers/", faculty, name="allpapers"),
    path("allpapers/<str:name>/<str:filter>/", faculty, name="papersfiltered"),
    path("removemark/", removemark, name="removeallmarks"),
    path("removemark/<int:id>/", removemark, name="removemark"),
    path("addmark/<int:id>/", addmark, name="addmark"),
    path("facultypage/<str:name>/", facultypaginator, name="facultypage"),
    path(
        "facultypage/<str:name>/<str:filter>/<str:sort>",
        facultypaginator,
        name="facultypagefiltered",
    ),
    path('search/results/', searchpaper, name='search_results_view'),
    path('addarticle/<path:doi>', addarticle, name='addarticle'),
    path('authorarticles/<str:name>', author, name='authorarticles'),
    path('customfilter/',customfilter, name='customfilter'),
    path('pure_entries/<int:article_id>/', single_article_pure_view, name='pure_entries'),
]
