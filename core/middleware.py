import hashlib
import logging
import re
from django.core.cache import cache

from django.conf import settings
from django.db import IntegrityError
from django.db.models import F, Sum
from django.utils import timezone
from django.urls import resolve


from .models import DailySiteVisitor, DailyPageVisitor, DailySiteTraffic, DailyPageTraffic, DailyEngagedVisitor

from urllib.parse import urlsplit, urlunsplit


IGNORED_EXACT_PATHS = (
    "/admin",
    "/favicon.ico",
    "/favicon.png",
    "/apple-touch-icon.png",
    "/apple-touch-icon-precomposed.png",
    "/robots.txt",
    "/login/",
    "/password-reset/",
    "/registrace/",
)

IGNORED_PATH_PREFIXES = (
    "/admin/",
    "/static/",
    "/media/",
    "/rozesilac/",

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
    "claude-user",
    "anthropic",

    # social previeweři
    "facebookexternalhit",
    "facebot",
    "twitterbot",
    "linkedinbot",
    "slackbot",
    "discordbot",
    "telegrambot",
    "whatsapp",

    #nejspíš když se zadá reklama na fb, tak tam naběhnou crawler, který si stáhne stránku a udělá screenshot:
    "meta-externalads",
    "meta-externalagent",
    "meta-webindexer",
    "facebookexternalhit",
    "facebot",
    "developers.facebook.com/docs/sharing/webmasters/crawler",

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
    "jetpack",
    "wordpress.com",
    "commoncrawl",
    "forestengine",
    "cms scanner",
    "wordpress cms scanner",
    "wpscan",
    "cms-security-auditor",
    "security-auditor",
    "tlm-audit-scanner",
    "censysinspect",
    "censys",
    "shodan",
    "zgrab",
    "zgrabber",
    "nuclei",
    "vuln_scanner",
    "cve-",
    "marketsizer",
    "domainhealth",
    "audit-helper",
    "lead-audit",
    "developers.cloudflare.com/security-center",
    "cloudflare-security",
    "wp-safe-scanner",
    "safe-scanner",
    "kaupr",
)

BOT_REFERER_PARTS = (
    "aisearchindex.space",
    "dataindex.pro",
    "readlife.net",
)

BOT_EXACT_PATHS = (
    "/robots.txt",
    "/sitemap.xml",
    "/meta.json",
)

OBVIOUS_SCANNER_UA_PARTS = (
    "wp2shell",
    "wp2shell-check",
    "cms-checker",
    "scrapy",
    "agency/",
    "mozlila/",
    "bulid/",
    "moblie",
    "ct-wp-probe",
    "palo alto networks",
    "cortex-xpanse",
)

OBVIOUS_SCANNER_PATH_PARTS = (
    "wp-admin",
    "wp-login",
    "wp-content",
    "wp-includes",
    "xmlrpc.php",
    "install.php",
    ".php",
    ".env",
    ".git",
    "sftp-config.json",
    "/.vscode/",
    "sftp.json",
)

OBVIOUS_SCANNER_OWN_REFERER_PATH_PARTS = (
    "/.env",
    "/.git/",
    "/wp-admin/",
    "/wp-login.php",
    "/xmlrpc.php",
    "/install.php",
    "/wp-json/",
    "/gravitysmtp/",
    "/_ignition/",
    "/_debugbar/",
    "/telescope",
    "/geoserver/",
    "/users/sign_in",
    "/login/index.php",
    "/wp-includes/",
    "/wp-content/",
    "/media/system/",
    "/media/system/js/",
    "/administrator/",
    "/plugins/",
    "/components/",
    "/modules/",
    "/templates/",
)

SCANNER_EXACT_PATHS = (
    "/manifest.json",
    "/dist/manifest.json",
    "/assets/manifest.json",
    "/asset-manifest.json",
    "/graphql",
    "/api/graphql",
    "/v1/graphql",
    "/workspace",
    "/user/login",
    "/settings",
    "/auth/login",
    "/signin",
    "/login",
    "/account",
    "/portal",
    "/admin",
    "/admin/",
    "/admin/login",
    "/admin/login/",
    "/manage",
    "/console",
    "/dashboard",
    "/app",
    "/profile",
    "/my",
    "/readme.html",
    "/feed/",
    "/feed/atom/",
    "/webpack-stats.json",
    "/ip",
    "/llms.txt",
    "/ads.txt",
    "/.well-known/ai-plugin.json",
    "/.well-known/gpc.json",
    "/news_sitemap.xml",
    "/news-sitemap.xml",
    "/ds_store",
    "/.ds_store",
    "/api/v1/secrets",
    "/_ignition/execute-solution",
    "/secrets.json",
    "/config.yaml",
    "/.cursor/mcp.json",
    "/.continue/config.json",
    "/.env.production",
    "/.env.production.local",
)

