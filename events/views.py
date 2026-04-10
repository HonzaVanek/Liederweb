from django.http import Http404
from django.shortcuts import render, redirect, get_object_or_404

from core.decorators import staff_required

from .models import Event, VipReservation
from rozesilac.models import EmailImage, EmailDelivery
from .forms import EventForm

from django.conf import settings
from django.core.mail import send_mail


@staff_required
def event_list(request):
    events = Event.objects.order_by("-starts_at", "-created_at")
    return render(request, "events/event_list.html", {"events": events})


@staff_required
def event_create(request):
    if request.method == "POST":
        form = EventForm(request.POST, request.FILES)
        if form.is_valid():
            event = form.save()
            return redirect("events:event_detail", pk=event.pk)
    else:
        form = EventForm()

    return render(request, "events/event_form.html", {
        "form": form,
        "recent_images": EmailImage.objects.order_by("-uploaded_at")[:8],
        "page_title": "Nový koncert",
    })


@staff_required
def event_edit(request, pk):
    event = get_object_or_404(Event.objects.prefetch_related("campaigns", "vip_reservations"), pk=pk)
    campaigns = event.campaigns.all().order_by("-created_at")
    vip_reservations = event.vip_reservations.all().order_by("-created_at")
    
    if request.method == "POST":
        form = EventForm(request.POST, request.FILES, instance=event)
        if form.is_valid():
            event = form.save()
            return redirect("events:event_detail", pk=event.pk)
    else:
        form = EventForm(instance=event)

    return render(request, "events/event_form.html", {
        "form": form,
        "page_title": "Upravit koncert",
        "recent_images": EmailImage.objects.order_by("-uploaded_at")[:8],
        "campaigns": campaigns,
        "vip_reservations": vip_reservations,
        "event": event,
    })


@staff_required
def event_detail(request, pk):
    event = get_object_or_404(Event, pk=pk)

    return render(request, "events/event_detail.html", {
        "event": event,
    })


def public_event_detail(request, slug):
    event = get_object_or_404(
        Event.objects.select_related("poster_image"),
        slug=slug,
        is_published=True,
    )

    return render(request, "events/public_event_detail.html", {
        "event": event,
        "vip_mode": False,
        "hide_header": True,
        "delivery": None,
        "contact": None,
    })

def vip_event_detail(request, token):
    delivery = get_object_or_404(
        EmailDelivery.objects.select_related("campaign__event", "contact"),
        tracking_token=token,
    )

    event = delivery.campaign.event

    if not event:
        raise Http404("Tato VIP pozvánka není navázaná na žádný koncert.")

    if not event.is_published:
        raise Http404("Tento koncert není veřejně dostupný.")

    return render(request, "events/public_event_detail.html", {
        "event": event,
        "vip_mode": True,
        "delivery": delivery,
        "contact": delivery.contact,
        "hide_header": True,
    })

def vip_reserve(request, token):
    if request.method != "POST":
        raise Http404()

    delivery = get_object_or_404(
        EmailDelivery.objects.select_related("campaign__event", "contact"),
        tracking_token=token,
    )

    event = delivery.campaign.event
    contact = delivery.contact
    campaign = delivery.campaign

    if not event:
        raise Http404("Tato VIP pozvánka není navázaná na žádný koncert.")

    if not event.is_published or not event.vip_enabled:
        raise Http404("VIP rezervace pro tento koncert nejsou dostupné.")

    if not contact:
        raise Http404("Tato VIP rezervace není navázaná na konkrétní kontakt.")

    reservation, created = VipReservation.objects.get_or_create(
        event=event,
        contact=contact,
        defaults={
            "campaign": campaign,
            "delivery": delivery,
        }
    )

    if created:
        subject = f"VIP rezervace: {contact.name or contact.email} – {event.title}"

        body = (
            f"Byla vytvořena nová VIP rezervace.\n\n"
            f"Koncert: {event.title}\n"
            f"{f'Datum koncertu: {event.starts_at:%d.%m.%Y %H:%M}\n' if event.starts_at else ''}"
            f"{f'Místo: {event.venue}\n' if event.venue else ''}"
            f"Jméno: {contact.name or '-'}\n"
            f"Oslovení: {contact.salutation or '-'}\n"
            f"E-mail: {contact.email}\n"
            f"Čas rezervace: {reservation.created_at:%d.%m.%Y %H:%M}\n"
            f"{f'Kampaň: {campaign.subject}\n' if campaign else ''}"
        )

        try:
            send_mail(
                subject=subject,
                message=body,
                from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
                recipient_list=getattr(settings, "VIP_NOTIFICATION_EMAILS", []),
                fail_silently=False,
            )
        except Exception:
            # rezervaci nechceme zrušit jen kvůli tomu, že notifikační mail selhal
            pass

    return redirect("events:vip_reservation_done", token=token)

def vip_reservation_done(request, token):
    delivery = get_object_or_404(
        EmailDelivery.objects.select_related("campaign__event", "contact"),
        tracking_token=token,
    )

    event = delivery.campaign.event

    if not event:
        raise Http404("Tato VIP pozvánka není navázaná na žádný koncert.")

    reservation = VipReservation.objects.filter(
        event=event,
        contact=delivery.contact,
    ).first()

    return render(request, "events/vip_reservation_done.html", {
        "event": event,
        "delivery": delivery,
        "contact": delivery.contact,
        "reservation": reservation,
        "hide_header": True,
    })