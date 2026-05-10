import hashlib

from django.conf import settings
from django.db import IntegrityError
from django.db.models import F
from django.utils import timezone

from .models import DailySiteVisitor


IGNORED_PATH_PREFIXES = (
    "/admin/",
    "/static/",
    "/media/",
    "/favicon.ico",
    "/robots.txt",
)

BOT_USER_AGENT_PARTS = (
    "bot",
    "crawler",
    "spider",
    "slurp",
    "bingpreview",
    "python-requests",
    "uptime",
    "monitor",
    "headless",
)


class SiteVisitStatsMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        try:
            self.track_visit(request, response)
        except Exception:
            # Statistiky nikdy nesmí rozbít web.
            pass

        return response

    def track_visit(self, request, response):
        path = request.path or ""

        if response.status_code >= 400:
            return

        if request.method != "GET":
            return

        if any(path.startswith(prefix) for prefix in IGNORED_PATH_PREFIXES):
            return

        user_agent = request.META.get("HTTP_USER_AGENT", "")[:500]
        user_agent_lower = user_agent.lower()

        if any(part in user_agent_lower for part in BOT_USER_AGENT_PARTS):
            return

        ip = self.get_client_ip(request)

        if not ip:
            return

        today = timezone.localdate()

        raw_visitor_id = f"{today}|{ip}|{user_agent}|{settings.SECRET_KEY}"
        visitor_hash = hashlib.sha256(raw_visitor_id.encode("utf-8")).hexdigest()

        defaults = {
            "pageviews": 0,
            "first_path": path[:500],
            "last_path": path[:500],
        }

        try:
            visit, _created = DailySiteVisitor.objects.get_or_create(
                day=today,
                visitor_hash=visitor_hash,
                defaults=defaults,
            )
        except IntegrityError:
            visit = DailySiteVisitor.objects.get(
                day=today,
                visitor_hash=visitor_hash,
            )

        DailySiteVisitor.objects.filter(pk=visit.pk).update(
            pageviews=F("pageviews") + 1,
            last_seen_at=timezone.now(),
            last_path=path[:500],
        )

    def get_client_ip(self, request):
        x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
        if x_forwarded_for:
            return x_forwarded_for.split(",")[0].strip()

        x_real_ip = request.META.get("HTTP_X_REAL_IP")
        if x_real_ip:
            return x_real_ip.strip()

        return request.META.get("REMOTE_ADDR")