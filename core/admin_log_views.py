from pathlib import Path
import subprocess
import re
from urllib.parse import urlparse
from datetime import datetime
from collections import Counter, defaultdict

from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpResponseForbidden
from django.shortcuts import render
from django.db.models import Count, Sum

from core.models import DailySiteVisitor, DailyPageVisitor, DailySiteTraffic, DailyPageTraffic, DailyEngagedVisitor, DailyBrowserVisitor, DailyEngagedPageVisitor


LOG_FILES = {
    "traffic": Path("/srv/log/traffic.log"),
    "staff_audit": Path("/srv/log/staff_audit.log"),
    "python": Path("/srv/log/python.log"),
    "python.old": Path("/srv/log/python.log.1"),
    "nginx": Path("/srv/log/nginx.log"),
    "cron": Path("/srv/log/cron.log"),
    "security": Path("/srv/log/security.log"),
    "supervisord": Path("/srv/log/supervisord.log"),
}

DEFAULT_LINES = 100
MAX_LINES = 10000

# Pro barevné rozlišení traffic logu.
IP_RE = re.compile(r"\bip=([0-9a-fA-F:.]+)")
CLIENT_RE = re.compile(r"\bclient=([a-f0-9]{8})")
VISITOR_RE = re.compile(r"\bvisitor=([a-f0-9]{8})")

TRAFFIC_KIND_RE = re.compile(
    r"\|\s+liederweb\.traffic\s+\|\s+"
    r"(META_EXIT_DIAG|SOCIAL_DUP_PAIR|"
    r"NETWORK_PATTERN_CANDIDATE|"
    r"RAPID_IDENTITY_CANDIDATE|POSTHOC_CLEANUP|"
    r"VISIT_DUPLICATE|BROWSER_CONFIRMED|BROWSER_SKIP|"
    r"ENGAGED_SKIP|ENGAGED|VISIT|BOT_LIKE|CLEANUP)\s+"
)

TRAFFIC_TS_RE = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})")

TRAFFIC_FIELD_PATTERNS = {
    "ip": re.compile(r"\bip=([^\s]+)"),
    "client": re.compile(r"\bclient=([a-f0-9]{8})"),
    "visitor": re.compile(r"\bvisitor=([a-f0-9]{8})"),
    "method": re.compile(r"\bmethod=([A-Z]+)"),
    "status": re.compile(r"\bstatus=(\d{3})"),
    "path": re.compile(r"\bpath=([^\s]*)"),
    "referer": re.compile(r"\breferer=([^\s]*)"),
    "source_referer": re.compile(r"\bsource_referer=([^\s]*)"),
    "reason": re.compile(r"\breason=([^\s]*)"),
    "score": re.compile(r"\bscore=([^\s]*)"),
    "trigger": re.compile(r"\btrigger=([^\s]*)"),
    "source": re.compile(r"\bsource=([^\s]+)"),
    "elapsed_ms": re.compile(r"\belapsed_ms=(\d+)"),
    "total_visible_ms": re.compile(r"\btotal_visible_ms=(\d+)"),
    "max_visible_span_ms": re.compile(r"\bmax_visible_span_ms=(\d+)"),
    "visibility_changes": re.compile(r"\bvisibility_changes=(\d+)"),
    "visible_intervals": re.compile(r"\bvisible_intervals=(\d+)"),
    "browser_sent": re.compile(r"\bbrowser_sent=([01])"),
    "engaged_sent": re.compile(r"\bengaged_sent=([01])"),
    "had_pointer": re.compile(r"\bhad_pointer=([01])"),
    "had_touch": re.compile(r"\bhad_touch=([01])"),
    "had_scroll": re.compile(r"\bhad_scroll=([01])"),
    "had_key": re.compile(r"\bhad_key=([01])"),
    "max_scroll_pct": re.compile(r"\bmax_scroll_pct=(\d+)"),
    "prerendered": re.compile(r"\bprerendered=([01])"),
    "removed_pageviews": re.compile(r"\bremoved_pageviews=(\d+)"),
    "candidates": re.compile(r"\bcandidates=(\d+)"),
    "fetch_user": re.compile(r"\bfetch_user=([^\s]*)"),
    "fetch_mode": re.compile(r"\bfetch_mode=([^\s]*)"),
    "fetch_dest": re.compile(r"\bfetch_dest=([^\s]*)"),
    "fetch_site": re.compile(r"\bfetch_site=([^\s]*)"),
    "purpose": re.compile(r"\bpurpose=([^\s]*)"),
    "span": re.compile(r"\bspan=([0-9.]+)"),
    "hits": re.compile(r"\bhits=(\d+)"),
    "paths": re.compile(r"\bpaths=(\d+)"),
    "visitors": re.compile(r"\bvisitors=(\d+)"),
    "uas": re.compile(r"\buas=(\d+)"),
    "details": re.compile(r"\bdetails=(.*)$"),
    "network": re.compile(r"\bnetwork=([^\s]+)"),
    "clients": re.compile(r"\bclients=(\d+)"),
    "ips": re.compile(r"\bips=(\d+)"),
    "span_seconds": re.compile(r"\bspan_seconds=(\d+)"),
    "sample_paths": re.compile(r"\bsample_paths=(.*)$"),
    "source_visitor": re.compile(r"\bsource_visitor=([a-f0-9]{8})"),
    "beacon_visitor": re.compile(r"\bbeacon_visitor=([a-f0-9]{8})"),
    "doc": re.compile(r"\bdoc=([^\s]+)"),
    "initial_visibility": re.compile(r"\binitial_visibility=([^\s]+)"),
    "final_visibility": re.compile(r"\bfinal_visibility=([^\s]+)"),
    "initial_focus": re.compile(r"\binitial_focus=([01])"),
    "final_focus": re.compile(r"\bfinal_focus=([01])"),
    "navigation_type": re.compile(r"\bnavigation_type=([^\s]+)"),
    "exit_trigger": re.compile(r"\bexit_trigger=([^\s]+)"),
    "pagehide_persisted": re.compile(r"\bpagehide_persisted=([01])"),
    "document_referrer": re.compile(r"\bdocument_referrer=([^\s]*)"),
    "document_ua": re.compile(r"\bdocument_ua=(.*?)\s+ua="),

    # SOCIAL_DUP_PAIR
    "age_ms": re.compile(r"\bage_ms=(\d+)"),
    "previous_visitor": re.compile(r"\bprevious_visitor=([a-f0-9]{8})"),
    "current_visitor": re.compile(r"\bcurrent_visitor=([a-f0-9]{8})"),
    "referer_host": re.compile(r"\breferer_host=([^\s]*)"),
    "previous_ua": re.compile(r"\bprevious_ua=(.*?)\s+current_ua="),
    "current_ua": re.compile(r"\bcurrent_ua=(.*)$"),
}

