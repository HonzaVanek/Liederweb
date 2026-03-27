from django.db import IntegrityError
from django.http import HttpResponseForbidden
from django.urls import reverse
from django.shortcuts import get_object_or_404, render
from core.decorators import staff_required
from .models import Contact, EmailCampaign, EmailDelivery, EmailClickEvent, EmailTemplate, EmailImage, ContactGroup
from django.db.models import OuterRef, Sum, Exists
from django.db.models.deletion import ProtectedError
from django.db.models import Prefetch
from .forms import EmailTemplateForm, EmailImageUploadForm, ContactForm, ContactImportForm, ContactGroupForm
from django.contrib import messages
from django.shortcuts import redirect
from openpyxl import load_workbook, Workbook
from django.core.validators import validate_email
from django.core.exceptions import ValidationError

# Create your views here.

@staff_required
def dashboard(request):
    cards = [
        {"title": "Šablony", "desc": "Vytvořit a upravit HTML šablony emailů.", "url": reverse("rozesilac:templates")},
        {"title": "Kontakty", "desc": "Správa kontaktů + import z XLSX.", "url": reverse("rozesilac:contacts")},
        {"title": "Odeslat", "desc": "Vybrat šablonu, příjemce a odeslat.", "url": reverse("rozesilac:send")},
        {"title": "Kampaně", "desc": "Historie rozesílek, výsledky a chyby.", "url": reverse("rozesilac:campaigns")},
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
    templates = EmailTemplate.objects.order_by("-updated_at", "name")
    return render(request, "rozesilac/templates_list.html", {"templates": templates})

@staff_required
def template_create(request):
    if request.method == "POST":
        form = EmailTemplateForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Šablona byla vytvořena.")
            return redirect("rozesilac:templates")
    else:
        form = EmailTemplateForm()

    recent_images = EmailImage.objects.all()[:4]
    total_size = EmailImage.objects.aggregate(total=Sum("file_size"))["total"] or 0
    limit_size = 100 * 1024 * 1024
    image_upload_form = EmailImageUploadForm()

    return render(request, "rozesilac/template_create.html", {
            "form": form,
            "page_title": "Nová šablona",
            "submit_label": "Vytvořit šablonu",
            "recent_images": recent_images,
            "total_size": total_size,
            "limit_size": limit_size,
            "image_upload_form": image_upload_form,
        },)

@staff_required
def template_edit(request, template_id):
        template_obj = get_object_or_404(EmailTemplate, id=template_id)

        if request.method == "POST":
            form = EmailTemplateForm(request.POST, instance=template_obj)
            if form.is_valid():
                form.save()
                messages.success(request, "Šablona byla upravena.")
                return redirect("rozesilac:templates")
        else:
            form = EmailTemplateForm(instance=template_obj)

        recent_images = EmailImage.objects.all()[:4]
        total_size = EmailImage.objects.aggregate(total=Sum("file_size"))["total"] or 0
        limit_size = 100 * 1024 * 1024
        image_upload_form = EmailImageUploadForm()
        return render(request, "rozesilac/template_edit.html",
                      {
                        "form": form,
                        "page_title": f"Upravit šablonu: {template_obj.name}",
                        "submit_label": "Uložit změny",
                        "template_obj": template_obj,
                        "recent_images": recent_images,
                        "total_size": total_size,
                        "limit_size": limit_size,
                        "image_upload_form": image_upload_form,
                     },)

@staff_required
def template_duplicate(request, template_id):
    template_obj = get_object_or_404(EmailTemplate, id=template_id)

    if request.method == "POST":
        base_name = f"{template_obj.name} (kopie)"
        new_name = base_name
        counter = 2

        while EmailTemplate.objects.filter(name=new_name).exists():
            new_name = f"{base_name} {counter}"
            counter += 1

        new_template = EmailTemplate.objects.create(
            name=new_name,
            subject=template_obj.subject,
            preheader=template_obj.preheader,
            html_body=template_obj.html_body,
            text_body=template_obj.text_body,
        )

        messages.success(request, f'Šablona byla zduplikována jako "{new_template.name}".')
        return redirect("rozesilac:templates")

    return render(request, "rozesilac/template_duplicate.html", {"template_obj": template_obj},)

@staff_required
def template_delete(request, template_id):
    template_obj = get_object_or_404(EmailTemplate, id=template_id)

    if request.method == "POST":
        try:
            template_obj.delete()
            messages.success(request, "Šablona byla smazána.")
        except ProtectedError:
            messages.error(
                request,
                "Tuto šablonu nelze smazat, protože už byla použita v odeslané kampani. "
                "Potřebujeme, aby historie kampaní zůstala zachována a tohle by nám rozmrdalo ty historické statistiky. Jestli tě existence té šablony sere fakt hodně, napiš mi a nějak to pořešíme :)"
            )
        return redirect("rozesilac:templates")
    return render(request, "rozesilac/template_delete.html", {"template_obj": template_obj},)


def get_contact_salutation(contact):
    if contact.salutation and contact.salutation.strip():
        return contact.salutation.strip()
    if contact.name and contact.name.strip():
        return contact.name.strip()
    return contact.email


@staff_required
def contacts(request):
    if request.method == "POST" and request.POST.get("action") == "delete_contact":
        contact_id = request.POST.get("contact_id")
        Contact.objects.filter(id=contact_id).delete()
        messages.success(request, "Kontakt smazán.")
        return redirect("rozesilac:contacts")

    if request.method == "POST" and request.POST.get("action") == "add_group":
        group_form = ContactGroupForm(request.POST)
        if group_form.is_valid():
            group_form.save()
            messages.success(request, "Skupina byla vytvořena.")
            return redirect("rozesilac:contacts")
    else:
        group_form = ContactGroupForm()

    if request.method == "POST" and request.POST.get("action") == "delete_group":
        group_id = request.POST.get("group_id")
        ContactGroup.objects.filter(id=group_id).delete()
        messages.success(request, "Skupina byla smazána.")
        return redirect("rozesilac:contacts")

    add_form = ContactForm()
    import_form = ContactImportForm()

    if request.method == "POST" and request.POST.get("action") == "add_contact":
        add_form = ContactForm(request.POST)
        if add_form.is_valid():
            try:
                add_form.save()
                messages.success(request, "Kontakt uložen.")
                return redirect("rozesilac:contacts")
            except IntegrityError:
                add_form.add_error("email", "Tento email už v kontaktech existuje.")

    if request.method == "POST" and request.POST.get("action") == "import":
        import_form = ContactImportForm(request.POST, request.FILES)
        if import_form.is_valid():
            f = import_form.cleaned_data["file"]
            selected_group = import_form.cleaned_data.get("group")

            wb = load_workbook(filename=f, data_only=True)
            ws = wb.active

            header_row = [str(c.value).strip().lower() if c.value is not None else "" for c in ws[1]]

            def find_col(possible_names):
                for i, h in enumerate(header_row):
                    if h in possible_names:
                        return i
                return None

            name_col = find_col({"jméno", "jmeno", "name"})
            email_col = find_col({"email", "e-mail", "e mail", "mail"})
            salutation_col = find_col({"osloveni", "salutation", "pozdrav", "oslovení"})

            if name_col is None or email_col is None:
                messages.error(request, "XLSX musí mít v prvním řádku sloupce 'jméno' a 'email'.")
                return redirect("rozesilac:contacts")

            created = 0
            skipped = 0
            invalid = 0

            for row in ws.iter_rows(min_row=2, values_only=True):
                raw_email = row[email_col] if email_col < len(row) else None
                raw_name = row[name_col] if name_col < len(row) else None
                raw_salutation = row[salutation_col] if (salutation_col is not None and salutation_col < len(row)) else None

                email = (str(raw_email).strip() if raw_email is not None else "").lower()
                name = str(raw_name).strip() if raw_name is not None else ""
                salutation = str(raw_salutation).strip() if raw_salutation is not None else ""

                if not email:
                    continue

                try:
                    validate_email(email)
                except ValidationError:
                    invalid += 1
                    continue

                obj, was_created = Contact.objects.get_or_create(
                    email=email,
                    defaults={"name": name, "salutation": salutation, "is_active": True},
                )

                if was_created:
                    created += 1
                else:
                    skipped += 1

                if selected_group:
                    obj.groups.add(selected_group)

            messages.success(
                request,
                f"Import hotový. Přidáno: {created}, přeskočeno (duplicitní): {skipped}, neplatné emaily: {invalid}."
            )
            return redirect("rozesilac:contacts")

    contacts = Contact.objects.prefetch_related("groups").order_by("groups__name", "email").distinct()
    groups = ContactGroup.objects.all()

    # --------------------------------------------------
    # Statistiky kontaktů pro přehled v seznamu
    # --------------------------------------------------

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

        for d in contact_deliveries:
            human_events = [e for e in d.click_events.all() if not e.is_suspected_bot]
            unique_urls = set(e.original_url for e in human_events)
            confirmed_unique_click_count += len(unique_urls)

        c.confirmed_unique_click_count_for_ui = confirmed_unique_click_count

    return render(
        request,
        "rozesilac/contacts.html",
        {
            "contacts": contacts,
            "groups": groups,
            "add_form": add_form,
            "import_form": import_form,
            "group_form": group_form,
        },
    )

@staff_required
def contact_detail(request, contact_id):
    contact = get_object_or_404(Contact, id=contact_id)

    human_clicks_subquery = EmailClickEvent.objects.filter(
        delivery=OuterRef("pk"),
        is_suspected_bot=False,
    )

    bot_clicks_subquery = EmailClickEvent.objects.filter(
        delivery=OuterRef("pk"),
        is_suspected_bot=True,
    )

    deliveries = (
        EmailDelivery.objects
        .filter(to_email=contact.email)
        .select_related("campaign", "campaign__template")
        .order_by("-created_at")
        .annotate(
            has_human_like_click=Exists(human_clicks_subquery),
            has_suspected_bot_click=Exists(bot_clicks_subquery),
        )
        .prefetch_related(
            "campaign__tracked_links",
            Prefetch(
                "click_events",
                queryset=EmailClickEvent.objects.order_by("created_at"),
            )
        )
    )

    total_deliveries = deliveries.count()
    sent_deliveries = deliveries.filter(status="sent").count()
    failed_deliveries = deliveries.filter(status="failed").count()
    clicked_campaigns_count = 0
    confirmed_unique_click_count_total = 0
    last_human_click_at = None

    for delivery in deliveries:
        all_events = list(delivery.click_events.all())
        human_events = [e for e in all_events if not e.is_suspected_bot]

        unique_urls = []
        seen_urls = set()

        for e in human_events:
            if e.original_url not in seen_urls:
                seen_urls.add(e.original_url)
                unique_urls.append(e.original_url)

        delivery.human_click_events_for_ui = human_events
        delivery.clicked_urls_for_ui = unique_urls
        delivery.confirmed_unique_click_count_for_ui = len(unique_urls)
        delivery.first_human_click_at_for_ui = human_events[0].created_at if human_events else None
        delivery.last_human_click_at_for_ui = human_events[-1].created_at if human_events else None

        if unique_urls:
            clicked_campaigns_count += 1
            confirmed_unique_click_count_total += len(unique_urls)

        if human_events:
            candidate_last = human_events[-1].created_at
            if last_human_click_at is None or candidate_last > last_human_click_at:
                last_human_click_at = candidate_last

    return render(
        request,
        "rozesilac/contact_detail.html",
        {
            "contact": contact,
            "deliveries": deliveries,
            "total_deliveries": total_deliveries,
            "sent_deliveries": sent_deliveries,
            "failed_deliveries": failed_deliveries,
            "clicked_campaigns_count": clicked_campaigns_count,
            "confirmed_unique_click_count_total": confirmed_unique_click_count_total,
            "last_human_click_at": last_human_click_at,
        },
    )


@staff_required
def contact_edit(request, contact_id):
    contact = get_object_or_404(Contact, id=contact_id)

    if request.method == "POST":
        form = ContactForm(request.POST, instance=contact)
        if form.is_valid():
            try:
                form.save()
                messages.success(request, "Kontakt byl upraven.")
                return redirect("rozesilac_contacts")
            except IntegrityError:
                form.add_error("email", "Tento email už v kontaktech existuje.")
    else:
        form = ContactForm(instance=contact)

    return render(
        request,
        "rozesilac/contact_edit.html",
        {
            "form": form,
            "page_title": f"Upravit kontakt: {contact.email}",
            "submit_label": "Uložit změny",
            "contact_obj": contact,
        },
    )

@staff_required
def images(request):
    return render(request, "rozesilac/images.html")

@staff_required
def image_upload(request):
    if request.method != "POST":
        return HttpResponseForbidden("Pouze POST.")

    form = EmailImageUploadForm(request.POST, request.FILES)
    next_url = request.POST.get("next") or "rozesilac:templates"

    if form.is_valid():
        obj = form.save(commit=False)
        obj.uploaded_by = request.user
        obj.file_size = obj.image.size
        obj.save()
        messages.success(request, "Obrázek byl nahrán.")
    else:
        for error in form.non_field_errors():
            messages.error(request, error)
            
        for field_name, errors in form.errors.items():
            if field_name == "__all__":
                continue
            for error in errors:
                messages.error(request, error)

    return redirect(next_url)

@staff_required
def send(request):
    return render(request, "rozesilac/send.html")

@staff_required
def campaigns(request):
    return render(request, "rozesilac/campaigns.html")

@staff_required
def campaign_detail(request, campaign_id):
    return render(request, "rozesilac/campaign_detail.html")