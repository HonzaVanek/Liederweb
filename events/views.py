from django.http import Http404, HttpResponse
from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from django.db.models import Prefetch
from django.db import transaction

from core.decorators import staff_required

from .models import (
    Event,
    EventArtist,
    EventProgramItem,
    EventPracticalInfo,
    EventResource,
    EventSponsor,
    EventTicketVariant,
    VipReservation,
    EventGalleryImage,
)

from rozesilac.models import EmailImage, EmailDelivery, EmailCampaign
from .forms import (
    EventForm,
    EventProgramItemFormSet,
    EventArtistFormSet,
    EventResourceFormSet,
    EventPracticalInfoFormSet,
    EventSponsorFormSet,
    VipReservationForm,
    EventTicketSettingsForm,
    EventTicketVariantFormSet,
    InitialEventTicketVariantFormSet,
    EventGalleryImageFormSet,
    get_default_ticket_variant_initials,
)

from media_assets.models import MediaAsset

from .services.ticket_pdf import build_event_ticket_pdf, build_ticket_pdf_filename

from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone
from django.views.decorators.http import require_POST

from openpyxl import Workbook
from openpyxl.styles import Font
from datetime import datetime

import logging

security_logger = logging.getLogger("liederweb.security")


def _token_prefix(token):
    return str(token)[:8] if token else "-"


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
        "gallery_formset": EventGalleryImageFormSet(
            data=data,
            instance=instance,
            prefix="gallery",
        ),
    }


def _get_recent_event_images():
    return MediaAsset.objects.filter(
        asset_type=MediaAsset.AssetType.IMAGE,
        is_active=True,
    ).order_by("-uploaded_at")[:10]

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
        "recent_images": _get_recent_event_images(),
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
        "recent_images": _get_recent_event_images(),
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
            "ticket_settings",
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
            Prefetch(
                "ticket_variants",
                queryset=EventTicketVariant.objects.order_by("sort_order", "id"),
            ),
        ),
        pk=pk,
    )

    related_content_posts = (event.content_posts.select_related("cover_image").order_by("-published_at", "-created_at"))
    campaigns = event.campaigns.all()
    vip_reservations = event.vip_reservations.all()
    ticket_settings = event.ticket_settings if hasattr(event, "ticket_settings") else None
    ticket_variants = event.ticket_variants.all()
    active_vip_reservations_count = event.vip_reservations.filter(status="active").count()
    active_vip_tickets_count = sum(
        r.ticket_count for r in event.vip_reservations.all() if r.status == "active"
    )

    return render(
        request,
        "events/event_detail.html",
        {
            "event": event,
            "campaigns": campaigns,
            "vip_reservations": vip_reservations,
            "ticket_settings": ticket_settings,
            "ticket_variants": ticket_variants,
            "active_vip_reservations_count": active_vip_reservations_count,
            "active_vip_tickets_count": active_vip_tickets_count,
            "related_content_posts": related_content_posts,
        },
    )


def public_event_detail(request, slug):
    Prefetch(
        "gallery_images",
        queryset=EventGalleryImage.objects.select_related("image_asset").order_by("sort_order", "id"),
    ),
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

    related_content_posts = (
        event.content_posts
        .filter(is_published=True)
        .select_related("cover_image")
        .order_by("-published_at", "-created_at")
    )

    gallery_images = list(event.gallery_images.all())

    if len(gallery_images) > 4:
        gallery_preview_images = gallery_images[:5]
    else:
        gallery_preview_images = gallery_images[:4]

    gallery_extra_count = max(len(gallery_images) - 4, 0)

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
            "gallery_images": gallery_images,
            "gallery_preview_images": gallery_preview_images,
            "gallery_extra_count": gallery_extra_count,
            "related_content_posts": related_content_posts,
        },
    )

