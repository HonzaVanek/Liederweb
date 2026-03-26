from django.urls import path
from . import views
from .views import VlastniLoginView

urlpatterns = [
    path('', views.home, name='home'),
    path('login/', VlastniLoginView.as_view(), name='login'),
]