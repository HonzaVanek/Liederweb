from django.urls import path
from . import views

app_name = "rozesilac"

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
]
    