def vip_event_detail(request, token):
    delivery = (
        EmailDelivery.objects
        .select_related("campaign__event", "contact")
        .filter(tracking_token=token)
        .first()
    )

    if not delivery:
        security_logger.warning(
            "Invalid VIP token on detail | token_prefix=%s | path=%s",
            _token_prefix(token),
            request.path,
        )
        raise Http404("VIP pozvánka nebyla nalezena.")

    event = delivery.campaign.event

    if not event:
        security_logger.warning(
            "VIP token without event | token_prefix=%s | delivery_id=%s | path=%s",
            _token_prefix(token),
            delivery.id,
            request.path,
        )
        raise Http404("Tato VIP pozvánka není navázaná na žádný koncert.")

    if not event.is_published:
        security_logger.warning(
            "VIP token for unpublished event | token_prefix=%s | delivery_id=%s | event_id=%s | path=%s",
            _token_prefix(token),
            delivery.id,
            event.id,
            request.path,
        )
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

    delivery = (
        EmailDelivery.objects
        .select_related("campaign__event", "contact")
        .filter(tracking_token=token)
        .first()
    )

    if not delivery:
        security_logger.warning(
            "Invalid VIP token on reserve | token_prefix=%s | path=%s",
            _token_prefix(token),
            request.path,
        )
        raise Http404("VIP pozvánka nebyla nalezena.")

    event = delivery.campaign.event
    contact = delivery.contact
    campaign = delivery.campaign

    if not event:
        security_logger.warning(
            "VIP reserve without event | token_prefix=%s | delivery_id=%s | path=%s",
            _token_prefix(token),
            delivery.id,
            request.path,
        )
        raise Http404("Tato VIP pozvánka není navázaná na žádný koncert.")

    if not event.is_published or not event.vip_enabled:
        security_logger.warning(
            "VIP reserve denied for unavailable event | token_prefix=%s | delivery_id=%s | event_id=%s | published=%s | vip_enabled=%s | path=%s",
            _token_prefix(token),
            delivery.id,
            event.id,
            event.is_published,
            event.vip_enabled,
            request.path,
        )
        raise Http404("VIP rezervace pro tento koncert nejsou dostupné.")

    if not contact:
        security_logger.warning(
            "VIP reserve without contact | token_prefix=%s | delivery_id=%s | event_id=%s | path=%s",
            _token_prefix(token),
            delivery.id,
            event.id,
            request.path,
        )
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
            "hide_header": True,
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
            status="active",
            cancelled_at=None,
        )
    else:
        reservation.ticket_count = ticket_count
        reservation.status = "active"
        reservation.cancelled_at = None
        if not reservation.campaign:
            reservation.campaign = campaign
        if not reservation.delivery:
            reservation.delivery = delivery
        reservation.save(update_fields=["ticket_count", "campaign", "delivery", "status", "cancelled_at"])

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
            security_logger.exception(
                "VIP reservation notification email failed | token_prefix=%s | delivery_id=%s | event_id=%s | reservation_id=%s",
                _token_prefix(token),
                delivery.id,
                event.id,
                reservation.id,
            )

    return redirect("events:vip_reservation_done", token=token)

def vip_reservation_done(request, token):
    delivery = (
        EmailDelivery.objects
        .select_related("campaign__event", "contact")
        .filter(tracking_token=token)
        .first()
    )

    if not delivery:
        security_logger.warning(
            "Invalid VIP token on reservation_done | token_prefix=%s | path=%s",
            _token_prefix(token),
            request.path,
        )
        raise Http404("VIP pozvánka nebyla nalezena.")

    event = delivery.campaign.event

    if not event:
        security_logger.warning(
            "VIP reservation_done without event | token_prefix=%s | delivery_id=%s | path=%s",
            _token_prefix(token),
            delivery.id,
            request.path,
        )
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


@require_POST
def vip_cancel_reservation(request, token):
    delivery = get_object_or_404(
        EmailDelivery.objects.select_related("campaign__event", "contact"),
        tracking_token=token,
    )

    event = delivery.campaign.event
    contact = delivery.contact

    if not event or not contact:
        raise Http404()

    reservation = get_object_or_404(
        VipReservation,
        event=event,
        contact=contact,
    )

    reservation.status = "cancelled"
    reservation.cancelled_at = timezone.now()
    reservation.save(update_fields=["status", "cancelled_at"])

    return redirect("events:vip_event_detail", token=token)

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
    headers = ["Jméno", "Email", "Oslovení", "Počet vstupenek", "Stav", "Zrušeno", "Čas rezervace", "Kampaň"]
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
            r.get_status_display(),
            r.cancelled_at.strftime("%d.%m.%Y %H:%M") if r.cancelled_at else "",
            r.created_at.strftime("%d.%m.%Y %H:%M"),
            r.campaign.subject if r.campaign else "",
        ])

    # trochu lepší šířky sloupců
    column_widths = [25, 30, 30, 18, 22, 20, 20, 30]
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

