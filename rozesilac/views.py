from django.shortcuts import render
from core.decorators import rozesilac_access_required

# Create your views here.

@rozesilac_access_required
def dashboard(request):
    return render(request, 'rozesilac/dashboard.html')