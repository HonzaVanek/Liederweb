from django.urls import path
from . import views

app_name = "events"

urlpatterns = [
    path("", views.event_list, name="event_list"),
    path("create/", views.event_create, name="event_create"),
    path("<int:pk>/", views.event_detail, name="event_detail"),
    path("<int:pk>/edit/", views.event_edit, name="event_edit"),
    path("<int:pk>/tickets/", views.event_tickets, name="event_tickets"),
    
    path("vip/<str:token>/", views.vip_event_detail, name="vip_event_detail"),
    path("vip/<str:token>/reserve/", views.vip_reserve, name="vip_reserve"),
    path("vip/<str:token>/done/", views.vip_reservation_done, name="vip_reservation_done"),

    path("<int:pk>/export-vip/", views.event_export_vip_xlsx, name="event_export_vip_xlsx"),
    
    # veřejná stránka se slugem musí být až nakonec, protože je nejširší
    # a jinak by mohla spolknout jiné textové URL
    path("<slug:slug>/", views.public_event_detail, name="public_event_detail")
]