@staff_required
def event_tickets(request, pk):
    event = get_object_or_404(
        Event.objects.select_related("ticket_settings").prefetch_related(
            Prefetch(
                "artists",
                queryset=EventArtist.objects.order_by("sort_order", "id"),
            ),
            Prefetch(
                "ticket_variants",
                queryset=EventTicketVariant.objects.order_by("sort_order", "id"),
            ),
        ),
        pk=pk,
    )

    settings_instance = getattr(event, "ticket_settings", None)
    variant_queryset = event.ticket_variants.all()
    has_existing_variants = variant_queryset.exists()

    VariantFormSetClass = (
        EventTicketVariantFormSet
        if has_existing_variants
        else InitialEventTicketVariantFormSet
    )

    if request.method == "POST":
        settings_form = EventTicketSettingsForm(
            request.POST,
            request.FILES,
            instance=settings_instance,
            event=event,
            prefix="ticket_settings",
        )
        variant_formset = VariantFormSetClass(
            request.POST,
            instance=event,
            queryset=variant_queryset,
            prefix="variants",
        )

        if settings_form.is_valid() and variant_formset.is_valid():
            with transaction.atomic():
                ticket_settings = settings_form.save(commit=False)
                ticket_settings.event = event
                ticket_settings.save()

                variant_formset.instance = event
                variant_formset.save()

            messages.success(request, "Nastavení vstupenek bylo uloženo.")
            return redirect("events:event_tickets", pk=event.pk)

        messages.error(request, "Formulář se nepodařilo uložit. Zkontroluj chyby níže.")

    else:
        settings_form = EventTicketSettingsForm(
            instance=settings_instance,
            event=event,
            prefix="ticket_settings",
        )

        if has_existing_variants:
            variant_formset = VariantFormSetClass(
                instance=event,
                queryset=variant_queryset,
                prefix="variants",
            )
        else:
            variant_formset = VariantFormSetClass(
                instance=event,
                queryset=variant_queryset,
                initial=get_default_ticket_variant_initials(),
                prefix="variants",
            )

    return render(
        request,
        "events/event_tickets.html",
        {
            "event": event,
            "settings_form": settings_form,
            "variant_formset": variant_formset,
            "recent_images": EmailImage.objects.order_by("-uploaded_at")[:10],
        },
    )

@staff_required
def event_ticket_pdf(request, pk, variant_code):
    event = get_object_or_404(
        Event.objects.select_related("ticket_settings").prefetch_related(
            Prefetch(
                "ticket_variants",
                queryset=EventTicketVariant.objects.order_by("sort_order", "id"),
            ),
            Prefetch(
                "artists",
                queryset=EventArtist.objects.order_by("sort_order", "id"),
            ),
        ),
        pk=pk,
    )

    ticket_settings = getattr(event, "ticket_settings", None)
    if not ticket_settings:
        messages.error(request, "Tento koncert ještě nemá nastavení vstupenek.")
        return redirect("events:event_tickets", pk=event.pk)

    variant = event.ticket_variants.filter(code=variant_code).first()
    if not variant:
        messages.error(request, "Požadovaná varianta vstupenky nebyla nalezena.")
        return redirect("events:event_tickets", pk=event.pk)

    if not variant.is_active:
        messages.error(request, "Tato varianta vstupenky není aktivní.")
        return redirect("events:event_tickets", pk=event.pk)

    try:
        pdf_bytes = build_event_ticket_pdf(event=event, variant=variant)
    except Exception:
        security_logger.exception(
            "Ticket PDF generation failed | event_id=%s | variant_code=%s | user_id=%s",
            event.id,
            variant_code,
            request.user.id if request.user.is_authenticated else None,
        )
        messages.error(request, "PDF vstupenek se nepodařilo vygenerovat.")
        return redirect("events:event_tickets", pk=event.pk)

    filename = build_ticket_pdf_filename(event, variant)

    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response





# veřejná stránka koncerty v MENU nahoře #

def public_event_list(request):
    now = timezone.now()

    base_qs = (
        Event.objects
        .filter(is_published=True, starts_at__isnull=False)
        .select_related(
            "poster_image",
            "poster_asset",
        )
    )

    upcoming_events = list(
        base_qs
        .filter(starts_at__gte=now)
        .order_by("starts_at", "created_at")
    )

    featured_event = upcoming_events[0] if upcoming_events else None
    other_upcoming_events = upcoming_events[1:] if len(upcoming_events) > 1 else []

    past_events = (
        base_qs
        .filter(starts_at__lt=now)
        .order_by("-starts_at", "-created_at")
    )

    return render(
        request,
        "events/public_event_list.html",
        {
            "featured_event": featured_event,
            "other_upcoming_events": other_upcoming_events,
            "past_events": past_events,
        },
    )