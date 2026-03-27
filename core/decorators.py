from functools import wraps
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden

def rozesilac_access_required(view_func):
    @login_required
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_staff:
            return HttpResponseForbidden("Nemáte oprávnění pro přístup do rozesílače. Musíte se zaregistrovat a napsat Vaňkovi.")
        return view_func(request, *args, **kwargs)
    return _wrapped_view