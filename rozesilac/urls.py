from django.urls import path
from . import views

app_name = "rozesilac"

urlpatterns = [
    path('', views.dashboard, name='dashboard'),

    path("templates/", views.templates, name="templates"),
    path("templates/nova/", views.template_create, name="template_create"),
    path("templates/<int:template_id>/upravit/", views.template_edit, name="template_edit"),
    path("templates/<int:template_id>/duplikovat/", views.template_duplicate, name="template_duplicate"),
    path("templates/<int:template_id>/smazat/", views.template_delete, name="template_delete"),

    path("kontakty/", views.contacts, name="contacts"),
    path("kontakty/<int:contact_id>/", views.contact_detail, name="contact_detail"),
    path("kontakty/<int:contact_id>/upravit/", views.contact_edit, name="contact_edit"),

    path("obrazky/", views.images, name="images"),
    path("obrazky/upload/", views.image_upload, name="image_upload"),

    path("odeslat/", views.send, name="send"),
    path("kampane/", views.campaigns, name="campaigns"),
    path("kampane/<int:campaign_id>/", views.campaign_detail, name="campaign_detail"), 
]
    