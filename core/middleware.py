import hashlib
import logging
from django.core.cache import cache

from django.conf import settings
from django.db import IntegrityError
from django.db.models import F
from django.utils import timezone
from django.urls import resolve

from .models import DailySiteVisitor, DailyPageVisitor

from urllib.parse import urlsplit, urlunsplit


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

    "googleother",
    "appengine-google",
    "virustotal",
    "virustotalcloud",
    "aisearchindex",

    "scrapy",
    "libwww",
    "mechanize",
    "beautifulsoup",
    "bs4",
    "requests",

    #další nalezené z logů
    "google-read-aloud",
    "read-aloud",
    "greedyhand",
    "nutch",
    "node-fetch",
    "builtwith",
    "visionheight",
)

logger = logging.getLogger("liederweb.traffic")
staff_audit_logger = logging.getLogger("liederweb.staff_audit")

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

    def clean_referer(self, referer):
        if not referer:
            return ""

        try:
            parts = urlsplit(referer)
            return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))
        except Exception:
            return referer.split("?", 1)[0][:300]
        
    def is_suspicious_rapid_visitor(self, client_label, path):
        now_ts = int(timezone.now().timestamp())

        cache_key = f"traffic_hits:{client_label}"
        hits = cache.get(cache_key, [])

        hits = [
            hit for hit in hits
            if now_ts - hit["ts"] <= 10
        ]

        hits.append({
            "ts": now_ts,
            "path": path,
        })

        cache.set(cache_key, hits, timeout=60)

        unique_paths = {hit["path"] for hit in hits}

        if len(hits) >= 5 and len(unique_paths) >= 4:
            return True

        return False


    def track_visit(self, request, response):
        path = request.path or ""

        # Počítat jen reálné načtení HTML stránky.
        # Tím vypadnou redirecty 301/302, 404, 403 atd.
        if response.status_code != 200:
            return

        if request.method not in ("GET", "POST"):
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
        if not user_agent.strip():
            return
        if self.is_probably_bot(user_agent):
            return


        ip = self.get_client_ip(request)
        if not ip:
            return

        today = timezone.localdate()

        raw_client_id = f"{today}|{ip}|{settings.SECRET_KEY}"
        client_hash = hashlib.sha256(raw_client_id.encode("utf-8")).hexdigest()
        client_label = client_hash[:8]

        raw_visitor_id = f"{today}|{ip}|{user_agent}|{settings.SECRET_KEY}"
        visitor_hash = hashlib.sha256(raw_visitor_id.encode("utf-8")).hexdigest()
        visitor_label = visitor_hash[:8]

        if self.is_suspicious_rapid_visitor(client_label, path):
            logger.info(
                "SKIP_BOT_LIKE ip=%s client=%s visitor=%s method=%s status=%s path=%s ua=%s",
                ip,
                client_label,
                visitor_label,
                request.method,
                response.status_code,
                path[:300],
                user_agent[:300],
            )
            return

        referer = self.clean_referer(request.META.get("HTTP_REFERER", ""))[:300]

        logger.info(
            "VISIT ip=%s client=%s visitor=%s method=%s status=%s path=%s referer=%s ua=%s",
            ip,
            client_label,
            visitor_label,
            request.method,
            response.status_code,
            path[:300],
            referer,
            user_agent[:300],
        )

        if request.method != "GET":
            return

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
    



### logování staff akcí ###
STAFF_AUDIT_IGNORED_EXACT_PATHS = (
    "/favicon.ico",
    "/favicon.png",
    "/apple-touch-icon.png",
    "/apple-touch-icon-precomposed.png",
    "/robots.txt",
)

STAFF_AUDIT_IGNORED_PATH_PREFIXES = (
    "/static/",
    "/media/",
)


IMPORTANT_STAFF_GET_PARTS = (
    "/export",
    "/download",
    "/pdf",
    "/preview",
    "/send-test",
)


class StaffAuditMiddleware:
    """
    Loguje aktivitu přihlášených staff uživatelů.

    Není to přesný audit změn typu "pole X změněno z A na B".
    Je to stopa, kdo jako staff otevřel nebo odeslal jakou stránku.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        try:
            response = self.get_response(request)
        except Exception as e:
            try:
                self.log_staff_request(request, response=None, exception=e)
            except Exception:
                pass
            raise

        try:
            self.log_staff_request(request, response=response)
        except Exception:
            # Audit log nikdy nesmí rozbít web.
            pass

        return response

    def log_staff_request(self, request, response=None, exception=None):
        path = request.path or ""

        if self.is_ignored_path(path):
            return

        user = getattr(request, "user", None)

        if not user or not user.is_authenticated or not user.is_staff:
            return

        method = request.method or ""

        # Chci logovat i běžné GET, takže nefiltrujeme jen POST.
        if method not in ("GET", "POST", "PUT", "PATCH", "DELETE"):
            return

        status_code = getattr(response, "status_code", None)

        try:
            match = resolve(request.path_info)
            view_name = match.view_name or ""
        except Exception:
            view_name = ""

        user_agent = request.META.get("HTTP_USER_AGENT", "")[:300]
        ip = self.get_client_ip(request)

        kind = self.get_action_kind(request)

        staff_audit_logger.info(
            "STAFF_ACTION kind=%s user_id=%s username=%s method=%s status=%s view=%s path=%s ip=%s ua=%s exception=%s",
            kind,
            user.pk,
            user.get_username(),
            method,
            status_code,
            view_name,
            path[:500],
            ip,
            user_agent,
            exception.__class__.__name__ if exception else "",
        )

    def get_action_kind(self, request):
        method = request.method or ""
        path = request.path or ""

        if method in ("POST", "PUT", "PATCH", "DELETE"):
            return "mutation"

        if method == "GET":
            for part in IMPORTANT_STAFF_GET_PARTS:
                if part in path:
                    return "important_get"

            return "common_get"

        return "other"

    def is_ignored_path(self, path):
        if path in STAFF_AUDIT_IGNORED_EXACT_PATHS:
            return True

        return any(path.startswith(prefix) for prefix in STAFF_AUDIT_IGNORED_PATH_PREFIXES)

    def get_client_ip(self, request):
        x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
        if x_forwarded_for:
            return x_forwarded_for.split(",")[0].strip()

        x_real_ip = request.META.get("HTTP_X_REAL_IP")
        if x_real_ip:
            return x_real_ip.strip()

        return request.META.get("REMOTE_ADDR", "")