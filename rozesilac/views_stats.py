from datetime import timedelta, date

from django.contrib.auth.decorators import user_passes_test
from django.db.models import Count, Sum
from django.shortcuts import render
from django.utils import timezone


from core.models import (
    DailySiteVisitor,
    DailyPageVisitor,
    DailySiteTraffic,
    DailyEngagedVisitor,
)

TRAFFIC_STATS_PUBLIC_START_DATE = date(2026, 8, 13)

def staff_required(view_func):
    return user_passes_test(
        lambda user: user.is_active and user.is_staff,
        login_url="core:login",
    )(view_func)


def zero_none(value):
    return value or 0


def percent(part, total):
    if not total:
        return None
    return round((part / total) * 100, 1)


def get_period_summary(start_day, end_day):
    human = (
        DailySiteVisitor.objects
        .filter(day__range=(start_day, end_day))
        .aggregate(
            unique_visitors=Count("id"),
            pageviews=Sum("pageviews"),
        )
    )

    traffic = (
        DailySiteTraffic.objects
        .filter(day__range=(start_day, end_day))
        .aggregate(
            total_hits=Sum("total_hits"),
            human_hits=Sum("human_hits"),
            bot_hits=Sum("bot_hits"),
        )
    )

    unique_visitors = zero_none(human["unique_visitors"])
    engaged_visitors = DailyEngagedVisitor.objects.filter(
        day__range=(start_day, end_day)
    ).count()

    pageviews = zero_none(human["pageviews"])
    human_hits = zero_none(traffic["human_hits"])
    bot_hits = zero_none(traffic["bot_hits"])
    total_hits = zero_none(traffic["total_hits"])

    return {
        "start_day": start_day,
        "end_day": end_day,
        "unique_visitors": unique_visitors,
        "engaged_visitors": engaged_visitors,
        "pageviews": pageviews,
        "human_hits": human_hits,
        "bot_hits": bot_hits,
        "total_hits": total_hits,
        "human_non_pageview_hits": max(0, human_hits - pageviews),
        "engaged_rate": percent(engaged_visitors, unique_visitors),
        "bot_share": percent(bot_hits, total_hits),
    }


def get_daily_rows(start_day, end_day):
    human_by_day = {
        row["day"]: row
        for row in (
            DailySiteVisitor.objects
            .filter(day__range=(start_day, end_day))
            .values("day")
            .annotate(
                unique_visitors=Count("id"),
                pageviews=Sum("pageviews"),
            )
        )
    }

    traffic_by_day = {
        row["day"]: row
        for row in (
            DailySiteTraffic.objects
            .filter(day__range=(start_day, end_day))
            .values("day", "total_hits", "human_hits", "bot_hits")
        )
    }

    engaged_by_day = {
        row["day"]: row["count"]
        for row in (
            DailyEngagedVisitor.objects
            .filter(day__range=(start_day, end_day))
            .values("day")
            .annotate(count=Count("id"))
        )
    }

    rows = []
    current = end_day

    while current >= start_day:
        human = human_by_day.get(current, {})
        traffic = traffic_by_day.get(current, {})

        unique_visitors = zero_none(human.get("unique_visitors"))
        engaged_visitors = zero_none(engaged_by_day.get(current))
        pageviews = zero_none(human.get("pageviews"))
        human_hits = zero_none(traffic.get("human_hits"))
        bot_hits = zero_none(traffic.get("bot_hits"))
        total_hits = zero_none(traffic.get("total_hits"))

        rows.append({
            "day": current,
            "unique_visitors": unique_visitors,
            "engaged_visitors": engaged_visitors,
            "pageviews": pageviews,
            "human_hits": human_hits,
            "bot_hits": bot_hits,
            "total_hits": total_hits,
            "engaged_rate": percent(engaged_visitors, unique_visitors),
        })

        current -= timedelta(days=1)

    return rows


def get_top_pages(start_day, end_day):
    ignored_prefixes = (
        "/admin",
        "/static/",
        "/media/",
        "/traffic/",
        "/__scan__",
    )

    qs = (
        DailyPageVisitor.objects
        .filter(day__range=(start_day, end_day))
        .values("path")
        .annotate(
            unique_visitors=Count("id"),
            pageviews=Sum("pageviews"),
        )
        .order_by("-pageviews", "path")
    )

    rows = []

    for row in qs:
        path = row["path"] or ""

        if any(path.startswith(prefix) for prefix in ignored_prefixes):
            continue

        rows.append({
            "path": path,
            "unique_visitors": zero_none(row["unique_visitors"]),
            "pageviews": zero_none(row["pageviews"]),
        })

        if len(rows) >= 20:
            break

    return rows


@staff_required
def traffic_stats(request):
    today = timezone.localdate()

    period_raw = request.GET.get("period", "30")
    allowed_periods = {
        "1": 1,
        "7": 7,
        "30": 30,
        "90": 90,
    }

    period_days = allowed_periods.get(period_raw, 30)

    requested_start_day = today - timedelta(days=period_days - 1)
    start_day = max(requested_start_day, TRAFFIC_STATS_PUBLIC_START_DATE)

    visible_days = max(0, (today - start_day).days + 1)
    period_is_clipped = start_day > requested_start_day

    today_summary = get_period_summary(today, today)
    period_summary = get_period_summary(start_day, today)
    daily_rows = get_daily_rows(start_day, today)
    top_pages = get_top_pages(start_day, today)

    return render(
        request,
        "rozesilac/traffic_stats.html",
        {
            "today": today,
            "period_raw": str(period_days),
            "period_days": period_days,
            "requested_start_day": requested_start_day,
            "start_day": start_day,
            "stats_started_on": TRAFFIC_STATS_PUBLIC_START_DATE,
            "visible_days": visible_days,
            "period_is_clipped": period_is_clipped,
            "today_summary": today_summary,
            "period_summary": period_summary,
            "daily_rows": daily_rows,
            "top_pages": top_pages,
        },
    )