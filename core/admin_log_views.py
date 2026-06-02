from pathlib import Path
import subprocess
import re

from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpResponseForbidden
from django.shortcuts import render
from django.db.models import Count, Sum

from core.models import DailySiteVisitor, DailyPageVisitor


LOG_FILES = {
    "traffic": Path("/srv/log/traffic.log"),
    "python": Path("/srv/log/python.log"),
    "python.old": Path("/srv/log/python.log.1"),
    "nginx": Path("/srv/log/nginx.log"),
    "cron": Path("/srv/log/cron.log"),
    "security": Path("/srv/log/security.log"),
    "supervisord": Path("/srv/log/supervisord.log"),
}

DEFAULT_LINES = 100
MAX_LINES = 1000

# Pro barevné rozlišení traffic logu.
VISITOR_RE = re.compile(r"VISIT visitor=([a-f0-9]{8})")

# Pravidelný healthcheck / monitoring přes python-requests.
HEALTHCHECK_RE = re.compile(
    r'"GET / HTTP/1\.0" 200 \d+ "-" "python-requests/[^"]+"'
)


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

    for line in log_text.splitlines():
        match = VISITOR_RE.search(line)

        visitor = None
        color_index = None

        if match:
            visitor = match.group(1)
            color_index = int(visitor, 16) % 12

        colored_log_lines.append({
            "text": line,
            "visitor": visitor,
            "color_index": color_index,
        })

    return colored_log_lines


@staff_member_required
def system_logs_view(request):
    if not request.user.is_superuser:
        return HttpResponseForbidden("Tato stránka je dostupná pouze superuserovi.")

    selected_log = request.GET.get("log", "traffic")
    log_path = LOG_FILES.get(selected_log)

    if log_path is None:
        selected_log = "traffic"
        log_path = LOG_FILES[selected_log]

    try:
        lines = int(request.GET.get("lines", DEFAULT_LINES))
    except ValueError:
        lines = DEFAULT_LINES

    lines = max(10, min(lines, MAX_LINES))

    hide_noise = request.GET.get("hide_noise", "1") == "1"
    hidden_noise_count = 0

    log_text = ""
    error_message = None

    # Když skrýváme healthchecky, načteme víc řádků,
    # aby po odfiltrování pořád zůstalo dost relevantních záznamů.
    tail_lines = lines
    if hide_noise and selected_log in ("python", "python.old"):
        tail_lines = min(lines * 5, 5000)

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
        log_text, hidden_noise_count = filter_noise_log_lines(log_text, lines)

    colored_log_lines = build_colored_log_lines(log_text)

    daily_stats = list(
        DailySiteVisitor.objects
        .values("day")
        .annotate(
            unique_visitors=Count("id"),
            pageviews=Sum("pageviews"),
        )
        .order_by("-day")[:30]
    )

    page_stats = list(
        DailyPageVisitor.objects
        .values("day", "path")
        .annotate(
            unique_visitors=Count("id"),
            pageviews=Sum("pageviews"),
        )
        .order_by("-day", "-pageviews")[:100]
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
        },
    )