OWN_REFERER_DOMAINS = (
    "lieder-society.cz",
    "liedersociety.cz",
    "liedersociety.website",
)

SUSPICIOUS_OWN_REFERER_HOSTS = (
    "m.liedersociety.cz",
    "m.lieder-society.cz",
)

ALLOWED_OWN_REFERER_SUBDOMAIN_LABELS = (
    "www",
)

SEARCH_REFERER_PARTS = (
    "google.",
    "seznam.",
    "bing.",
    "duckduckgo.",
    "yahoo.",
    "ecosia.",
    "startpage.",
    "search.brave.",
)

CLIENT_LEVEL_CLEANUP_REASONS = (
    "rapid_identity_switch",
    "homepage_identity_switch",
    "ua_rotation",
    "rapid_navigation",
    "known_scanner",
    "meta_infrastructure_ip",
    "scanner_request",
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


        if len(hits) >= 3 and unique_paths == {"/"}:
            return True

        if len(hits) >= 5:
            return True

        if len(hits) >= 3 and len(unique_paths) >= 3:
            return True

        return False

    def is_suspicious_homepage_identity_switch(self, client_label, path, referer_raw, user_agent):
        if path != "/":
            return False

        now_ts = int(timezone.now().timestamp())
        ua = (user_agent or "").strip().lower()
        host = self.get_referer_host(referer_raw)

        cache_key = f"traffic_homepage_identity:{client_label}"
        hits = cache.get(cache_key, [])

        hits = [
            hit for hit in hits
            if now_ts - hit["ts"] <= 90
        ]

        hits.append({
            "ts": now_ts,
            "ua": ua,
            "host": host,
        })

        cache.set(cache_key, hits, timeout=120)

        unique_uas = {hit["ua"] for hit in hits if hit["ua"]}
        unique_hosts = {hit["host"] for hit in hits if hit["host"]}

        if len(hits) >= 3 and len(unique_uas) >= 2 and len(unique_hosts) >= 2:
            return True

        return False

    def is_suspicious_ua_rotating_client(self, client_label, user_agent):
        now_ts = int(timezone.now().timestamp())
        ua = (user_agent or "").strip().lower()

        if not ua:
            return False

        cache_key = f"traffic_client_uas:{client_label}"
        hits = cache.get(cache_key, [])

        hits = [
            hit for hit in hits
            if now_ts - hit["ts"] <= 5 * 60
        ]

        hits.append({
            "ts": now_ts,
            "ua": ua,
        })

        cache.set(cache_key, hits, timeout=10 * 60)

        unique_uas = {hit["ua"] for hit in hits}

        return len(unique_uas) >= 5

    def is_obvious_scanner(self, path, referer, user_agent):
        path_lower = (path or "").lower()
        ua_lower = (user_agent or "").strip().lower()

        # User-Agent nemá být URL.
        # Typicky: ua=http://liedersociety.cz/wp-admin/install.php?step=1
        if ua_lower.startswith("http://") or ua_lower.startswith("https://"):
            return True

        # Jasně podezřelé User-Agenty.
        if any(part in ua_lower for part in OBVIOUS_SCANNER_UA_PARTS):
            return True

        # Jasně skenovací path.
        if any(part in path_lower for part in OBVIOUS_SCANNER_PATH_PARTS):
            return True

        # Referer kontrolujeme opatrněji:
        # vadí nám hlavně fake referer na citlivou URL NAŠÍ domény.
        referer_host = self.get_referer_host(referer)

        if self.is_own_referer_host(referer_host):
            referer_lower = (referer or "").lower()

            if self.is_disallowed_own_referer_subdomain(referer_host):
                return True

            if any(part in referer_lower for part in OBVIOUS_SCANNER_OWN_REFERER_PATH_PARTS):
                return True

        return False

    def is_suspicious_shared_user_agent(self, path, referer_raw, user_agent, client_label):
        ua = (user_agent or "").strip().lower()

        if not ua:
            return False, ""

        host = self.get_referer_host(referer_raw)

        if self.is_search_referer_host(host):
            return False, ""

        ua_client_count = self.remember_user_agent_client(user_agent, client_label)

        is_social_iab = self.is_social_or_in_app_ua(user_agent)
        is_mobile_browser = self.is_common_mobile_browser_ua(user_agent)

        # Facebook/Instagram in-app browser po reklamě:
        # neřešit přes shared_ua, ale přes Meta IP, scanner pathy, rapid behavior a beacon matching.
        if is_social_iab:
            return False, ""

        # Desktop / generic bez refereru: pořád přísné.
        empty_ref_shared_ua_client_threshold = 3
        general_shared_ua_client_threshold = 8

        # Mobilní browsery mají častěji stejné UA, tak mírně povolit,
        # ale ne úplně absurdně vysoko.
        if is_mobile_browser:
            empty_ref_shared_ua_client_threshold = 8
            general_shared_ua_client_threshold = 15

        if not host and ua_client_count >= empty_ref_shared_ua_client_threshold:
            return True, f"same_ua_empty_ref_clients:{ua_client_count}"

        if self.is_own_referer_host(host) and ua_client_count >= general_shared_ua_client_threshold:
            return True, f"same_ua_many_clients:{ua_client_count}"

        return False, ""


    def is_suspicious_rapid_identity_switch(self, client_label, visitor_label, path, referer_raw, user_agent):
        now_ts = int(timezone.now().timestamp())
        ua = (user_agent or "").strip().lower()
        host = self.get_referer_host(referer_raw)

        cache_key = f"traffic_identity_switch:{client_label}"
        hits = cache.get(cache_key, [])

        hits = [
            hit for hit in hits
            if now_ts - hit["ts"] <= 3
        ]

        hits.append({
            "ts": now_ts,
            "ua": ua,
            "path": path or "",
            "host": host,
            "visitor": visitor_label,
        })

        cache.set(cache_key, hits, timeout=30)

        unique_paths = {hit["path"] for hit in hits}
        unique_uas = {hit["ua"] for hit in hits if hit["ua"]}
        unique_hosts = {hit["host"] for hit in hits if hit["host"]}
        unique_visitors = {
            hit["visitor"]
            for hit in hits
            if hit.get("visitor")
        }

        has_search_referer = any(
            self.is_search_referer_host(hit["host"])
            for hit in hits
            if hit.get("host")
        )

        # Velmi podezřelé: stejný client během pár sekund otevře homepage
        # jako dva různí návštěvníci / prohlížeče bez vyhledávače.
        if (
            len(hits) >= 2
            and unique_paths == {"/"}
            and len(unique_uas) >= 2
            and len(unique_visitors) >= 2
            and not has_search_referer
        ):
            return True

        # Původní širší pravidlo pro tři rychlé homepage identity.
        if len(hits) >= 3 and unique_paths == {"/"}:
            if len(unique_uas) >= 2:
                return True

            if len(unique_hosts) >= 2:
                return True

        return False

    def is_meta_infrastructure_ip(self, ip):
        ip = (ip or "").lower()
        return ip.startswith("2a03:2880:")

    def is_social_or_in_app_ua(self, user_agent):
        ua = (user_agent or "").lower()
        return any(part in ua for part in (
            "fb_iab/",
            "fban/",
            "fbav/",
            "instagram ",
            "instagram/",
            "iabmv/1",
        ))


    def is_common_mobile_browser_ua(self, user_agent):
        ua = (user_agent or "").lower()

        if "mobile safari" not in ua:
            return False

        return (
            "android" in ua
            or "iphone" in ua
            or "samsungbrowser" in ua
        )    

    def get_referer_host(self, referer):
        referer = (referer or "").strip()

        if not referer:
            return ""

        # Někteří boti posílají referer bez schématu:
        # www.google.com místo https://www.google.com/
        if "://" not in referer:
            referer = "http://" + referer

        try:
            return urlsplit(referer).netloc.lower().split(":")[0].rstrip(".")
        except Exception:
            return ""


    def is_own_referer_host(self, host):
        host = (host or "").lower()

        return any(
            host == domain or host.endswith("." + domain)
            for domain in OWN_REFERER_DOMAINS
        )

    def get_own_referer_subdomain_label(self, host):
        host = (host or "").lower()

        for domain in OWN_REFERER_DOMAINS:
            suffix = "." + domain

            if host.endswith(suffix):
                subdomain = host[:-len(suffix)]

                if subdomain:
                    return subdomain

        return ""

    def is_disallowed_own_referer_subdomain(self, host):
        label = self.get_own_referer_subdomain_label(host)

        if not label:
            return False

        return label not in ALLOWED_OWN_REFERER_SUBDOMAIN_LABELS


    def is_search_referer_host(self, host):
        host = (host or "").lower()
        return any(part in host for part in SEARCH_REFERER_PARTS)


    def remember_user_agent_client(self, user_agent, client_label):
        """
        Vrací, z kolika různých clientů jsme dnes viděli
        úplně stejný User-Agent.
        """
        ua_key = hashlib.sha256(
            (user_agent or "").strip().lower().encode("utf-8")
        ).hexdigest()[:16]

        today = timezone.localdate().isoformat()
        cache_key = f"traffic_ua_clients:{today}:{ua_key}"

        clients = cache.get(cache_key, [])

        if client_label not in clients:
            clients.append(client_label)

        clients = clients[-300:]

        cache.set(cache_key, clients, timeout=60 * 60 * 26)

        return len(set(clients))


    def score_disguised_bot(self, path, referer_raw, user_agent, client_label):
        """
        Citlivé skórování maskovaných botů.

        Důležité:
        - týká se jen konkrétního masového vzorce iPhone OS 13_2_3,
        - samotný starý iPhone nestačí,
        - samotná homepage nestačí,
        - samotný vlastní referer nestačí,
        - landing/detail stránky mají projít.
        """
        score = 0
        reasons = []

        path = path or ""
        ua = (user_agent or "").strip().lower()
        host = self.get_referer_host(referer_raw)

        is_old_iphone_13 = (
            "iphone os 13_2_3" in ua
            and "safari/604.1" in ua
        )

        # Tohle je klíčové:
        # Pokud to není ten konkrétní podezřelý iPhone UA,
        # skórovací mechanismus se na request vůbec nepoužije.
        if not is_old_iphone_13:
            return 0, []

        is_homepage = path == "/"
        is_own_referer = self.is_own_referer_host(host)
        is_suspicious_own_referer = host in SUSPICIOUS_OWN_REFERER_HOSTS
        is_search_referer = self.is_search_referer_host(host)
        is_public_auth_path = path in ("/login/", "/registrace/", "/password-reset/")

        # Slabý signál. Sám o sobě nestačí.
        score += 1
        reasons.append("old_iphone_13_2_3")

        # Tenhle konkrétní masový vzorec.
        if is_homepage and is_own_referer:
            score += 4
            reasons.append("old_iphone_self_ref_homepage")

        # Další podezřelý vzorec:
        # starý iPhone UA leze na auth stránky bez refereru z vyhledávače.
        if is_public_auth_path and not is_search_referer:
            score += 5
            reasons.append("old_iphone_auth_path")

        # m.liedersociety.cz / m.lieder-society.cz,
        # pokud takovou mobilní subdoménu reálně nepoužíváte.
        if is_suspicious_own_referer:
            score += 2
            reasons.append("suspicious_mobile_subdomain_referer")

        # Stejný přesný UA z mnoha různých clientů za den.
        ua_client_count = self.remember_user_agent_client(user_agent, client_label)

        if ua_client_count >= 10:
            score += 3
            reasons.append(f"same_ua_many_clients:{ua_client_count}")
        elif ua_client_count >= 5:
            score += 1
            reasons.append(f"same_ua_some_clients:{ua_client_count}")

        # Google/Seznam/Bing/DuckDuckGo referer je dobrý signál.
        if is_search_referer:
            score -= 2
            reasons.append("search_referer")

        # Nechceme vyhazovat člověka, který otevře konkrétní stránku a odejde.
        if path != "/":
            score -= 1
            reasons.append("non_homepage")

        # Důležité veřejné stránky chráníme ještě víc.
        if (
            path.startswith("/agnes-tyrrell/")
            or path.startswith("/events/")
            or path.startswith("/lide/")
            or path.startswith("/objevujte/")
        ):
            score -= 1
            reasons.append("important_public_page")

        return max(score, 0), reasons

    def is_scanner_path(self, path):
        path = path or ""

        path_lower = path.lower()
        if path_lower in BOT_EXACT_PATHS:
            return True

        if path_lower == "/wp-json" or path_lower.startswith("/wp-json/") or path_lower.startswith("/wp-sitemap"):
            return True

        if path_lower in SCANNER_EXACT_PATHS:
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
        
        if ("/.env" in path_lower or path_lower.endswith("sftp-config.json") or path_lower.endswith("sftp.json") or "/.vscode/" in path_lower):
            return True

        return any(path_lower.startswith(prefix) for prefix in scanner_prefixes)


    def get_sticky_bot_like_reason(self, client_label):
        return cache.get(f"traffic_bot_like_client:{client_label}")


    def mark_sticky_bot_like_client(self, client_label, reason):
        cache.set(
            f"traffic_bot_like_client:{client_label}",
            reason or "bot_like",
            timeout=60 * 30,
        )


    def should_cleanup_client_human_stats(self, reason):
        reason = reason or ""

        if reason.startswith("sticky:"):
            reason = reason.removeprefix("sticky:")

        if reason.startswith("shared_ua:"):
            return True

        return reason in CLIENT_LEVEL_CLEANUP_REASONS

    def should_cleanup_visitor_human_stats(self, reason):
        reason = reason or ""

        if reason.startswith("shared_ua:"):
            return True

        if reason.startswith("sticky:shared_ua:"):
            return True

        return False


    def cleanup_client_human_stats(self, day, client_hash):
        page_rows = list(
            DailyPageVisitor.objects
            .filter(day=day, client_hash=client_hash)
            .values("path")
            .annotate(pageviews=Sum("pageviews"))
        )

        total_pageviews = sum(row["pageviews"] or 0 for row in page_rows)

        # Pokud se client později ukáže jako bot, nesmí zůstat
        # ani mezi potvrzenými / JS beacon návštěvníky.
        DailyEngagedVisitor.objects.filter(
            day=day,
            client_hash=client_hash,
        ).delete()

        if not total_pageviews:
            return 0

        DailyPageVisitor.objects.filter(
            day=day,
            client_hash=client_hash,
        ).delete()

        DailySiteVisitor.objects.filter(
            day=day,
            client_hash=client_hash,
        ).delete()

        # Překlasifikování technické zátěže: human -> bot.
        site_traffic = DailySiteTraffic.objects.filter(day=day).first()

        if site_traffic:
            site_traffic.human_hits = max(site_traffic.human_hits - total_pageviews, 0)
            site_traffic.bot_hits += total_pageviews
            site_traffic.save(update_fields=["human_hits", "bot_hits"])

        for row in page_rows:
            path = row["path"]
            count = row["pageviews"] or 0

            page_traffic = DailyPageTraffic.objects.filter(
                day=day,
                path=path,
            ).first()

            if page_traffic:
                page_traffic.human_hits = max(page_traffic.human_hits - count, 0)
                page_traffic.bot_hits += count
                page_traffic.save(update_fields=["human_hits", "bot_hits"])

        return total_pageviews

    def cleanup_visitor_human_stats(self, day, visitor_hash):
        page_rows = list(
            DailyPageVisitor.objects
            .filter(day=day, visitor_hash=visitor_hash)
            .values("path")
            .annotate(pageviews=Sum("pageviews"))
        )

        total_pageviews = sum(row["pageviews"] or 0 for row in page_rows)

        # Pokud se konkrétní visitor později ukáže jako bot,
        # smažeme ho i z potvrzených / JS beacon návštěv.
        DailyEngagedVisitor.objects.filter(
            day=day,
            visitor_hash=visitor_hash,
        ).delete()

        if not total_pageviews:
            return 0

        DailyPageVisitor.objects.filter(
            day=day,
            visitor_hash=visitor_hash,
        ).delete()

        DailySiteVisitor.objects.filter(
            day=day,
            visitor_hash=visitor_hash,
        ).delete()

        site_traffic = DailySiteTraffic.objects.filter(day=day).first()

        if site_traffic:
            site_traffic.human_hits = max(site_traffic.human_hits - total_pageviews, 0)
            site_traffic.bot_hits += total_pageviews
            site_traffic.save(update_fields=["human_hits", "bot_hits"])

        for row in page_rows:
            path = row["path"]
            count = row["pageviews"] or 0

            page_traffic = DailyPageTraffic.objects.filter(
                day=day,
                path=path,
            ).first()

            if page_traffic:
                page_traffic.human_hits = max(page_traffic.human_hits - count, 0)
                page_traffic.bot_hits += count
                page_traffic.save(update_fields=["human_hits", "bot_hits"])

        return total_pageviews

    def normalize_visitor_user_agent(self, user_agent):
        ua = (user_agent or "").strip()

        if not self.is_social_or_in_app_ua(ua):
            return ua

        # Facebook umí mezi requesty přidat/změnit FBNV.
        ua = re.sub(r"(?:\s+|;)FBNV/[^\s;\]]+", "", ua, flags=re.IGNORECASE)

        # Instagram/iOS mění např. NW/3 <-> NW/1.
        ua = re.sub(r"\s+NW/\d+\b", "", ua, flags=re.IGNORECASE)

        # Po odstranění tokenů sjednotit mezery.
        ua = re.sub(r"\s+", " ", ua).strip()

        return ua        

    def is_recent_social_page_duplicate(self, client_label, path, user_agent, referer_raw,):
        """
        Detekuje technický dvojrequest Facebook/Instagram in-app browseru.

        Za duplicitu považujeme pouze případ:
        - social / in-app UA,
        - stejný client,
        - stejná path,
        - do 10 sekund,
        - raw User-Agent se změnil,
        - po odstranění volatilních FB/IG tokenů je UA stejný,
        - referer host zůstává stejný.

        Normální reload se stejným UA tímto neodfiltrujeme.
        """
        if not self.is_social_or_in_app_ua(user_agent):
            return False

        raw_ua = (user_agent or "").strip()
        normalized_ua = self.normalize_visitor_user_agent(raw_ua)
        referer_host = self.get_referer_host(referer_raw)

        now_ts = timezone.now().timestamp()

        path_key = hashlib.sha256((path or "").encode("utf-8")).hexdigest()[:16]

        cache_key = (
            f"traffic_social_page:"
            f"{client_label}:"
            f"{path_key}"
        )

        previous = cache.get(cache_key)

        if previous:
            previous_ts = previous.get("ts", 0)
            age = now_ts - previous_ts

            is_recent = 0 <= age <= 10

            raw_ua_changed = (previous.get("raw_ua", "") != raw_ua)

            normalized_ua_same = (previous.get("normalized_ua", "") == normalized_ua)

            referer_host_same = (previous.get("referer_host", "") == referer_host)

            if (
                is_recent
                and raw_ua_changed
                and normalized_ua_same
                and referer_host_same
            ):
                # Duplicitu schválně NEukládáme jako nový základ,
                # aby se nám nevytvořil řetězec A -> B -> A.
                return True

        cache.set(
            cache_key,
            {
                "ts": now_ts,
                "raw_ua": raw_ua,
                "normalized_ua": normalized_ua,
                "referer_host": referer_host,
            },
            timeout=15,
        )

        return False


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
        referer_raw = request.META.get("HTTP_REFERER", "")

        has_user_agent = bool(user_agent.strip())

        ip = self.get_client_ip(request)
        if not ip:
            return

        referer = self.clean_referer(referer_raw)[:300]
        today = timezone.localdate()
        status_code = response.status_code
        is_scanner_request = (
            self.is_scanner_path(path)
            or self.is_obvious_scanner(path, referer_raw, user_agent)
        )



        known_bot_reason = ""

        is_known_bot = False

        if is_scanner_request:
            is_known_bot = True
            known_bot_reason = "scanner_request"
        elif request.method == "HEAD":
            is_known_bot = True
            known_bot_reason = "head_request"
        elif not has_user_agent:
            is_known_bot = True
            known_bot_reason = "no_user_agent"
        elif self.is_probably_bot(user_agent):
            is_known_bot = True
            known_bot_reason = "bot_user_agent"
        elif self.is_probably_bot_referer(referer):
            is_known_bot = True
            known_bot_reason = "bot_referer"

        if self.is_meta_infrastructure_ip(ip):
            is_known_bot = True
            known_bot_reason = "meta_infrastructure_ip"
        
        raw_client_id = f"{today}|{ip}|{settings.SECRET_KEY}"
        client_hash = hashlib.sha256(raw_client_id.encode("utf-8")).hexdigest()
        client_label = client_hash[:8]

        visitor_user_agent = self.normalize_visitor_user_agent(user_agent)

        raw_visitor_id = (f"{today}|{ip}|{visitor_user_agent}|{settings.SECRET_KEY}")
        visitor_hash = hashlib.sha256(raw_visitor_id.encode("utf-8")).hexdigest()
        visitor_label = visitor_hash[:8]

        is_bot_like = False
        bot_like_reason = ""
        should_mark_sticky_bot_like = False
        disguised_score = 0
        disguised_reasons = []

        if not is_known_bot:
            sticky_reason = self.get_sticky_bot_like_reason(client_label)

            if sticky_reason:
                is_bot_like = True
                bot_like_reason = "sticky:" + sticky_reason

        if not is_known_bot and not is_bot_like:
            if self.is_suspicious_rapid_identity_switch(
                client_label,
                visitor_label,
                path,
                referer_raw,
                user_agent,
            ):
                is_bot_like = True
                should_mark_sticky_bot_like = True
                bot_like_reason = "rapid_identity_switch"

        if not is_known_bot and not is_bot_like:
            if self.is_suspicious_homepage_identity_switch(
                client_label,
                path,
                referer_raw,
                user_agent,
            ):
                is_bot_like = True
                should_mark_sticky_bot_like = True
                bot_like_reason = "homepage_identity_switch"


        if not is_known_bot and not is_bot_like:
            if self.is_suspicious_ua_rotating_client(client_label, user_agent):
                is_bot_like = True
                should_mark_sticky_bot_like = True
                bot_like_reason = "ua_rotation"

        if not is_known_bot and not is_bot_like:
            disguised_score, disguised_reasons = self.score_disguised_bot(
                path,
                referer_raw,
                user_agent,
                client_label,
            )

            if disguised_score >= 5:
                is_bot_like = True
                should_mark_sticky_bot_like = True
                bot_like_reason = "disguised_iphone:" + ",".join(disguised_reasons)

        if not is_known_bot and not is_bot_like:
            is_shared_ua, shared_ua_reason = self.is_suspicious_shared_user_agent(
                path,
                referer_raw,
                user_agent,
                client_label,
            )

            if is_shared_ua:
                is_bot_like = True
                should_mark_sticky_bot_like = True
                bot_like_reason = "shared_ua:" + shared_ua_reason

        if not is_known_bot and not is_bot_like:
            if self.is_suspicious_rapid_visitor(client_label, path):
                is_bot_like = True
                should_mark_sticky_bot_like = True
                bot_like_reason = "rapid_navigation"

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
            if should_mark_sticky_bot_like:
                self.mark_sticky_bot_like_client(client_label, bot_like_reason)

            removed = 0

            if self.should_cleanup_client_human_stats(bot_like_reason):
                removed = self.cleanup_client_human_stats(today, client_hash)

            elif self.should_cleanup_visitor_human_stats(bot_like_reason):
                removed = self.cleanup_visitor_human_stats(today, visitor_hash)

            if removed:
                logger.info(
                    "CLEANUP client=%s visitor=%s reason=%s removed_pageviews=%s",
                    client_label,
                    visitor_label,
                    bot_like_reason,
                    removed,
                )

            logger.info(
                "BOT_LIKE client=%s visitor=%s method=%s status=%s path=%s referer=%s reason=%s score=%s ua=%s",
                client_label,
                visitor_label,
                request.method,
                status_code,
                path[:300],
                referer,
                bot_like_reason,
                disguised_score,
                user_agent[:300],
            )
            return

        if is_known_bot:
            if is_scanner_request or known_bot_reason == "meta_infrastructure_ip":
                removed = self.cleanup_client_human_stats(today, client_hash)

                self.mark_sticky_bot_like_client(client_label, known_bot_reason or "known_bot")

                if removed:
                    logger.info(
                        "CLEANUP client=%s visitor=%s reason=%s path=%s removed_pageviews=%s",
                        client_label,
                        visitor_label,
                        known_bot_reason or "known_bot",
                        path[:300],
                        removed,
                    )

            if known_bot_reason == "meta_infrastructure_ip":
                logger.info(
                    "BOT_LIKE client=%s visitor=%s method=%s status=%s path=%s referer=%s reason=%s score=%s ua=%s",
                    client_label,
                    visitor_label,
                    request.method,
                    status_code,
                    path[:300],
                    referer,
                    known_bot_reason,
                    0,
                    user_agent[:300],
                )

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

        if request.method == "GET":
            is_social_duplicate = self.is_recent_social_page_duplicate(
                client_label=client_label,
                path=path,
                user_agent=user_agent,
                referer_raw=referer_raw,
            )

            if is_social_duplicate:
                logger.info(
                    "VISIT_DUPLICATE ip=%s client=%s visitor=%s method=%s status=%s path=%s referer=%s reason=social_ua_variant ua=%s",
                    ip,
                    client_label,
                    visitor_label,
                    request.method,
                    status_code,
                    path[:300],
                    referer,
                    user_agent[:300],
                )
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

        cache.set(
            f"traffic_visit_source:{today}:{client_hash}:{path[:500]}",
            {
                "referer": referer,
                "visitor": visitor_label,
            },
            timeout=30 * 60,
        )

        # Detailní návštěvnost lidí počítáme jen pro GET.
        if request.method != "GET":
            return

        defaults = {
            "pageviews": 0,
            "client_hash": client_hash,
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
            client_hash=client_hash,
            last_seen_at=timezone.now(),
            last_path=path[:500],
        )

        page_path = path[:500]

        page_defaults = {
            "pageviews": 0,
            "client_hash": client_hash,
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
            client_hash=client_hash,
            last_seen_at=timezone.now(),
        )

    def is_ignored_path(self, path):
        if path in IGNORED_EXACT_PATHS:
            return True

        return any(path.startswith(prefix) for prefix in IGNORED_PATH_PREFIXES)
    
    def is_hard_ignored_path(self, path):
        """
        Tohle ignorujeme úplně i pro technickou zátěž veřejného webu.
        Admin/staff/login/static/media/beacon by zbytečně nafukovaly statistiku.
        """
        if path in (
            "/admin",
            "/traffic/engaged/",
            "/login/",
            "/password-reset/",
            "/registrace/",
            "/favicon.ico",
            "/favicon.png",
            "/apple-touch-icon.png",
            "/apple-touch-icon-precomposed.png",
        ):
            return True

        return any(
            path.startswith(prefix)
            for prefix in (
                "/admin/",
                "/rozesilac/",
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

        if path_lower.startswith("/wp-sitemap") or path_lower in (
            "/readme.html",
            "/feed/",
            "/feed/atom/",
        ):
            return "/__scan__/wp-meta"

        if path_lower == "/webpack-stats.json":
            return "/__scan__/dev-config"
        
        if "/wp-includes/" in path_lower or path_lower.endswith("wlwmanifest.xml"):
            return "/__scan__/wp-includes/wlwmanifest.xml"
        
        if "/.env" in path_lower:
            return "/__scan__/.env"

        if path_lower.endswith("sftp-config.json") or path_lower.endswith("sftp.json") or "/.vscode/" in path_lower:
            return "/__scan__/dev-config"

        if path_lower == "/wp-json" or path_lower.startswith("/wp-json/"):
            return "/__scan__/wp-json"

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

        if path_lower in (
            "/manifest.json",
            "/dist/manifest.json",
            "/assets/manifest.json",
            "/asset-manifest.json",
        ):
            return "/__scan__/manifest"

        if path_lower in ("/graphql", "/api/graphql", "/v1/graphql"):
            return "/__scan__/graphql"

        if path_lower in SCANNER_EXACT_PATHS:
            return f"/__scan__{path_lower}"

        if path_lower in (
            "/meta.json",
            "/news_sitemap.xml",
            "/news-sitemap.xml",
        ):
            return "/__scan__/meta"

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