UA_RE = re.compile(r"\bua=(.*)$")

# Pravidelný healthcheck / monitoring přes python-requests.
HEALTHCHECK_RE = re.compile(
    r'"GET / HTTP/1\.0" 200 \d+ "-" "python-requests/[^"]+"'
)


IP_LABELS = {
    "185.68.212.2": "ČTÚ",
    "212.20.115.101": "Trachta",
    "213.235.82.162": "Monike",
    "90.183.235.234": "Eva z ÚPV",
}

def filter_noise_log_lines(log_text, max_lines):
    hidden_count = 0
    kept_lines = []

    for line in log_text.splitlines():
        if HEALTHCHECK_RE.search(line):
            hidden_count += 1
            continue

        kept_lines.append(line)

    kept_lines = kept_lines[-max_lines:]

    return "\n".join(kept_lines), hidden_count


def build_colored_log_lines(log_text):
    colored_log_lines = []

    previous_key = None
    previous_color_index = None

    # V rámci jednoho zobrazení logu držíme stejnému klientovi/IP stejnou barvu.
    assigned_colors = {}

    for line in log_text.splitlines():
        ip_match = IP_RE.search(line)
        client_match = CLIENT_RE.search(line)
        visitor_match = VISITOR_RE.search(line)

        ip = None
        ip_label = None
        client = None
        visitor = None
        color_index = None

        if ip_match:
            ip = ip_match.group(1)
        
        if ip:
            ip_label = IP_LABELS.get(ip)

        if client_match:
            client = client_match.group(1)

        if visitor_match:
            visitor = visitor_match.group(1)

        # Pro identitu řádku preferujeme IP, protože tu teď zobrazuješ v badge.
        # Client/visitor jsou fallback pro starší řádky bez ip=.
        color_key = ip or client or visitor
        kind_match = TRAFFIC_KIND_RE.search(line)

        if color_key:
            if color_key in assigned_colors:
                color_index = assigned_colors[color_key]
            else:
                if ip:
                    # Původní logika podle IP.
                    color_index = sum(ord(char) for char in ip) % 12
                elif client:
                    color_index = int(client, 16) % 12
                elif visitor:
                    color_index = int(visitor, 16) % 12

                # Když jiný návštěvník/IP hned pod předchozím vyjde stejnou barvou,
                # posuneme ho na další barvu z palety.
                if (
                    previous_color_index is not None
                    and color_index == previous_color_index
                    and color_key != previous_key
                ):
                    color_index = (color_index + 1) % 12

                assigned_colors[color_key] = color_index

        kind = kind_match.group(1) if kind_match else ""
        kind_class = kind.lower().replace("_", "-") if kind else ""

        colored_log_lines.append({
            "text": line,
            "ip": ip,
            "client": client,
            "visitor": visitor,
            "color_index": color_index,
            "ip_label": ip_label,
            "kind": kind,
            "kind_class": kind_class,
            "is_engaged": kind == "ENGAGED",
            "is_browser_confirmed": kind == "BROWSER_CONFIRMED",
        })

        if color_key:
            previous_key = color_key
            previous_color_index = color_index

    return colored_log_lines

def filter_common_staff_get_lines(log_text, max_lines):
    hidden_count = 0
    kept_lines = []

    for line in log_text.splitlines():
        if "STAFF_ACTION" in line and " kind=common_get " in line:
            hidden_count += 1
            continue

        kept_lines.append(line)

    kept_lines = kept_lines[-max_lines:]

    return "\n".join(kept_lines), hidden_count


def build_time_search_terms(value):
    value = (value or "").strip()

    if not value:
        return []

    formats = (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y/%m/%d %H:%M:%S",
        "%Y/%m/%d %H:%M",
    )

    parsed = None

    for fmt in formats:
        try:
            parsed = datetime.strptime(value, fmt)
            break
        except ValueError:
            continue

    # Když to neumíme rozparsovat jako datum, použijeme to prostě jako text.
    if parsed is None:
        return [value]

    return [
        parsed.strftime("%Y-%m-%d %H:%M"),
        parsed.strftime("%Y/%m/%d %H:%M"),
        parsed.strftime("%d/%b/%Y:%H:%M"),
    ]


def filter_log_lines_with_context(log_text, search_terms, context_lines, max_output_lines):
    search_terms = [
        term.lower()
        for term in search_terms
        if term and term.strip()
    ]

    if not search_terms:
        return log_text, 0

    lines = log_text.splitlines()
    selected_indexes = set()
    match_count = 0

    for index, line in enumerate(lines):
        line_lower = line.lower()

        if any(term in line_lower for term in search_terms):
            match_count += 1

            start = max(0, index - context_lines)
            end = min(len(lines), index + context_lines + 1)

            selected_indexes.update(range(start, end))

    if not selected_indexes:
        return "", 0

    output_lines = []
    previous_index = None

    for index in sorted(selected_indexes):
        if previous_index is not None and index > previous_index + 1:
            output_lines.append("…")

        output_lines.append(lines[index])
        previous_index = index

    if len(output_lines) > max_output_lines:
        output_lines = output_lines[-max_output_lines:]

    return "\n".join(output_lines), match_count


