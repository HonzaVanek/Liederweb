from django.urls import path
from . import views
from .views import VlastniLoginView
from django.contrib.auth import views as auth_views

app_name = 'core'

urlpatterns = [
    path('', views.home, name='home'),
    path('login/', VlastniLoginView.as_view(), name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='core:login'), name='logout'),
    path('registrace/', views.registrace, name='registrace'),
    path('activate/<uidb64>/<token>/', views.activate, name='activate'),
    path('password-reset/', auth_views.PasswordResetView.as_view(template_name="core/password_reset_form.html", email_template_name="core/password_reset_email.html", subject_template_name="core/password_reset_subject.txt", success_url="done/",), name='password_reset'),
    path('password-reset/done/', auth_views.PasswordResetDoneView.as_view(template_name="core/password_reset_done.html"), name="password_reset_done"),
    path("reset/<uidb64>/<token>/", auth_views.PasswordResetConfirmView.as_view(template_name="core/password_reset_confirm.html", success_url="/password-reset/complete/"), name="password_reset_confirm"),
    path("password-reset/complete/", auth_views.PasswordResetCompleteView.as_view(template_name="core/password_reset_complete.html"), name="password_reset_complete"),
    path("newsletter/prihlaseni/", views.newsletter_signup, name="newsletter_signup"),

    path("lide/", views.PersonListView.as_view(), name="person_list"),
    path("lide/<slug:slug>/", views.PersonDetailView.as_view(), name="person_detail"),

    path("staff/lide/", views.PersonAdminListView.as_view(), name="person_admin_list"),
    path("staff/lide/novy/", views.PersonCreateView.as_view(), name="person_create"),
    path("staff/lide/<slug:slug>/upravit/", views.PersonUpdateView.as_view(), name="person_update"),
]