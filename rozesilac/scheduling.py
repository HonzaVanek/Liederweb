from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from .models import EmailCampaign


def get_scheduled_campaign_min_gap_minutes():
    return int(getattr(settings, "NEWSLETTER_SCHEDULED_CAMPAIGN_MIN_GAP_MINUTES", 5))


def get_min_allowed_scheduled_at():
    return timezone.now() + timedelta(minutes=get_scheduled_campaign_min_gap_minutes())


def find_scheduled_campaign_conflict(scheduled_at, exclude_campaign_id=None):
    """
    Vrátí existující scheduled kampaň, která je příliš blízko zvolenému času.

    Přesně 5 minut rozdíl je povolený.
    Méně než 5 minut rozdíl je konflikt.
    """
    min_gap_minutes = get_scheduled_campaign_min_gap_minutes()

    window_start = scheduled_at - timedelta(minutes=min_gap_minutes)
    window_end = scheduled_at + timedelta(minutes=min_gap_minutes)

    qs = EmailCampaign.objects.filter(
        status="scheduled",
        is_test=False,
        scheduled_at__isnull=False,
        scheduled_at__gt=window_start,
        scheduled_at__lt=window_end,
    ).order_by("scheduled_at", "id")

    if exclude_campaign_id:
        qs = qs.exclude(id=exclude_campaign_id)

    return qs.first()