def parse_traffic_log_line(line):
    kind_match = TRAFFIC_KIND_RE.search(line)

    if not kind_match:
        return None

    item = {
        "line": line,
        "kind": kind_match.group(1),
        "timestamp": None,
        "ip": "",
        "client": "",
        "visitor": "",
        "method": "",
        "status": None,
        "path": "",
        "referer": "",
        "source_referer": "",
        "reason": "",
        "score": "",
        "trigger": "",
        "source": "",
        "elapsed_ms": "",
        "total_visible_ms": "",
        "max_visible_span_ms": "",
        "visibility_changes": "",
        "visible_intervals": "",
        "browser_sent": "",
        "engaged_sent": "",
        "had_pointer": "",
        "had_touch": "",
        "had_scroll": "",
        "had_key": "",
        "max_scroll_pct": "",
        "prerendered": "",
        "fetch_user": "",
        "fetch_mode": "",
        "fetch_dest": "",
        "fetch_site": "",
        "purpose": "",
        "ua": "",
        "removed_pageviews": "",
        "candidates": "",
        "span": "",
        "hits": "",
        "paths": "",
        "visitors": "",
        "uas": "",
        "network": "",
        "clients": "",
        "ips": "",
        "span_seconds": "",
        "sample_paths": "",
        "details": "",
        "source_visitor": "",
        "beacon_visitor": "",
        "doc": "",
        "initial_visibility": "",
        "final_visibility": "",
        "initial_focus": "",
        "final_focus": "",
        "navigation_type": "",
        "exit_trigger": "",
        "pagehide_persisted": "",
        "document_referrer": "",
        "document_ua": "",

        "age_ms": "",
        "previous_visitor": "",
        "current_visitor": "",
        "referer_host": "",
        "previous_ua": "",
        "current_ua": "",
    }

    timestamp_match = TRAFFIC_TS_RE.search(line)
    if timestamp_match:
        try:
            item["timestamp"] = datetime.strptime(
                timestamp_match.group(1),
                "%Y-%m-%d %H:%M:%S",
            )
        except ValueError:
            pass

    for key, pattern in TRAFFIC_FIELD_PATTERNS.items():
        match = pattern.search(line)
        if match:
            item[key] = match.group(1)

    ua_match = UA_RE.search(line)
    if ua_match:
        item["ua"] = ua_match.group(1).strip()

    if item["status"]:
        try:
            item["status"] = int(item["status"])
        except ValueError:
            item["status"] = None

    return item


def shorten_text(value, max_length=160):
    value = value or ""

    if len(value) <= max_length:
        return value

    return value[:max_length - 1] + "…"


def get_reason_family(reason):
    reason = reason or ""

    if not reason:
        return "bez důvodu"

    return reason.split(":", 1)[0]


SOCIAL_IMAGE_404_RE = re.compile(
    r"^/\d{8,}_.+_n/?$",
    re.IGNORECASE,
)

SOCIAL_IMAGE_PREFIX_404_RE = re.compile(
    r"^/(?:mng|z6p|dsc)[_-].*",
    re.IGNORECASE,
)


def normalize_audit_404_path(path):
    path = (path or "").strip()
    path_lower = path.lower()

    if path_lower in (
        "/meta.json",
        "/news_sitemap.xml",
        "/news-sitemap.xml",
    ):
        return "/__scan__/meta"

    if (
        SOCIAL_IMAGE_404_RE.match(path_lower)
        or SOCIAL_IMAGE_PREFIX_404_RE.match(path_lower)
    ):
        return "/__scan__/social-image"

    if (
        "sitemap" in path_lower
        and (
            path_lower.endswith(".xml")
            or path_lower.endswith(".txt")
        )
    ):
        return "/__scan__/sitemap"

    return path



AUDIT_OWN_REFERER_DOMAINS = (
    "lieder-society.cz",
    "liedersociety.cz",
    "liedersociety.website",
)

AUDIT_SEARCH_REFERER_PARTS = (
    "google.",
    "seznam.",
    "bing.",
    "duckduckgo.",
    "yahoo.",
    "ecosia.",
    "startpage.",
    "search.brave.",
)

AUDIT_SOCIAL_REFERER_DOMAINS = (
    "facebook.com",
    "instagram.com",
    "threads.net",
    "twitter.com",
    "x.com",
    "t.co",
    "linkedin.com",
)

# Tyto realtime cleanupy mažou celý client, ne pouze konkrétní visitor identity.
# Musíme je proto při auditu odečítat podle clientu.
AUDIT_CLIENT_LEVEL_CLEANUP_REASONS = {
    "rapid_identity_switch",
    "homepage_identity_switch",
    "ua_rotation",
    "rapid_navigation",
    "known_scanner",
    "meta_infrastructure_ip",
    "scanner_request",
    "subnet_swarm",
    "repeated_exact_no_ref_no_engagement",
}


def get_audit_day(item):
    timestamp = item.get("timestamp")

    if timestamp is None:
        return None

    return timestamp.date()


def classify_audit_referer(referer):
    referer = (referer or "").strip()

    if not referer:
        return "EMPTY"

    value = referer

    if "://" not in value:
        value = "https://" + value

    try:
        host = (
            urlparse(value).hostname
            or ""
        ).lower().rstrip(".")
    except Exception:
        host = ""

    if any(
        host == domain
        or host.endswith("." + domain)
        for domain in AUDIT_OWN_REFERER_DOMAINS
    ):
        return "OWN"

    if any(
        part in host
        for part in AUDIT_SEARCH_REFERER_PARTS
    ):
        return "SEARCH"

    if any(
        host == domain
        or host.endswith("." + domain)
        for domain in AUDIT_SOCIAL_REFERER_DOMAINS
    ):
        return "SOCIAL"

    return "EXTERNAL"


def is_audit_client_level_cleanup_reason(reason):
    reason = (reason or "").strip()

    # Sticky varianta jen obaluje původní důvod.
    while reason.startswith("sticky:"):
        reason = reason.removeprefix("sticky:")

    # shared_ua cleanupuje v middleware celý client.
    if (
        reason == "shared_ua"
        or reason.startswith("shared_ua:")
    ):
        return True

    return reason in AUDIT_CLIENT_LEVEL_CLEANUP_REASONS




