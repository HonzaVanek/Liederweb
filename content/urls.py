from django.urls import path

from . import views
from . import staff_views

app_name = "content"

public_urlpatterns = [
    path("<slug:slug>/", views.post_detail, name="post_detail"),
]

staff_urlpatterns = [
    path("", staff_views.post_list, name="post_list"),
    path("new/", staff_views.post_create, name="post_create"),
    path("<int:post_id>/edit/", staff_views.post_edit, name="post_edit"),
]

urlpatterns = public_urlpatterns