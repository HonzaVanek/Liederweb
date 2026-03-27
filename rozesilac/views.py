from django.shortcuts import render
from core.decorators import staff_required
from .models import Contact, EmailCampaign, EmailDelivery, EmailClickEvent
from django.db.models import Prefetch

# Create your views here.

@staff_required
def dashboard(request):
    cards = [
        {"title": "Šablony", "desc": "Vytvořit a upravit HTML šablony emailů.", "url": "rozesilac_templates"},
        {"title": "Kontakty", "desc": "Správa kontaktů + import z XLSX.", "url": "rozesilac_contacts"},
        {"title": "Odeslat", "desc": "Vybrat šablonu, příjemce a odeslat.", "url": "rozesilac_send"},
        {"title": "Kampaně", "desc": "Historie rozesílek, výsledky a chyby.", "url": "rozesilac_campaigns"},
    ]
    contacts_total = Contact.objects.count()
    active_contacts_total = Contact.objects.filter(is_active=True).count()
    campaigns_total = EmailCampaign.objects.count()
    deliveries_total = EmailDelivery.objects.count()
    sent_deliveries_total = EmailDelivery.objects.filter(status="sent").count()

    campaigns = (
        EmailCampaign.objects
        .select_related("template", "created_by")
        .prefetch_related("deliveries__click_events")
        .order_by("-created_at")
    )

    campaign_stats = []

    for campaign in campaigns:
        deliveries = list(campaign.deliveries.all())

        sent_count = sum(1 for d in deliveries if d.status == "sent")
        failed_count = sum(1 for d in deliveries if d.status == "failed")
        queued_count = sum(1 for d in deliveries if d.status == "queued")

        clicked_delivery_count = 0
        confirmed_unique_click_count_total = 0

        for delivery in deliveries:
            human_events = [e for e in delivery.click_events.all() if not e.is_suspected_bot]
            unique_urls = set(e.original_url for e in human_events)

            if unique_urls:
                clicked_delivery_count += 1
                confirmed_unique_click_count_total += len(unique_urls)

        click_rate_percent = round((clicked_delivery_count / sent_count) * 100, 1) if sent_count else 0
        click_rate_width = max(0, min(100, int(round(click_rate_percent))))

        campaign.sent_count_for_ui = sent_count
        campaign.failed_count_for_ui = failed_count
        campaign.queued_count_for_ui = queued_count
        campaign.clicked_delivery_count_for_ui = clicked_delivery_count
        campaign.confirmed_unique_click_count_total_for_ui = confirmed_unique_click_count_total
        campaign.click_rate_percent_for_ui = click_rate_percent
        campaign.click_rate_width_for_ui = click_rate_width

        campaign_stats.append(campaign)

    latest_campaign = campaign_stats[0] if campaign_stats else None

    top_campaigns = sorted(
        campaign_stats,
        key=lambda c: (
            c.confirmed_unique_click_count_total_for_ui,
            c.clicked_delivery_count_for_ui,
            c.created_at,
        ),
        reverse=True,
    )[:5]

    recent_campaigns = campaign_stats[:8]

    # --------------------------------------------------
    # Statistiky kontaktů
    # --------------------------------------------------

    contacts = list(Contact.objects.prefetch_related("groups").all())
    contact_emails = [c.email for c in contacts]

    deliveries_for_contacts = (
        EmailDelivery.objects
        .filter(to_email__in=contact_emails)
        .prefetch_related(
            Prefetch(
                "click_events",
                queryset=EmailClickEvent.objects.order_by("created_at"),
            )
        )
    )

    deliveries_by_email = {}
    for d in deliveries_for_contacts:
        deliveries_by_email.setdefault(d.to_email, []).append(d)

    for c in contacts:
        contact_deliveries = deliveries_by_email.get(c.email, [])
        c.delivery_count_for_ui = len(contact_deliveries)

        confirmed_unique_click_count = 0
        clicked_campaigns_count = 0
        last_human_click_at = None

        for d in contact_deliveries:
            human_events = [e for e in d.click_events.all() if not e.is_suspected_bot]
            unique_urls = set(e.original_url for e in human_events)

            confirmed_unique_click_count += len(unique_urls)

            if unique_urls:
                clicked_campaigns_count += 1

            if human_events:
                event_last = human_events[-1].created_at
                if last_human_click_at is None or event_last > last_human_click_at:
                    last_human_click_at = event_last

        c.confirmed_unique_click_count_for_ui = confirmed_unique_click_count
        c.clicked_campaigns_count_for_ui = clicked_campaigns_count
        c.last_human_click_at_for_ui = last_human_click_at

    top_contacts = sorted(
        contacts,
        key=lambda c: (
            c.confirmed_unique_click_count_for_ui,
            c.clicked_campaigns_count_for_ui,
            c.delivery_count_for_ui,
        ),
        reverse=True,
    )[:10]

    max_recent_click_rate = max(
        [c.click_rate_percent_for_ui for c in recent_campaigns],
        default=0,
    )

    return render(
        request,
        "rozesilac/dashboard.html",
        {
            "contacts_total": contacts_total,
            "active_contacts_total": active_contacts_total,
            "campaigns_total": campaigns_total,
            "deliveries_total": deliveries_total,
            "sent_deliveries_total": sent_deliveries_total,
            "latest_campaign": latest_campaign,
            "top_campaigns": top_campaigns,
            "top_contacts": top_contacts,
            "recent_campaigns": recent_campaigns,
            "max_recent_click_rate": max_recent_click_rate,
            "cards": cards,
        },
    )


@staff_required
def templates(request):
    return render(request, "rozesilac/templates_list.html")

@staff_required
def contacts(request):
    return render(request, "rozesilac/contacts.html")

@staff_required
def images(request):
    return render(request, "rozesilac/images.html")

@staff_required
def send(request):
    return render(request, "rozesilac/send.html")

@staff_required
def campaigns(request):
    return render(request, "rozesilac/campaigns.html")