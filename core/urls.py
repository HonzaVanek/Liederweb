from django.urls import path
from . import views
from .views import VlastniLoginView
from django.contrib.auth import views as auth_views

urlpatterns = [
    path('', views.home, name='home'),
    path('login/', VlastniLoginView.as_view(), name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='login'), name='logout'),
    path('registrace/', views.registrace, name='registrace'),
    path('activate/<uidb64>/<token>/', views.activate, name='activate'),
]