def build_traffic_audit(log_text, since=None):
    items = []

    for line in log_text.splitlines():
        item = parse_traffic_log_line(line)

        if item:
            items.append(item)

    if since is not None:
        items = [item for item in items if item["timestamp"] is not None and item["timestamp"] >= since]

    kind_counts = Counter(item["kind"] for item in items)

    bot_like_reasons = Counter(
        get_reason_family(item["reason"])
        for item in items
        if item["kind"] == "BOT_LIKE"
    )

    engaged_skip_reasons = Counter(
        item["reason"] or "bez důvodu"
        for item in items
        if item["kind"] == "ENGAGED_SKIP"
    )

    browser_skip_reasons = Counter(
        item["reason"] or "bez důvodu"
        for item in items
        if item["kind"] == "BROWSER_SKIP"
    )

    browser_confirmed_triggers = Counter(
        item["trigger"] or "bez triggeru"
        for item in items
        if item["kind"] == "BROWSER_CONFIRMED"
    )

    visit_paths = Counter(
        item["path"]
        for item in items
        if item["kind"] == "VISIT" and item["path"]
    )

    duplicate_paths = Counter(
        item["path"]
        for item in items
        if item["kind"] == "VISIT_DUPLICATE" and item["path"]
    )

    duplicate_reasons = Counter(
        item["reason"] or "bez důvodu"
        for item in items
        if item["kind"] == "VISIT_DUPLICATE"
    )

    bot_like_paths = Counter(
        item["path"]
        for item in items
        if item["kind"] == "BOT_LIKE" and item["path"]
    )

    not_found_paths = Counter(
        normalize_audit_404_path(item["path"])
        for item in items
        if item["status"] == 404 and item["path"]
    )

    posthoc_cleanup_reasons = Counter(
        get_reason_family(item["reason"])
        for item in items
        if item["kind"] == "POSTHOC_CLEANUP"
    )

    posthoc_cleanup_rows = []

    for item in reversed(items):
        if item["kind"] != "POSTHOC_CLEANUP":
            continue

        posthoc_cleanup_rows.append({
            "time": item["timestamp"],
            "client": item["client"],
            "visitor": item["visitor"],
            "path": item["path"],
            "reason": item["reason"] or "bez důvodu",
            "removed_pageviews": item["removed_pageviews"],
            "candidates": item["candidates"],
            "line": item["line"],
        })

        if len(posthoc_cleanup_rows) >= 20:
            break


    # =========================================================
    # VISIT BEZ JS POTVRZENÍ
    #
    # Nezajímá nás počet jednotlivých VISIT log řádků,
    # ale unikátní visitor identity.
    #
    # Do DailySiteVisitor middleware zapisuje pouze GET,
    # proto i zde počítáme pouze GET VISIT.
    # =========================================================

    visit_items = [
        item
        for item in items
        if (
            item["kind"] == "VISIT"
            and item["method"] == "GET"
            and item["visitor"]
        )
    ]

    visit_keys = {
        (
            get_audit_day(item),
            item["visitor"],
        )
        for item in visit_items
    }

    browser_confirmed_keys = {
        (
            get_audit_day(item),
            item["visitor"],
        )
        for item in items
        if (
            item["kind"] == "BROWSER_CONFIRMED"
            and item["visitor"]
        )
    }

    engaged_keys = {
        (
            get_audit_day(item),
            item["visitor"],
        )
        for item in items
        if (
            item["kind"] == "ENGAGED"
            and item["visitor"]
        )
    }

    # ENGAGED je také jednoznačné JS potvrzení skutečného browseru.
    # Kdyby z nějakého důvodu chyběl samostatný BROWSER_CONFIRMED,
    # nechceme takového návštěvníka považovat za nepotvrzeného.
    js_confirmed_keys = (
        browser_confirmed_keys
        | engaged_keys
    )

    cleaned_visitor_keys = set()
    cleaned_client_keys = set()

    for item in items:
        day = get_audit_day(item)

        if item["kind"] == "POSTHOC_CLEANUP":
            if item["visitor"]:
                cleaned_visitor_keys.add(
                    (
                        day,
                        item["visitor"],
                    )
                )

            continue

        if item["kind"] != "CLEANUP":
            continue

        if is_audit_client_level_cleanup_reason(
            item["reason"]
        ):
            if item["client"]:
                cleaned_client_keys.add(
                    (
                        day,
                        item["client"],
                    )
                )

        elif item["visitor"]:
            cleaned_visitor_keys.add(
                (
                    day,
                    item["visitor"],
                )
            )

    # Pro každého VISIT visitora zjistíme jeho client identity.
    # Je to potřeba proto, že některý CLEANUP odstraní celý client.
    visitor_clients = defaultdict(set)

    for item in visit_items:
        visitor_key = (
            get_audit_day(item),
            item["visitor"],
        )

        if item["client"]:
            visitor_clients[visitor_key].add(
                (
                    get_audit_day(item),
                    item["client"],
                )
            )

    cleaned_visit_keys = set()

    for visitor_key in visit_keys:
        if visitor_key in cleaned_visitor_keys:
            cleaned_visit_keys.add(visitor_key)
            continue

        client_keys = visitor_clients.get(
            visitor_key,
            set(),
        )

        if client_keys & cleaned_client_keys:
            cleaned_visit_keys.add(visitor_key)

    browser_confirmed_visit_keys = (
        visit_keys
        & browser_confirmed_keys
    )

    engaged_visit_keys = (
        visit_keys
        & engaged_keys
    )

    js_confirmed_visit_keys = (
        visit_keys
        & js_confirmed_keys
    )

    # Tohle je množina, kterou chceme skutečně zkoumat:
    #
    # VISIT
    # - browser/engaged confirmation
    # - realtime/posthoc cleanup
    unconfirmed_visit_keys = (
        visit_keys
        - js_confirmed_keys
        - cleaned_visit_keys
    )

    visits_by_visitor = defaultdict(list)

    for item in visit_items:
        visitor_key = (
            get_audit_day(item),
            item["visitor"],
        )

        if visitor_key in unconfirmed_visit_keys:
            visits_by_visitor[
                visitor_key
            ].append(item)

    unconfirmed_rows = []

    for (
        day,
        visitor,
    ), visitor_items in visits_by_visitor.items():

        visitor_items.sort(
            key=lambda row: (
                row["timestamp"]
                or datetime.min
            )
        )

        first = visitor_items[0]
        last = visitor_items[-1]

        unique_paths = list(
            dict.fromkeys(
                row["path"]
                for row in visitor_items
                if row["path"]
            )
        )

        referer = (
            first["referer"]
            or ""
        )

        ua = (
            first["ua"]
            or ""
        )

        unconfirmed_rows.append({
            "day": day,
            "first_seen": first["timestamp"],
            "last_seen": last["timestamp"],
            "ip": first["ip"],
            "client": first["client"],
            "visitor": visitor,
            "visit_count": len(visitor_items),
            "path_count": len(unique_paths),
            "first_path": (
                unique_paths[0]
                if unique_paths
                else ""
            ),
            "referer": referer,
            "referer_kind": classify_audit_referer(
                referer
            ),
            "fetch_user": first["fetch_user"],
            "fetch_mode": first["fetch_mode"],
            "fetch_dest": first["fetch_dest"],
            "fetch_site": first["fetch_site"],
            "purpose": first["purpose"],
            "ua": shorten_text(
                ua,
                220,
            ),
            "_ua_full": ua,
        })

    unconfirmed_rows.sort(
        key=lambda row: (
            row["last_seen"]
            or datetime.min
        ),
        reverse=True,
    )

    unconfirmed_referer_counter = Counter(
        row["referer_kind"]
        for row in unconfirmed_rows
    )

    unconfirmed_referer_breakdown = [
        (
            label,
            unconfirmed_referer_counter.get(
                label,
                0,
            ),
        )
        for label in (
            "EMPTY",
            "OWN",
            "SEARCH",
            "SOCIAL",
            "EXTERNAL",
        )
    ]

    unconfirmed_visit_distribution = [
        (
            "1 VISIT",
            sum(
                1
                for row in unconfirmed_rows
                if row["visit_count"] == 1
            ),
        ),
        (
            "2 VISIT",
            sum(
                1
                for row in unconfirmed_rows
                if row["visit_count"] == 2
            ),
        ),
        (
            "3+ VISIT",
            sum(
                1
                for row in unconfirmed_rows
                if row["visit_count"] >= 3
            ),
        ),
    ]

    unconfirmed_ua_counter = Counter(
        (
            row["_ua_full"]
            or "bez User-Agentu"
        )
        for row in unconfirmed_rows
    )

    unconfirmed_top_uas = [
        {
            "ua": shorten_text(
                ua,
                180,
            ),
            "visitor_count": count,
        }
        for ua, count
        in unconfirmed_ua_counter.most_common(10)
    ]


    ua_clients = defaultdict(set)
    client_uas = defaultdict(set)
    client_kinds = defaultdict(set)

    suspicious_visits = []

    for item in items:
        ua = item["ua"]
        client = item["client"]
        kind = item["kind"]

        if ua and client:
            ua_clients[ua].add(client)
            client_uas[client].add(ua)

        if client:
            client_kinds[client].add(kind)

        if kind == "VISIT":
            ua_lower = ua.lower()
            path_lower = (item["path"] or "").lower()
            referer = item["referer"] or ""

            reasons = []

            if any(part in ua_lower for part in ("wordpress cms scanner", "cms scanner", "ct-wp-probe", "palo alto networks", "cortex-xpanse")):
                reasons.append("scanner_ua")

            if path_lower == "/wp-json" or path_lower.startswith("/wp-json/"):
                reasons.append("wp_json_path")

            if path_lower == "/feed" or path_lower.startswith("/feed/"):
                reasons.append("feed_path")

            if not referer and "chrome/148" in ua_lower:
                reasons.append("empty_referer_chrome_148")

            if reasons:
                suspicious_visits.append({
                    "time": item["timestamp"],
                    "client": client,
                    "path": item["path"],
                    "status": item["status"],
                    "reasons": ", ".join(reasons),
                    "ua": shorten_text(ua, 140),
                    "line": item["line"],
                })

    ua_many_clients = [
        {
            "ua": shorten_text(ua, 160),
            "client_count": len(clients),
        }
        for ua, clients in ua_clients.items()
        if len(clients) >= 5
    ]
    ua_many_clients.sort(key=lambda row: row["client_count"], reverse=True)

    clients_many_uas = [
        {
            "client": client,
            "ua_count": len(uas),
            "sample_uas": [shorten_text(ua, 90) for ua in list(uas)[:5]],
        }
        for client, uas in client_uas.items()
        if len(uas) >= 4
    ]
    clients_many_uas.sort(key=lambda row: row["ua_count"], reverse=True)

    mixed_clients = [
        {
            "client": client,
            "kinds": ", ".join(sorted(kinds)),
            "ua_count": len(client_uas.get(client, set())),
        }
        for client, kinds in client_kinds.items()
        if "VISIT" in kinds and "BOT_LIKE" in kinds
    ]
    mixed_clients.sort(key=lambda row: row["ua_count"], reverse=True)

    duplicate_rows = []

    for item in reversed(items):
        if item["kind"] != "VISIT_DUPLICATE":
            continue

        duplicate_rows.append({
            "time": item["timestamp"],
            "ip": item["ip"],
            "client": item["client"],
            "visitor": item["visitor"],
            "path": item["path"],
            "reason": item["reason"] or "bez důvodu",
            "referer": item["referer"],
            "ua": shorten_text(item["ua"], 180),
        })

        if len(duplicate_rows) >= 20:
            break


    browser_confirmed_rows = []

    for item in reversed(items):
        if item["kind"] != "BROWSER_CONFIRMED":
            continue

        browser_confirmed_rows.append({
            "time": item["timestamp"],
            "ip": item["ip"],
            "client": item["client"],
            "visitor": item["visitor"],
            "path": item["path"],
            "trigger": item["trigger"] or "—",
            "referer": item["referer"],
            "source_referer": item["source_referer"],
            "ua": shorten_text(item["ua"], 160),
        })

        if len(browser_confirmed_rows) >= 20:
            break


    browser_skip_rows = []

    for item in reversed(items):
        if item["kind"] != "BROWSER_SKIP":
            continue

        browser_skip_rows.append({
            "time": item["timestamp"],
            "ip": item["ip"],
            "client": item["client"],
            "visitor": item["visitor"],
            "path": item["path"],
            "reason": item["reason"] or "bez důvodu",
            "referer": item["referer"],
            "source_referer": item["source_referer"],
            "ua": shorten_text(item["ua"], 160),
        })

        if len(browser_skip_rows) >= 20:
            break

    engaged_skip_rows = []

    for item in reversed(items):
        if item["kind"] != "ENGAGED_SKIP":
            continue

        engaged_skip_rows.append({
            "time": item["timestamp"],
            "ip": item["ip"],
            "client": item["client"],
            "visitor": item["visitor"],
            "path": item["path"],
            "reason": item["reason"] or "bez důvodu",
            "referer": item["referer"],
            "source_referer": item["source_referer"],
            "ua": shorten_text(item["ua"], 160),
        })

        if len(engaged_skip_rows) >= 20:
            break

    rapid_identity_candidates = []

    for item in reversed(items):
        if item["kind"] != "RAPID_IDENTITY_CANDIDATE":
            continue

        rapid_identity_candidates.append({
            "time": item["timestamp"],
            "client": item["client"],
            "span": item["span"],
            "hits": item["hits"],
            "paths": item["paths"],
            "visitors": item["visitors"],
            "uas": item["uas"],
            "details": shorten_text(
                item["details"],
                800,
            ),
        })

        if len(rapid_identity_candidates) >= 30:
            break
    meta_exit_diag_rows = []

    def audit_diag_int(value):
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0

    for item in reversed(items):
        if item["kind"] != "META_EXIT_DIAG":
            continue

        elapsed_ms = audit_diag_int(
            item["elapsed_ms"]
        )

        total_visible_ms = audit_diag_int(
            item["total_visible_ms"]
        )

        max_visible_span_ms = audit_diag_int(
            item["max_visible_span_ms"]
        )

        visibility_changes = audit_diag_int(
            item["visibility_changes"]
        )

        visible_intervals = audit_diag_int(
            item["visible_intervals"]
        )

        max_scroll_pct = audit_diag_int(
            item["max_scroll_pct"]
        )

        browser_sent = (
            item["browser_sent"] == "1"
        )

        engaged_sent = (
            item["engaged_sent"] == "1"
        )

        had_pointer = (
            item["had_pointer"] == "1"
        )

        had_touch = (
            item["had_touch"] == "1"
        )

        had_scroll = (
            item["had_scroll"] == "1"
        )

        had_key = (
            item["had_key"] == "1"
        )

        prerendered = (
            item["prerendered"] == "1"
        )

        interaction_parts = []

        if had_pointer:
            interaction_parts.append("pointer")

        if had_touch:
            interaction_parts.append("touch")

        if had_scroll:
            interaction_parts.append("scroll")

        if had_key:
            interaction_parts.append("key")

        had_any_interaction = bool(
            interaction_parts
        )

        # Pouze diagnostický flag.
        #
        # Dokument existoval alespoň 3 sekundy,
        # ale nikdy nebyl 750 ms v kuse visible,
        # neposlal Browser ani Engaged a nebyla
        # zachycena žádná uživatelská interakce.
        background_candidate = (
            elapsed_ms >= 3000
            and max_visible_span_ms < 750
            and not browser_sent
            and not engaged_sent
            and not had_any_interaction
        )

        initial_focus = (
            item["initial_focus"] == "1"
        )

        final_focus = (
            item["final_focus"] == "1"
        )

        pagehide_persisted = (
            item["pagehide_persisted"] == "1"
        )

        # Kompatibilita se starými META_EXIT_DIAG řádky,
        # které měly jen visitor=...
        source_visitor = (
            item["source_visitor"]
            or item["visitor"]
        )

        beacon_visitor = (
            item["beacon_visitor"]
            or item["visitor"]
        )


        meta_exit_diag_rows.append({
            "time": item["timestamp"],

            "source": (item["source"] or "unknown"),

            "ip": item["ip"],
            "client": item["client"],

            "source_visitor": source_visitor,
            "beacon_visitor": beacon_visitor,

            "doc": item["doc"],

            "path": item["path"],

            "elapsed_ms": elapsed_ms,
            "total_visible_ms": total_visible_ms,
            "max_visible_span_ms": max_visible_span_ms,

            "visibility_changes": visibility_changes,
            "visible_intervals": visible_intervals,

            "initial_visibility": (
                item["initial_visibility"]
                or "—"
            ),

            "final_visibility": (
                item["final_visibility"]
                or "—"
            ),

            "initial_focus": initial_focus,
            "final_focus": final_focus,

            "navigation_type": (
                item["navigation_type"]
                or "—"
            ),

            "exit_trigger": (
                item["exit_trigger"]
                or item["trigger"]
                or "—"
            ),

            "pagehide_persisted": (
                pagehide_persisted
            ),

            "browser_sent": browser_sent,
            "engaged_sent": engaged_sent,

            "interaction": (
                ", ".join(interaction_parts)
                if interaction_parts
                else "—"
            ),

            "max_scroll_pct": max_scroll_pct,
            "prerendered": prerendered,

            "background_candidate": (
                background_candidate
            ),

            "document_referrer": shorten_text(
                item["document_referrer"],
                180,
            ),

            "document_ua": shorten_text(
                item["document_ua"],
                220,
            ),

            "ua": shorten_text(
                item["ua"],
                220,
            ),
        })

        if len(meta_exit_diag_rows) >= 50:
            break


    social_dup_pair_rows = []

    for item in reversed(items):
        if item["kind"] != "SOCIAL_DUP_PAIR":
            continue

        social_dup_pair_rows.append({
            "time": item["timestamp"],
            "client": item["client"],
            "path": item["path"],

            "age_ms": audit_diag_int(
                item["age_ms"]
            ),

            "previous_visitor": (
                item["previous_visitor"]
            ),

            "current_visitor": (
                item["current_visitor"]
            ),

            "referer_host": (
                item["referer_host"]
            ),

            "previous_ua": shorten_text(
                item["previous_ua"],
                260,
            ),

            "current_ua": shorten_text(
                item["current_ua"],
                260,
            ),
        })

        if len(social_dup_pair_rows) >= 50:
            break

    network_pattern_candidates = []

    for item in reversed(items):
        if item["kind"] != "NETWORK_PATTERN_CANDIDATE":
            continue

        network_pattern_candidates.append({
            "time": item["timestamp"],
            "network": item["network"],
            "reason": (
                item["reason"]
                or "bez důvodu"
            ),
            "hits": item["hits"],
            "clients": item["clients"],
            "visitors": item["visitors"],
            "ips": item["ips"],
            "paths": item["paths"],
            "uas": item["uas"],
            "span_seconds": item["span_seconds"],
            "sample_paths": (
                item["sample_paths"]
                or ""
            ),
        })

        if len(network_pattern_candidates) >= 30:
            break

    return {
        "total_items": len(items),
        "kind_counts": kind_counts.most_common(),
        "bot_like_reasons": bot_like_reasons.most_common(10),
        "visit_paths": visit_paths.most_common(15),
        "duplicate_paths": duplicate_paths.most_common(15),
        "duplicate_reasons": duplicate_reasons.most_common(10),
        "duplicate_rows": duplicate_rows,
        "bot_like_paths": bot_like_paths.most_common(15),
        "not_found_paths": not_found_paths.most_common(15),
        "ua_many_clients": ua_many_clients[:15],
        "clients_many_uas": clients_many_uas[:15],
        "mixed_clients": mixed_clients[:15],
        "suspicious_visits": suspicious_visits[:30],
        "rapid_identity_candidates": rapid_identity_candidates,
        "network_pattern_candidates": network_pattern_candidates,
        "meta_exit_diag_rows": meta_exit_diag_rows,
        "social_dup_pair_rows": social_dup_pair_rows,
        "browser_skip_reasons": browser_skip_reasons.most_common(10),
        "browser_confirmed_triggers": browser_confirmed_triggers.most_common(10),
        "browser_confirmed_rows": browser_confirmed_rows,
        "browser_skip_rows": browser_skip_rows,
        "engaged_skip_reasons": engaged_skip_reasons.most_common(10),
        "engaged_skip_rows": engaged_skip_rows,
        "posthoc_cleanup_reasons": posthoc_cleanup_reasons.most_common(10),
        "posthoc_cleanup_rows": posthoc_cleanup_rows,
        "visit_visitor_count": len(visit_keys),
        "browser_confirmed_visit_visitor_count": len(browser_confirmed_visit_keys),
        "engaged_visit_visitor_count": len(engaged_visit_keys),
        "js_confirmed_visit_visitor_count": len(js_confirmed_visit_keys),
        "cleaned_visit_visitor_count": len(cleaned_visit_keys),
        "unconfirmed_visit_visitor_count": len(unconfirmed_visit_keys),
        "unconfirmed_referer_breakdown": (unconfirmed_referer_breakdown),
        "unconfirmed_visit_distribution": (unconfirmed_visit_distribution),
        "unconfirmed_top_uas": unconfirmed_top_uas,
        "unconfirmed_rows": unconfirmed_rows[:50],
    }


