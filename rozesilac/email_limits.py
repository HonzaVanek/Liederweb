from datetime import timedelta

from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from .models import EmailDelivery


def get_daily_email_limit():
    return int(getattr(settings, "BREVO_DAILY_EMAIL_LIMIT", 300))


def get_day_bounds(day=None):
    if day is None:
        day = timezone.localtime()
    else:
        day = timezone.localtime(day)

    day_start = day.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = day_start + timedelta(days=1)

    return day_start, day_end


def get_today_bounds():
    return get_day_bounds()


def get_sent_email_count_for_day(day=None):
    day_start, day_end = get_day_bounds(day)

    return EmailDelivery.objects.filter(
        status="sent",
        sent_at__gte=day_start,
        sent_at__lt=day_end,
    ).count()


def get_reserved_queued_email_count_for_day(day=None, exclude_campaign_id=None):
    """
    Počítá queued e-maily, které už mají v daný den rezervovanou kapacitu.

    Zahrnuje:
    - naplánované kampaně podle scheduled_at,
    - právě běžící kampaně podle started_at.

    Nezahrnuje sent, protože ty se počítají zvlášť podle sent_at.
    """
    day_start, day_end = get_day_bounds(day)

    qs = EmailDelivery.objects.filter(
        status="queued",
        campaign__is_test=False,
    ).filter(
        Q(
            campaign__status="scheduled",
            campaign__scheduled_at__gte=day_start,
            campaign__scheduled_at__lt=day_end,
        )
        |
        Q(
            campaign__status="sending",
            campaign__started_at__gte=day_start,
            campaign__started_at__lt=day_end,
        )
    )

    if exclude_campaign_id:
        qs = qs.exclude(campaign_id=exclude_campaign_id)

    return qs.count()


def get_daily_email_usage(day=None, exclude_campaign_id=None):
    limit = get_daily_email_limit()
    day_start, day_end = get_day_bounds(day)

    sent = get_sent_email_count_for_day(day)
    reserved = get_reserved_queued_email_count_for_day(
        day,
        exclude_campaign_id=exclude_campaign_id,
    )

    used_or_reserved = sent + reserved

    return {
        "limit": limit,
        "sent": sent,
        "reserved": reserved,
        "used_or_reserved": used_or_reserved,
        "remaining": max(limit - used_or_reserved, 0),
        "day_start": day_start,
        "day_end": day_end,
    }


def get_email_count_for_send_form(cleaned_data):
    send_mode = cleaned_data.get("send_mode")

    if send_mode == "test":
        return 1

    contacts = cleaned_data.get("contacts")
    if not contacts:
        return 0

    return contacts.count()


def can_fit_email_count_in_day(email_count, day=None, exclude_campaign_id=None):
    usage = get_daily_email_usage(day, exclude_campaign_id=exclude_campaign_id)

    return {
        "ok": email_count <= usage["remaining"],
        "email_count": email_count,
        **usage,
    }