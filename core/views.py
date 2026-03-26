from django.shortcuts import render
from django.contrib.auth.views import LoginView
from .forms import VlastniLoginForm

def home(request):
    return render(request, 'core/home.html')

class VlastniLoginView(LoginView):
    template_name = 'core/login.html'
    form_class = VlastniLoginForm