import logging
from functools import wraps
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden



security_logger = logging.getLogger("liederweb.security")


def staff_required(view_func):
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_staff:
            security_logger.warning(
                "Unauthorized staff access attempt | path=%s | user_id=%s | username=%s | authenticated=%s",
                request.path,
                request.user.id if request.user.is_authenticated else None,
                request.user.get_username() if request.user.is_authenticated else None,
                request.user.is_authenticated,
            )
            return HttpResponseForbidden(
                "Nemáte oprávnění pro přístup do této sekce. Musíte se zaregistrovat a napsat Vaňkovi."
            )

        return view_func(request, *args, **kwargs)

    return login_required(_wrapped_view)