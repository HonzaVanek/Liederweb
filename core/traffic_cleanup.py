from django.db.models import Sum

from .models import (
    DailySiteVisitor,
    DailyPageVisitor,
    DailySiteTraffic,
    DailyPageTraffic,
    DailyEngagedVisitor,
)


def cleanup_visitor_human_stats(
    day,
    visitor_hash,
    *,
    delete_engaged=True,
):
    page_rows = list(
        DailyPageVisitor.objects
        .filter(
            day=day,
            visitor_hash=visitor_hash,
        )
        .values("path")
        .annotate(pageviews=Sum("pageviews"))
    )

    total_pageviews = sum(
        row["pageviews"] or 0
        for row in page_rows
    )

    if delete_engaged:
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

    site_traffic = DailySiteTraffic.objects.filter(
        day=day,
    ).first()

    if site_traffic:
        site_traffic.human_hits = max(
            site_traffic.human_hits - total_pageviews,
            0,
        )
        site_traffic.bot_hits += total_pageviews
        site_traffic.save(
            update_fields=[
                "human_hits",
                "bot_hits",
            ]
        )

    for row in page_rows:
        path = row["path"]
        count = row["pageviews"] or 0

        page_traffic = DailyPageTraffic.objects.filter(
            day=day,
            path=path,
        ).first()

        if page_traffic:
            page_traffic.human_hits = max(
                page_traffic.human_hits - count,
                0,
            )
            page_traffic.bot_hits += count
            page_traffic.save(
                update_fields=[
                    "human_hits",
                    "bot_hits",
                ]
            )

    return total_pageviews