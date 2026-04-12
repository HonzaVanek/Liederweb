from django.http import Http404, HttpResponse
from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from django.db.models import Prefetch

from core.decorators import staff_required

from .models import (
    Event,
    EventArtist,
    EventProgramItem,
    EventPracticalInfo,
    EventResource,
    EventSponsor,
    VipReservation,
)

from rozesilac.models import EmailImage, EmailDelivery, EmailCampaign
from .forms import (EventForm,EventProgramItemFormSet, EventArtistFormSet, EventResourceFormSet, EventPracticalInfoFormSet, EventSponsorFormSet, VipReservationForm,)

from django.conf import settings
from django.core.mail import send_mail

from openpyxl import Workbook
from openpyxl.styles import Font
from datetime import datetime


def _build_event_formsets(data=None, instance=None):
    return {
        "program_formset": EventProgramItemFormSet(
            data=data,
            instance=instance,
            prefix="program",
        ),
        "artist_formset": EventArtistFormSet(
            data=data,
            instance=instance,
            prefix="artists",
        ),
        "resource_formset": EventResourceFormSet(
            data=data,
            instance=instance,
            prefix="resources",
        ),
        "practical_info_formset": EventPracticalInfoFormSet(
            data=data,
            instance=instance,
            prefix="practical",
        ),
        "sponsor_formset": EventSponsorFormSet(
            data=data,
            instance=instance,
            prefix="sponsors",
        ),
    }


@staff_required
def event_list(request):
    events = Event.objects.order_by("-starts_at", "-created_at")
    return render(request, "events/event_list.html", {"events": events})


@staff_required
def event_create(request):
    event = Event()

    if request.method == "POST":
        form = EventForm(request.POST, request.FILES, instance=event)
        formsets = _build_event_formsets(data=request.POST, instance=event)

        form_valid = form.is_valid()

        formset_validity = {}
        for name, fs in formsets.items():
            formset_validity[name] = fs.is_valid()

        if form_valid and all(formset_validity.values()):
            event = form.save()

            for formset in formsets.values():
                formset.instance = event
                formset.save()

            messages.success(request, "Koncert byl vytvořen.")
            return redirect("events:event_detail", pk=event.pk)

        print("MAIN FORM ERRORS:", form.errors)
        for name, fs in formsets.items():
            print(f"{name} VALID:", formset_validity[name])
            print(f"{name} ERRORS:", fs.errors)
            print(f"{name} NON_FORM_ERRORS:", fs.non_form_errors())

        messages.error(request, "Formulář se nepodařilo uložit. Zkontroluj chyby níže.")

    else:
        form = EventForm(instance=event)
        formsets = _build_event_formsets(instance=event)

    context = {
        "form": form,
        "page_title": "Nový koncert",
        "recent_images": EmailImage.objects.order_by("-uploaded_at")[:8],
        "event": None,
        **formsets,
    }
    return render(request, "events/event_form.html", context)


@staff_required
def event_edit(request, pk):
    event = get_object_or_404(Event, pk=pk)

    if request.method == "POST":
        form = EventForm(request.POST, request.FILES, instance=event)
        formsets = _build_event_formsets(data=request.POST, instance=event)

        form_valid = form.is_valid()

        formset_validity = {}
        for name, fs in formsets.items():
            formset_validity[name] = fs.is_valid()

        if form_valid and all(formset_validity.values()):
            event = form.save()

            for formset in formsets.values():
                formset.instance = event
                formset.save()

            messages.success(request, "Koncert byl upraven.")
            return redirect("events:event_detail", pk=event.pk)

        print("MAIN FORM ERRORS:", form.errors)
        for name, fs in formsets.items():
            print(f"{name} VALID:", formset_validity[name])
            print(f"{name} ERRORS:", fs.errors)
            print(f"{name} NON_FORM_ERRORS:", fs.non_form_errors())

        messages.error(request, "Formulář se nepodařilo uložit. Zkontroluj chyby níže.")

    else:
        form = EventForm(instance=event)
        formsets = _build_event_formsets(instance=event)

    context = {
        "form": form,
        "page_title": "Upravit koncert",
        "recent_images": EmailImage.objects.order_by("-uploaded_at")[:8],
        "event": event,
        **formsets,
    }
    return render(request, "events/event_form.html", context)


@staff_required
def event_detail(request, pk):
    event = get_object_or_404(
        Event.objects.select_related(
            "poster_image",
            "hero_image",
            "secondary_image",
        ).prefetch_related(
            Prefetch(
                "campaigns",
                queryset=EmailCampaign.objects.order_by("-created_at"),
            ),
            Prefetch(
                "vip_reservations",
                queryset=VipReservation.objects.select_related(
                    "contact",
                    "campaign",
                    "delivery",
                ).order_by("-created_at"),
            ),
            Prefetch(
                "program_items",
                queryset=EventProgramItem.objects.order_by("sort_order", "id"),
            ),
            Prefetch(
                "artists",
                queryset=EventArtist.objects.select_related("photo_image").order_by("sort_order", "id"),
            ),
            Prefetch(
                "resources",
                queryset=EventResource.objects.order_by("sort_order", "id"),
            ),
            Prefetch(
                "practical_infos",
                queryset=EventPracticalInfo.objects.order_by("sort_order", "id"),
            ),
            Prefetch(
                "sponsors",
                queryset=EventSponsor.objects.select_related("logo_image").order_by("sort_order", "id"),
            ),
        ),
        pk=pk,
    )

    campaigns = event.campaigns.all()
    vip_reservations = event.vip_reservations.all()

    return render(
        request,
        "events/event_detail.html",
        {
            "event": event,
            "campaigns": campaigns,
            "vip_reservations": vip_reservations,
        },
    )


