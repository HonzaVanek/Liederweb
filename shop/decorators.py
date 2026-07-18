from functools import wraps

from django.conf import settings
from django.http import Http404


def shop_public_or_staff_preview(view_func):
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        shop_public_enabled = getattr(
            settings,
            "SHOP_PUBLIC_ENABLED",
            False,
        )

        if not shop_public_enabled and not request.user.is_staff:
            raise Http404

        return view_func(request, *args, **kwargs)

    return _wrapped_view