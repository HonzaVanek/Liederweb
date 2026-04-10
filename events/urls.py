from django.urls import path
from . import views

app_name = "events"

urlpatterns = [
    path("", views.event_list, name="event_list"),
    path("create/", views.event_create, name="event_create"),
    path("<int:pk>/", views.event_detail, name="event_detail"),
    path("<int:pk>/edit/", views.event_edit, name="event_edit"),
    
    # veřejná stránka se slugem prý má být dole jako poslední. Nejsem si jistý proč to tak je, ale asi aby se neshodovalo s ostatními URL, které začínají číslem (pk).
    path("<slug:slug>/", views.public_event_detail, name="public_event_detail")
]