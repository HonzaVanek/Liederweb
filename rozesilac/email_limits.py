from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from .models import EmailDelivery


def get_today_bounds():
    now = timezone.localtime()
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = day_start + timedelta(days=1)
    return day_start, day_end


def get_daily_email_usage():
    limit = getattr(settings, "BREVO_DAILY_EMAIL_LIMIT", 300)
    day_start, day_end = get_today_bounds()

    sent = EmailDelivery.objects.filter(
        status="sent",
        sent_at__gte=day_start,
        sent_at__lt=day_end,
    ).count()

    return {
        "limit": limit,
        "sent": sent,
        "remaining": max(limit - sent, 0),
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