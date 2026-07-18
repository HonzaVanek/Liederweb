from django.conf import settings
from django.http import Http404
from django.shortcuts import render

from .decorators import shop_public_or_staff_preview

@shop_public_or_staff_preview
def shop_home(request):
    return render(
        request,
        "shop/shop_home.html",
        {
            "shop_preview_mode": not getattr(
                settings,
                "SHOP_PUBLIC_ENABLED",
                False,
            ),
        },
    )