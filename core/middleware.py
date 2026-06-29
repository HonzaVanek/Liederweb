import hashlib
import logging
from django.core.cache import cache

from django.conf import settings
from django.db import IntegrityError
from django.db.models import F
from django.utils import timezone
from django.urls import resolve


from .models import DailySiteVisitor, DailyPageVisitor, DailySiteTraffic, DailyPageTraffic

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
    "internetmeasurement",
    "internet-measurement",

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

BOT_REFERER_PARTS = (
    "aisearchindex.space",
)

BOT_EXACT_PATHS = (
    "/robots.txt",
    "/sitemap.xml",
    "/meta.json",
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

    def is_scanner_path(self, path):
        path = path or ""

        path_lower = path.lower()
        if path_lower in BOT_EXACT_PATHS:
            return True

        if (
            path_lower == "/.env"
            or path_lower.endswith("/.env")
            or "phpinfo" in path_lower
            or path_lower in (
                "/info.php",
                "/php.php",
                "/i.php",
                "/pi.php",
                "/pinfo.php",
                "/test.php",
                "/debug.php",
                "/p.php",
            )
            or path_lower.startswith("/_profiler")
            or path_lower == "/_environment"
            or path_lower == "/.well-known/ucp"
        ):
            return True

        scanner_prefixes = (
            "/wp-admin/",
            "/wp-content/",
            "/wp-includes/",
            "/wordpress/",
            "/.git/",
            "/.env",
            "/vendor/",
            "/cgi-bin/",

            # Joomla / obecné CMS skeny
            "/administrator/",
            "/plugins/",
            "/components/",
            "/modules/",
            "/templates/",

            # obecné skeny na upload/file adresáře
            "/images/",
            "/files/",
            "/uploads/",
            "/sites/default/",
        )

        scanner_exact = (
            "/xmlrpc.php",
            "/wp-login.php",
        )

        if path_lower in scanner_exact:
            return True
        
        if "/wp-includes/" in path_lower:
            return True

        if path_lower.endswith("wlwmanifest.xml"):
            return True
        
        if ("/.env" in path_lower or path_lower.endswith("sftp-config.json") or "/.vscode/" in path_lower):
            return True

        return any(path_lower.startswith(prefix) for prefix in scanner_prefixes)


    def track_visit(self, request, response):
        path = request.path or ""

        if request.method not in ("GET", "POST", "HEAD"):
            return

        if self.is_hard_ignored_path(path):
            return

        user = getattr(request, "user", None)

        # Staff nechci ani v technické zátěži veřejného webu.
        # Staff audit řešíme zvlášť.
        if user and user.is_authenticated and user.is_staff:
            return

        user_agent = request.META.get("HTTP_USER_AGENT", "")[:500]
        has_user_agent = bool(user_agent.strip())

        ip = self.get_client_ip(request)
        if not ip:
            return

        referer = self.clean_referer(request.META.get("HTTP_REFERER", ""))[:300]
        today = timezone.localdate()
        status_code = response.status_code

        is_known_bot = (
            self.is_scanner_path(path)
            or request.method == "HEAD"
            or not has_user_agent
            or self.is_probably_bot(user_agent)
            or self.is_probably_bot_referer(referer)
        )

        raw_client_id = f"{today}|{ip}|{settings.SECRET_KEY}"
        client_hash = hashlib.sha256(raw_client_id.encode("utf-8")).hexdigest()
        client_label = client_hash[:8]

        raw_visitor_id = f"{today}|{ip}|{user_agent}|{settings.SECRET_KEY}"
        visitor_hash = hashlib.sha256(raw_visitor_id.encode("utf-8")).hexdigest()
        visitor_label = visitor_hash[:8]

        is_bot_like = False

        if not is_known_bot:
            is_bot_like = self.is_suspicious_rapid_visitor(client_label, path)

        is_bot_for_traffic = is_known_bot or is_bot_like

        # Technická zátěž:
        # počítáme i 404/403/500, protože to je reálná práce serveru.
        self.record_page_traffic(
            today,
            path,
            status_code=status_code,
            is_bot=is_bot_for_traffic,
        )

        if is_bot_like:
            return

        if is_known_bot:
            return

        # Odteď dál řešíme už jen úspěšnou lidskou návštěvnost existujících HTML stránek.
        # 404/403/500 už byly započítány výše do DailyPageTraffic jako technická zátěž.
        if status_code != 200:
            return
        # Skenovací/admin/static/media cesty nechceme počítat jako lidské pageviews.
        if self.is_ignored_path(path):
            return

        content_type = response.headers.get("Content-Type", "")
        if content_type and "text/html" not in content_type:
            return

        purpose = (
            request.headers.get("Purpose", "")
            or request.headers.get("Sec-Purpose", "")
        ).lower()
        if "prefetch" in purpose or "prerender" in purpose:
            return

        fetch_dest = request.headers.get("Sec-Fetch-Dest", "").lower()
        if fetch_dest and fetch_dest not in ("document", "iframe", "nested-document"):
            return

        logger.info(
            "VISIT ip=%s client=%s visitor=%s method=%s status=%s path=%s referer=%s ua=%s",
            ip,
            client_label,
            visitor_label,
            request.method,
            status_code,
            path[:300],
            referer,
            user_agent[:300],
        )

        # Detailní návštěvnost lidí počítáme jen pro GET.
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
    
    def is_hard_ignored_path(self, path):
        """
        Tohle ignorujeme úplně i pro technickou zátěž.
        Static/media/favicon by zbytečně nafukovaly statistiku.
        """
        if path in (
            "/favicon.ico",
            "/favicon.png",
            "/apple-touch-icon.png",
            "/apple-touch-icon-precomposed.png",
        ):
            return True

        return any(
            path.startswith(prefix)
            for prefix in (
                "/static/",
                "/media/",
            )
        )

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
    
    def is_probably_bot_referer(self, referer):
        referer_lower = (referer or "").lower()
        return any(part in referer_lower for part in BOT_REFERER_PARTS)
    
    def normalize_traffic_path(self, path, status_code):
        """
        Pro existující stránky necháme reálnou URL.
        Pro známý skenovací bordel seskupíme cesty, aby DB nebobtnala.
        """
        path = path or ""

        path_lower = path.lower()

        if path_lower == "/.env" or path_lower.endswith("/.env"):
            return "/__scan__/.env"

        if (
            "phpinfo" in path_lower
            or path_lower in (
                "/info.php",
                "/php.php",
                "/i.php",
                "/pi.php",
                "/pinfo.php",
                "/test.php",
                "/debug.php",
                "/p.php",
            )
        ):
            return "/__scan__/phpinfo"

        if path_lower.startswith("/_profiler") or path_lower == "/_environment":
            return "/__scan__/debug-env"

        if path_lower == "/.well-known/ucp":
            return "/__scan__/.well-known"
        
        if "/wp-includes/" in path_lower or path_lower.endswith("wlwmanifest.xml"):
            return "/__scan__/wp-includes/wlwmanifest.xml"
        
        if "/.env" in path_lower:
            return "/__scan__/.env"

        if path_lower.endswith("sftp-config.json") or "/.vscode/" in path_lower:
            return "/__scan__/dev-config"

        scanner_prefixes = (
            "/wp-admin/",
            "/wp-content/",
            "/wp-includes/",
            "/wordpress/",
            "/.git/",
            "/.env",
            "/vendor/",
            "/cgi-bin/",

            # Joomla / obecné CMS skeny
            "/administrator/",
            "/plugins/",
            "/components/",
            "/modules/",
            "/templates/",

            # obecné skeny na upload/file adresáře
            "/images/",
            "/files/",
            "/uploads/",
            "/sites/default/",
        )

        scanner_exact = (
            "/xmlrpc.php",
            "/wp-login.php",
        )

        if path_lower in scanner_exact:
            return f"/__scan__{path_lower}"

        for prefix in scanner_prefixes:
            if path_lower.startswith(prefix):
                return f"/__scan__{prefix}"

        # U běžných 404 chceme vidět konkrétní cestu.
        # To pomůže odhalit rozbité odkazy.
        return path[:500]
    
    def get_status_bucket(self, status_code):
        if 200 <= status_code < 300:
            return "ok"

        if 300 <= status_code < 400:
            return "redirect"

        if status_code == 404:
            return "not_found"

        if 500 <= status_code < 600:
            return "error"

        return "other"
    
    def record_page_traffic(self, day, path, status_code, is_bot):
        page_path = self.normalize_traffic_path(path, status_code)
        now = timezone.now()
        status_bucket = self.get_status_bucket(status_code)

        try:
            site_traffic, _created = DailySiteTraffic.objects.get_or_create(
                day=day,
                defaults={
                    "total_hits": 0,
                    "human_hits": 0,
                    "bot_hits": 0,
                },
            )
        except IntegrityError:
            site_traffic = DailySiteTraffic.objects.get(day=day)

        site_update = {
            "total_hits": F("total_hits") + 1,
            "last_seen_at": now,
        }

        if is_bot:
            site_update["bot_hits"] = F("bot_hits") + 1
        else:
            site_update["human_hits"] = F("human_hits") + 1

        DailySiteTraffic.objects.filter(pk=site_traffic.pk).update(**site_update)

        try:
            page_traffic, _created = DailyPageTraffic.objects.get_or_create(
                day=day,
                path=page_path,
                defaults={
                    "total_hits": 0,
                    "human_hits": 0,
                    "bot_hits": 0,
                },
            )
        except IntegrityError:
            page_traffic = DailyPageTraffic.objects.get(
                day=day,
                path=page_path,
            )

        page_update = {
            "total_hits": F("total_hits") + 1,
            "last_seen_at": now,
        }

        if is_bot:
            page_update["bot_hits"] = F("bot_hits") + 1
        else:
            page_update["human_hits"] = F("human_hits") + 1

        # Pokud tyhle sloupce v modelu máš:
        if status_bucket == "ok":
            page_update["ok_hits"] = F("ok_hits") + 1
        elif status_bucket == "redirect":
            page_update["redirect_hits"] = F("redirect_hits") + 1
        elif status_bucket == "not_found":
            page_update["not_found_hits"] = F("not_found_hits") + 1
        elif status_bucket == "error":
            page_update["error_hits"] = F("error_hits") + 1

        DailyPageTraffic.objects.filter(pk=page_traffic.pk).update(**page_update)


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