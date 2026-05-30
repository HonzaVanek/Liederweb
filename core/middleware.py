import hashlib
import logging

from django.conf import settings
from django.db import IntegrityError
from django.db.models import F
from django.utils import timezone

from .models import DailySiteVisitor, DailyPageVisitor


IGNORED_EXACT_PATHS = (
    "/admin",
    "/favicon.ico",
    "/favicon.png",
    "/apple-touch-icon.png",
    "/apple-touch-icon-precomposed.png",
    "/robots.txt",
)

IGNORED_PATH_PREFIXES = (
    "/admin/",
    "/static/",
    "/media/",

    # běžný skenovací bordel
    "/wp-admin/",
    "/wp-content/",
    "/wp-includes/",
    "/wordpress/",
    "/xmlrpc.php",
    "/.env",
    "/.git/",
    "/vendor/",
    "/cgi-bin/",
)

BOT_USER_AGENT_PARTS = (
    # obecné
    "bot",
    "crawler",
    "spider",
    "slurp",
    "headless",
    "monitor",
    "uptime",

    # technické klienty
    "python-requests",
    "python-urllib",
    "go-http-client",
    "curl",
    "wget",
    "httpclient",
    "http-client",
    "aiohttp",
    "okhttp",
    "java/",

    # SEO / indexace
    "ahrefs",
    "semrush",
    "mj12bot",
    "dotbot",
    "petalbot",
    "bytespider",
    "bingbot",
    "googlebot",
    "yandex",
    "baiduspider",
    "duckduckbot",
    "applebot",

    # AI crawleři
    "oai-searchbot",
    "gptbot",
    "chatgpt-user",
    "perplexitybot",
    "xai-searchbot",
    "claudebot",
    "ccbot",

    # social previeweři
    "facebookexternalhit",
    "facebot",
    "twitterbot",
    "linkedinbot",
    "slackbot",
    "discordbot",
    "telegrambot",
    "whatsapp",

    # často jen mezikrok před otevřením v browseru
    "qr scanner",
)

logger = logging.getLogger(__name__)


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

        # Počítat jen reálné načtení HTML stránky.
        # Tím vypadnou redirecty 301/302, 404, 403 atd.
        if response.status_code != 200:
            return

        if request.method != "GET":
            return

        if self.is_ignored_path(path):
            return

        # Pokud je uživatel přihlášený staff, nechci ho ve veřejné návštěvnosti.
        user = getattr(request, "user", None)
        if user and user.is_authenticated and user.is_staff:
            return

        content_type = response.headers.get("Content-Type", "")
        if content_type and "text/html" not in content_type:
            return

        # Browser prefetch/prerender nechceme počítat jako reálnou návštěvu.
        purpose = (
            request.headers.get("Purpose", "")
            or request.headers.get("Sec-Purpose", "")
        ).lower()
        if "prefetch" in purpose or "prerender" in purpose:
            return

        # Pokud browser posílá Sec-Fetch-Dest, počítat jen dokumenty.
        fetch_dest = request.headers.get("Sec-Fetch-Dest", "").lower()
        if fetch_dest and fetch_dest not in ("document", "iframe", "nested-document"):
            return

        user_agent = request.META.get("HTTP_USER_AGENT", "")[:500]
        if self.is_probably_bot(user_agent):
            return


        logger.warning(
            "IP DEBUG path=%s REMOTE_ADDR=%s X_FORWARDED_FOR=%s X_REAL_IP=%s",
            path,
            request.META.get("REMOTE_ADDR"),
            request.META.get("HTTP_X_FORWARDED_FOR"),
            request.META.get("HTTP_X_REAL_IP"),
        )
        
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


        page_path = path[:500]

        page_defaults = {
            "pageviews": 0,
        }

        try:
            page_visit, _created = DailyPageVisitor.objects.get_or_create(
                day=today,
                path=page_path,
                visitor_hash=visitor_hash,
                defaults=page_defaults,
            )
        except IntegrityError:
            page_visit = DailyPageVisitor.objects.get(
                day=today,
                path=page_path,
                visitor_hash=visitor_hash,
            )

        DailyPageVisitor.objects.filter(pk=page_visit.pk).update(
            pageviews=F("pageviews") + 1,
            last_seen_at=timezone.now(),
        )

    def is_ignored_path(self, path):
        if path in IGNORED_EXACT_PATHS:
            return True

        return any(path.startswith(prefix) for prefix in IGNORED_PATH_PREFIXES)

    def is_probably_bot(self, user_agent):
        user_agent_lower = (user_agent or "").lower()
        return any(part in user_agent_lower for part in BOT_USER_AGENT_PARTS)

    def get_client_ip(self, request):
        x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
        if x_forwarded_for:
            return x_forwarded_for.split(",")[0].strip()

        x_real_ip = request.META.get("HTTP_X_REAL_IP")
        if x_real_ip:
            return x_real_ip.strip()

        return request.META.get("REMOTE_ADDR")