def read_log_tail(log_path, lines, timeout=5):
    if not log_path.exists():
        return "", f"Soubor neexistuje: {log_path}"

    try:
        result = subprocess.run(
            ["tail", "-n", str(lines), str(log_path)],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )

        if result.returncode == 0:
            return result.stdout, None

        return "", result.stderr or "Log se nepodařilo načíst."

    except subprocess.TimeoutExpired:
        return "", "Čtení logu trvalo příliš dlouho."
    except Exception as e:
        return "", f"Chyba při čtení logu: {e}"

@staff_member_required
def system_logs_view(request):
    if not request.user.is_superuser:
        return HttpResponseForbidden("Tato stránka je dostupná pouze superuserovi.")

    selected_log = request.GET.get("log", "traffic")
    log_path = LOG_FILES.get(selected_log)

    hide_common_staff_get = request.GET.get("hide_common_staff_get", "1") == "1"
    hidden_common_staff_get_count = 0

    if log_path is None:
        selected_log = "traffic"
        log_path = LOG_FILES[selected_log]

    try:
        lines = int(request.GET.get("lines", DEFAULT_LINES))
    except ValueError:
        lines = DEFAULT_LINES

    lines = max(10, min(lines, MAX_LINES))

    search_query = request.GET.get("q", "").strip()
    around_time = request.GET.get("around_time", "").strip()
    audit_since_raw = request.GET.get("audit_since", "").strip()
    audit_since = None

    if audit_since_raw:
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
            try:
                audit_since = datetime.strptime(audit_since_raw, fmt)
                break
            except ValueError:
                pass

    try:
        context_lines = int(request.GET.get("context_lines", 30))
    except ValueError:
        context_lines = 30

    context_lines = max(0, min(context_lines, 200))

    try:
        scan_lines = int(request.GET.get("scan_lines", 50000))
    except ValueError:
        scan_lines = 50000

    scan_lines = max(lines, min(scan_lines, 200000))

    search_terms = []

    if search_query:
        search_terms.append(search_query)

    search_terms.extend(build_time_search_terms(around_time))

    search_active = bool(search_terms)
    search_match_count = 0

    hide_noise = request.GET.get("hide_noise", "1") == "1"
    hidden_noise_count = 0

    log_text = ""
    error_message = None

    # Když skrýváme healthchecky, načteme víc řádků,
    # aby po odfiltrování pořád zůstalo dost relevantních záznamů.
    tail_lines = lines

    if search_active:
        tail_lines = scan_lines
    else:
        if hide_noise and selected_log in ("python", "python.old"):
            tail_lines = min(lines * 5, 5000)

        if hide_common_staff_get and selected_log == "staff_audit":
            tail_lines = min(lines * 10, 10000)

    if not log_path.exists():
        error_message = f"Soubor neexistuje: {log_path}"
    else:
        try:
            result = subprocess.run(
                ["tail", "-n", str(tail_lines), str(log_path)],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )

            if result.returncode == 0:
                log_text = result.stdout
            else:
                error_message = result.stderr or "Log se nepodařilo načíst."

        except subprocess.TimeoutExpired:
            error_message = "Čtení logu trvalo příliš dlouho."
        except Exception as e:
            error_message = f"Chyba při čtení logu: {e}"

    if hide_noise and selected_log in ("python", "python.old"):
        log_text, hidden_noise_count = filter_noise_log_lines(
            log_text,
            scan_lines if search_active else lines,
        )

    if hide_common_staff_get and selected_log == "staff_audit":
        log_text, hidden_common_staff_get_count = filter_common_staff_get_lines(
            log_text,
            scan_lines if search_active else lines,
        )

    if search_active:
        log_text, search_match_count = filter_log_lines_with_context(
            log_text,
            search_terms,
            context_lines,
            lines,
        )

    colored_log_lines = build_colored_log_lines(log_text)


    traffic_audit = None
    traffic_audit_error = None

    if selected_log == "traffic":
        traffic_audit_text, traffic_audit_error = read_log_tail(
            LOG_FILES["traffic"],
            min(scan_lines, 50000),
        )

        if traffic_audit_text:
            traffic_audit = build_traffic_audit(
                traffic_audit_text,
                since=audit_since,
            )

    human_daily_stats = {
        row["day"]: row
        for row in (
            DailySiteVisitor.objects
            .values("day")
            .annotate(
                unique_visitors=Count("id"),
                unique_clients=Count("client_hash", distinct=True),
                pageviews=Sum("pageviews"),
            )
        )
    }

    daily_stats = list(
        DailySiteTraffic.objects
        .values(
            "day",
            "total_hits",
            "human_hits",
            "bot_hits",
        )
        .order_by("-day")[:30]
    )

    browser_counts = {
        row["day"]: row["count"]
        for row in (
            DailyBrowserVisitor.objects
            .values("day")
            .annotate(count=Count("id"))
        )
    }

    engaged_counts = {
        row["day"]: row["count"]
        for row in (
            DailyEngagedVisitor.objects
            .values("day")
            .annotate(count=Count("id"))
        )
    }


    browser_source_counts = defaultdict(
        lambda: {
            "facebook": 0,
            "instagram": 0,
            "google": 0,
            "other": 0,
        }
    )

    for source_row in (
        DailyBrowserVisitor.objects
        .values("day", "source")
        .annotate(count=Count("id"))
    ):
        source = source_row["source"]

        if source not in (
            "facebook",
            "instagram",
            "google",
        ):
            source = "other"

        browser_source_counts[
            source_row["day"]
        ][source] += source_row["count"]


    engaged_source_counts = defaultdict(
        lambda: {
            "facebook": 0,
            "instagram": 0,
            "google": 0,
            "other": 0,
        }
    )

    for source_row in (
        DailyEngagedVisitor.objects
        .values("day", "source")
        .annotate(count=Count("id"))
    ):
        source = source_row["source"]

        if source not in (
            "facebook",
            "instagram",
            "google",
        ):
            source = "other"

        engaged_source_counts[
            source_row["day"]
        ][source] += source_row["count"]

    for row in daily_stats:
        human_row = human_daily_stats.get(
            row["day"],
            {},
        )

        pageviews = (
            human_row.get("pageviews", 0)
            or 0
        )

        human_requests = (
            row.get("human_hits", 0)
            or 0
        )

        unique_visitors = (
            human_row.get("unique_visitors", 0)
            or 0
        )

        browser_visitors = (
            browser_counts.get(row["day"], 0)
            or 0
        )

        engaged_visitors = (
            engaged_counts.get(row["day"], 0)
            or 0
        )

        browser_sources = browser_source_counts[
            row["day"]
        ]

        engaged_sources = engaged_source_counts[
            row["day"]
        ]

        row["unique_visitors"] = unique_visitors
        row["unique_clients"] = (
            human_row.get("unique_clients", 0)
            or 0
        )

        row["browser_visitors"] = browser_visitors
        row["engaged_visitors"] = engaged_visitors

        row["browser_facebook"] = browser_sources["facebook"]
        row["browser_instagram"] = browser_sources["instagram"]
        row["browser_google"] = browser_sources["google"]
        row["browser_other"] = browser_sources["other"]

        row["engaged_facebook"] = engaged_sources["facebook"]
        row["engaged_instagram"] = engaged_sources["instagram"]
        row["engaged_google"] = engaged_sources["google"]
        row["engaged_other"] = engaged_sources["other"]

        if unique_visitors:
            row["browser_pct_of_visitors"] = round(
                browser_visitors
                / unique_visitors
                * 100,
                1,
            )
        else:
            row["browser_pct_of_visitors"] = 0

        if browser_visitors:
            row["engaged_pct_of_browser"] = round(
                engaged_visitors
                / browser_visitors
                * 100,
                1,
            )
        else:
            row["engaged_pct_of_browser"] = 0

        row["pageviews"] = pageviews
        row["human_requests"] = human_requests

        row["human_non_pageview_hits"] = max(
            0,
            human_requests - pageviews,
        )

    engaged_page_stats = defaultdict(
        lambda: {
            "total": 0,
            "facebook": 0,
            "instagram": 0,
            "google": 0,
            "own": 0,
            "other": 0,
        }
    )

    for source_row in (
        DailyEngagedPageVisitor.objects
        .values(
            "day",
            "path",
            "source",
        )
        .annotate(
            count=Count("id"),
        )
    ):
        key = (
            source_row["day"],
            source_row["path"],
        )

        source = source_row["source"]

        if source not in (
            "facebook",
            "instagram",
            "google",
            "own",
        ):
            source = "other"

        count = source_row["count"] or 0

        engaged_page_stats[key]["total"] += count
        engaged_page_stats[key][source] += count

    human_page_stats = {
        (row["day"], row["path"]): row
        for row in (
            DailyPageVisitor.objects
            .values("day", "path")
            .annotate(
                unique_visitors=Count("id"),
                human_pageviews=Sum("pageviews"),
            )
        )
    }

    page_stats = list(
        DailyPageTraffic.objects
        .values(
            "day",
            "path",
            "total_hits",
            "human_hits",
            "bot_hits",
            "ok_hits",
            "redirect_hits",
            "not_found_hits",
            "error_hits",
        )
        .order_by("-day", "-total_hits")[:100]
    )

    for row in page_stats:
        human_row = human_page_stats.get((row["day"], row["path"]), {})

        human_pageviews = human_row.get("human_pageviews", 0) or 0
        human_requests = row.get("human_hits", 0) or 0
        engaged_page = engaged_page_stats.get((row["day"], row["path"]), {},)

        row["unique_visitors"] = human_row.get("unique_visitors", 0)
        row["human_pageviews"] = human_pageviews
        row["human_requests"] = human_requests
        row["human_non_pageview_hits"] = max(0, human_requests - human_pageviews)
        row["engaged_visitors"] = engaged_page.get("total", 0) or 0
        row["engaged_facebook"] = engaged_page.get("facebook", 0) or 0
        row["engaged_instagram"] = engaged_page.get("instagram", 0) or 0
        row["engaged_google"] = engaged_page.get("google", 0) or 0
        row["engaged_own"] = engaged_page.get("own", 0) or 0
        row["engaged_other"] = engaged_page.get("other", 0) or 0
        row["other_hits"] = (
            row["total_hits"]
            - row["ok_hits"]
            - row["redirect_hits"]
            - row["not_found_hits"]
            - row["error_hits"]
        )

    agnes_stats = list(
        DailyPageVisitor.objects
        .filter(path="/agnes-tyrrell/")
        .values("day", "path")
        .annotate(
            unique_visitors=Count("id"),
            pageviews=Sum("pageviews"),
        )
        .order_by("-day")[:30]
    )

    return render(
        request,
        "admin/system_logs.html",
        {
            "title": "Systémové logy",
            "available_logs": LOG_FILES,
            "selected_log": selected_log,
            "selected_path": log_path,
            "lines": lines,
            "max_lines": MAX_LINES,
            "log_text": log_text,
            "error_message": error_message,
            "daily_stats": daily_stats,
            "page_stats": page_stats,
            "agnes_stats": agnes_stats,
            "colored_log_lines": colored_log_lines,
            "hide_noise": hide_noise,
            "hidden_noise_count": hidden_noise_count,
            "hide_common_staff_get": hide_common_staff_get,
            "hidden_common_staff_get_count": hidden_common_staff_get_count,
            "search_query": search_query,
            "around_time": around_time,
            "context_lines": context_lines,
            "scan_lines": scan_lines,
            "search_active": search_active,
            "search_match_count": search_match_count,
            "traffic_audit": traffic_audit,
            "traffic_audit_error": traffic_audit_error,
            "audit_since": audit_since_raw,
        },
    )