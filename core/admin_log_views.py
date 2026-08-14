from pathlib import Path
import subprocess
import re
from datetime import datetime
from collections import Counter, defaultdict

from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpResponseForbidden
from django.shortcuts import render
from django.db.models import Count, Sum

from core.models import DailySiteVisitor, DailyPageVisitor, DailySiteTraffic, DailyPageTraffic, DailyEngagedVisitor


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

TRAFFIC_KIND_RE = re.compile(r"\|\s+liederweb\.traffic\s+\|\s+(VISIT|BOT_LIKE|CLEANUP|ENGAGED|ENGAGED_SKIP)\s+")
TRAFFIC_TS_RE = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})")

TRAFFIC_FIELD_PATTERNS = {
    "ip": re.compile(r"\bip=([^\s]+)"),
    "client": re.compile(r"\bclient=([a-f0-9]{8})"),
    "visitor": re.compile(r"\bvisitor=([a-f0-9]{8})"),
    "method": re.compile(r"\bmethod=([A-Z]+)"),
    "status": re.compile(r"\bstatus=(\d{3})"),
    "path": re.compile(r"\bpath=([^\s]*)"),
    "referer": re.compile(r"\breferer=([^\s]*)"),
    "reason": re.compile(r"\breason=([^\s]*)"),
    "score": re.compile(r"\bscore=([^\s]*)"),
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
        "reason": "",
        "score": "",
        "ua": "",
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

    visit_paths = Counter(
        item["path"]
        for item in items
        if item["kind"] == "VISIT" and item["path"]
    )

    bot_like_paths = Counter(
        item["path"]
        for item in items
        if item["kind"] == "BOT_LIKE" and item["path"]
    )

    not_found_paths = Counter(
        item["path"]
        for item in items
        if item["status"] == 404 and item["path"]
    )

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

            if "wordpress cms scanner" in ua_lower or "cms scanner" in ua_lower:
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

    return {
        "total_items": len(items),
        "kind_counts": kind_counts.most_common(),
        "bot_like_reasons": bot_like_reasons.most_common(10),
        "visit_paths": visit_paths.most_common(15),
        "bot_like_paths": bot_like_paths.most_common(15),
        "not_found_paths": not_found_paths.most_common(15),
        "ua_many_clients": ua_many_clients[:15],
        "clients_many_uas": clients_many_uas[:15],
        "mixed_clients": mixed_clients[:15],
        "suspicious_visits": suspicious_visits[:30],
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

    engaged_counts = {
        row["day"]: row["count"]
        for row in (
            DailyEngagedVisitor.objects
            .values("day")
            .annotate(count=Count("id"))
        )
    }

    for row in daily_stats:
        human_row = human_daily_stats.get(row["day"], {})

        pageviews = human_row.get("pageviews", 0) or 0
        human_requests = row.get("human_hits", 0) or 0

        row["unique_visitors"] = human_row.get("unique_visitors", 0)
        row["engaged_visitors"] = engaged_counts.get(row["day"], 0)
        row["pageviews"] = pageviews
        row["human_requests"] = human_requests
        row["human_non_pageview_hits"] = max(0, human_requests - pageviews)

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

        row["unique_visitors"] = human_row.get("unique_visitors", 0)
        row["human_pageviews"] = human_pageviews
        row["human_requests"] = human_requests
        row["human_non_pageview_hits"] = max(0, human_requests - human_pageviews)

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