from django.urls import path
from . import views

app_name = "rozesilac"

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path("templates/", views.templates, name="templates"),
    path("kontakty/", views.contacts, name="contacts"),
    path("obrazky/", views.images, name="images"),
    path("odeslat/", views.send, name="send"),
    path("kampane/", views.campaigns, name="campaigns"),
]
    