def public_event_detail(request, slug):
    event = get_object_or_404(
        Event.objects.select_related(
            "poster_image",
            "hero_image",
            "secondary_image",
        ).prefetch_related(
            "program_items",
            "artists",
            "resources",
            "practical_infos",
            "sponsors__logo_image",
        ),
        slug=slug,
        is_published=True,
    )

    return render(
        request,
        "events/public_event_detail.html",
        {
            "event": event,
            "vip_mode": False,
            "hide_header": True,
            "delivery": None,
            "contact": None,
            "reservation": None,
            "vip_form": None,
        },
    )

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

    reservation = None
    if delivery.contact:
        reservation = VipReservation.objects.filter(
            event=event,
            contact=delivery.contact,
        ).first()

    initial_ticket_count = reservation.ticket_count if reservation else 1
    vip_form = VipReservationForm(initial={"ticket_count": initial_ticket_count})

    return render(request, "events/public_event_detail.html", {
        "event": event,
        "vip_mode": True,
        "delivery": delivery,
        "contact": delivery.contact,
        "reservation": reservation,
        "vip_form": vip_form,
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

    form = VipReservationForm(request.POST)
    if not form.is_valid():
        return render(request, "events/public_event_detail.html", {
            "event": event,
            "vip_mode": True,
            "delivery": delivery,
            "contact": contact,
            "reservation": VipReservation.objects.filter(event=event, contact=contact).first(),
            "vip_form": form,
        })

    ticket_count = form.cleaned_data["ticket_count"]

    reservation = VipReservation.objects.filter(event=event, contact=contact).first()
    created = reservation is None

    if created:
        reservation = VipReservation.objects.create(
            event=event,
            contact=contact,
            campaign=campaign,
            delivery=delivery,
            ticket_count=ticket_count,
        )
    else:
        reservation.ticket_count = ticket_count
        if not reservation.campaign:
            reservation.campaign = campaign
        if not reservation.delivery:
            reservation.delivery = delivery
        reservation.save(update_fields=["ticket_count", "campaign", "delivery"])

    if created:
        subject = f"VIP rezervace: {contact.name or contact.email} – {event.title}"

        lines = [
            "Byla vytvořena nová VIP rezervace.",
            "",
            f"Koncert: {event.title}",
        ]

        if event.starts_at:
            lines.append(f"Datum koncertu: {event.starts_at:%d.%m.%Y %H:%M}")

        if event.venue:
            lines.append(f"Místo: {event.venue}")

        lines.extend([
            f"Jméno: {contact.name or '-'}",
            f"Oslovení: {contact.salutation or '-'}",
            f"E-mail: {contact.email}",
            f"Počet vstupenek: {reservation.ticket_count}",
            f"Čas rezervace: {reservation.created_at:%d.%m.%Y %H:%M}",
        ])

        if campaign:
            lines.append(f"Kampaň: {campaign.subject}")

        body = "\n".join(lines)

        try:
            send_mail(
                subject=subject,
                message=body,
                from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
                recipient_list=getattr(settings, "VIP_NOTIFICATION_EMAILS", ["info@lieder-society.cz"]),
                fail_silently=False,
            )
        except Exception:
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


@staff_required
def event_export_vip_xlsx(request, pk):
    event = get_object_or_404(Event, pk=pk)

    reservations = (
        event.vip_reservations
        .select_related("contact", "campaign")
        .order_by("created_at")
    )

    wb = Workbook()
    ws = wb.active
    ws.title = "VIP rezervace"

    # hlavička
    headers = ["Jméno", "Email", "Oslovení", "Počet vstupenek", "Čas rezervace", "Kampaň"]
    ws.append(headers)

    # bold header
    for cell in ws[1]:
        cell.font = Font(bold=True)

    # data
    for r in reservations:
        ws.append([
            r.contact.name or "",
            r.contact.email,
            r.contact.salutation or "",
            r.ticket_count,
            r.created_at.strftime("%d.%m.%Y %H:%M"),
            r.campaign.subject if r.campaign else "",
        ])

    # trochu lepší šířky sloupců
    column_widths = [25, 30, 30, 18, 20, 30]
    for i, width in enumerate(column_widths, start=1):
        ws.column_dimensions[chr(64 + i)].width = width

    # response
    filename = f"vip_rezervace_{event.slug}.xlsx"

    response = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response["Content-Disposition"] = f'attachment; filename="{filename}"'

    wb.save(response)
    return response