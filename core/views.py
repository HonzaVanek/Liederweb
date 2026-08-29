import hashlib
import logging

from django.db import IntegrityError
from django.db.models import F
from urllib.parse import urldefrag, urlsplit
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.views import LoginView
from django.views.generic import ListView, DetailView, CreateView, UpdateView
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.utils import timezone
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode, url_has_allowed_host_and_scheme
from django.http import HttpResponse
from django.contrib.auth.models import User
from django.contrib.auth.tokens import default_token_generator
from django.utils.encoding import force_bytes
from django.urls import reverse
from django.template.loader import render_to_string
from django.core.mail import EmailMessage, send_mail
from django.core.paginator import Paginator
from django.core.cache import cache
from django.utils.decorators import method_decorator

from .forms import VlastniLoginForm, RegistraceForm, PersonForm, NewsletterSignupForm, PartnerForm, HomeCarouselManualSlideForm, AgnesSupportIntentForm, HomeSupportPromoForm, HomeQuoteSlideForm
from .models import Person, Partner, HomeCarouselManualSlide, HomeSupportPromo, HomeQuoteSlide, DailyEngagedVisitor, DailyEngagedPageVisitor, DailySiteVisitor, DailyPageVisitor, DailyBrowserVisitor, DailySiteTraffic, DailyPageTraffic
from events.models import Event
from media_assets.models import MediaAsset
from social_feed.models import SocialPost, SocialSource
from .decorators import staff_required
from rozesilac.models import Contact
from rozesilac.services import get_web_contacts_group
from datetime import timedelta

from .utils.payments import build_spd_payload, make_qr_svg


def robots_txt(request):
    content = """# Lieder Society
# https://lieder-society.cz/robots.txt

User-agent: GPTBot
Disallow: /

User-agent: ClaudeBot
Disallow: /

User-agent: Google-Extended
Disallow: /

User-agent: CCBot
Disallow: /

User-agent: Bytespider
Disallow: /

User-agent: Amazonbot
Disallow: /

User-agent: Meta-ExternalAgent
Disallow: /

User-agent: FacebookBot
Disallow: /

User-agent: *
Allow: /

Disallow: /admin/
Disallow: /staff/
Disallow: /rozesilac/
Disallow: /media-assets/

Disallow: /login/
Disallow: /logout/
Disallow: /registrace/
Disallow: /password-reset/
Disallow: /reset/
Disallow: /activate/

Disallow: /events/create/
Disallow: /events/vip/
Disallow: /events/*/edit/
Disallow: /events/*/tickets/
Disallow: /events/*/export-vip/

# Sitemap: https://lieder-society.cz/sitemap.xml
"""
    return HttpResponse(content, content_type="text/plain")



### hlavní landing page ####

def home(request):
    now = timezone.now()

    upcoming_event = (
        Event.objects
        .select_related("poster_asset", "poster_image")
        .filter(is_published=True, starts_at__gte=now)
        .order_by("starts_at")
        .first()
    )

    latest_past_event = (
        Event.objects
        .select_related("poster_asset", "poster_image")
        .filter(is_published=True, starts_at__lt=now)
        .order_by("-starts_at")
        .first()
    )

    featured_event = upcoming_event or latest_past_event
    has_upcoming_event = upcoming_event is not None

    default_carousel_slide_index = 1 if has_upcoming_event else 0

    featured_facebook_post = (
        SocialPost.objects.select_related("source")
        .prefetch_related("media_items")
        .filter(
            source__platform=SocialSource.Platform.FACEBOOK,
            source__is_active=True,
            is_visible=True,
            image_url__gt="",
        )
        .order_by("-published_at", "-id")
        .first()
    )

    recent_facebook_posts = (
        SocialPost.objects.select_related("source")
        .filter(
            source__platform=SocialSource.Platform.FACEBOOK,
            source__is_active=True,
            is_visible=True,
        )
        .order_by("-published_at", "-id")[:5]
    )

    manual_home_slide = HomeCarouselManualSlide.get_solo()
    support_promo = HomeSupportPromo.get_solo()

    home_quote_slides = (
        HomeQuoteSlide.objects
        .filter(is_active=True)
        .select_related("background_media")
        .order_by("sort_order", "id")
    )

    return render(
        request,
        "core/home.html",
        {
            "featured_event": featured_event,
            "featured_facebook_post": featured_facebook_post,
            "recent_facebook_posts": recent_facebook_posts,
            "manual_home_slide": manual_home_slide,
            "support_promo": support_promo,
            "now": now,
            "has_upcoming_event": has_upcoming_event,
            "default_carousel_slide_index": default_carousel_slide_index,
            "home_quote_slides": home_quote_slides,
        },
    )

@staff_required
def home_manual_slide_edit(request):
    slide = HomeCarouselManualSlide.get_solo()

    if request.method == "POST":
        form = HomeCarouselManualSlideForm(request.POST, instance=slide)

        if form.is_valid():
            slide = form.save(commit=False)
            slide.updated_by = request.user
            slide.save()

            messages.success(request, "Blok homepage carouselu byl uložen.")
            return redirect("core:home_manual_slide_edit")
    else:
        form = HomeCarouselManualSlideForm(instance=slide)

    image_assets_qs = form.fields["image_asset"].queryset

    paginator = Paginator(image_assets_qs, 18)
    image_page_number = (
        request.GET.get("images_page")
        or request.POST.get("images_page")
        or 1
    )
    image_page = paginator.get_page(image_page_number)

    selected_image_asset_id = str(form["image_asset"].value() or "")

    selected_image_asset = None
    if selected_image_asset_id:
        selected_image_asset = (
            image_assets_qs
            .filter(pk=selected_image_asset_id)
            .first()
        )

    return render(
        request,
        "core/home_manual_slide_form.html",
        {
            "form": form,
            "slide": slide,
            "image_page": image_page,
            "selected_image_asset": selected_image_asset,
            "selected_image_asset_id": selected_image_asset_id,
            "page_title": "Homepage carousel",
        },
    )


@staff_required
def home_support_promo_edit(request):
    promo = HomeSupportPromo.get_solo()

    if request.method == "POST":
        form = HomeSupportPromoForm(request.POST, instance=promo)

        if form.is_valid():
            promo = form.save(commit=False)
            promo.updated_by = request.user
            promo.save()

            messages.success(request, "Sekce podpory na homepage byla uložena.")
            return redirect("core:home_support_promo_edit")
    else:
        form = HomeSupportPromoForm(instance=promo)

    return render(
        request,
        "core/home_support_promo_form.html",
        {
            "form": form,
            "promo": promo,
            "page_title": "Homepage – podpora",
        },
    )


@staff_required
def home_quote_slide_list(request):
    slides = (
        HomeQuoteSlide.objects
        .select_related("background_media", "updated_by")
        .order_by("sort_order", "id")
    )

    return render(
        request,
        "core/home_quote_slide_list.html",
        {
            "slides": slides,
            "page_title": "Homepage citace",
        },
    )

@staff_required
def home_quote_slide_create(request):
    if request.method == "POST":
        form = HomeQuoteSlideForm(request.POST)

        if form.is_valid():
            slide = form.save(commit=False)
            slide.updated_by = request.user
            slide.save()

            messages.success(request, "Citace byla vytvořena.")
            return redirect("core:home_quote_slide_list")
    else:
        form = HomeQuoteSlideForm()

    return render(
        request,
        "core/home_quote_slide_form.html",
        {
            "form": form,
            "page_title": "Nová citace na homepage",
            "submit_label": "Vytvořit citaci",
        },
    )

@staff_required
def home_quote_slide_update(request, pk):
    slide = get_object_or_404(HomeQuoteSlide, pk=pk)

    if request.method == "POST":
        form = HomeQuoteSlideForm(request.POST, instance=slide)

        if form.is_valid():
            slide = form.save(commit=False)
            slide.updated_by = request.user
            slide.save()

            messages.success(request, "Citace byla upravena.")
            return redirect("core:home_quote_slide_list")
    else:
        form = HomeQuoteSlideForm(instance=slide)

    return render(
        request,
        "core/home_quote_slide_form.html",
        {
            "form": form,
            "slide": slide,
            "page_title": f"Upravit citaci: {slide.kicker}",
            "submit_label": "Uložit změny",
        },
    )

@staff_required
def home_quote_slide_delete(request, pk):
    slide = get_object_or_404(HomeQuoteSlide, pk=pk)

    if request.method == "POST":
        slide.delete()
        messages.success(request, "Citace byla smazána.")
        return redirect("core:home_quote_slide_list")

    return render(
        request,
        "core/home_quote_slide_confirm_delete.html",
        {
            "slide": slide,
            "page_title": f"Smazat citaci: {slide.kicker}",
        },
    )


#newsletter signup view a pomocné funkce
NEWSLETTER_ANCHOR = "newsletter-signup"

def _add_newsletter_anchor(url):
    url_without_fragment, _fragment = urldefrag(url)
    return f"{url_without_fragment}#{NEWSLETTER_ANCHOR}"

def _get_safe_redirect_url(request):
    redirect_url = request.POST.get("next") or request.META.get("HTTP_REFERER")

    if redirect_url and url_has_allowed_host_and_scheme(
        url=redirect_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return _add_newsletter_anchor(redirect_url)

    return _add_newsletter_anchor(reverse("core:home"))


@require_POST
def newsletter_signup(request):
    redirect_url = _get_safe_redirect_url(request)
    form = NewsletterSignupForm(request.POST)

    if not form.is_valid():
        messages.error(request, "Zkontrolujte prosím e-mail a zkuste to znovu.", extra_tags="newsletter")
        return redirect(redirect_url)

    # Honeypot – pokud je vyplněný, pravděpodobně bot.
    # Nevracíme chybu, jen tiše přesměrujeme.
    if form.cleaned_data.get("website"):
        return redirect(redirect_url)

    email = form.cleaned_data["email"]
    name = form.cleaned_data.get("name", "").strip()

    group = get_web_contacts_group()

    contact, created = Contact.objects.get_or_create(
        email=email,
        defaults={
            "name": name,
            "is_active": True,
        },
    )

    update_fields = []

    if not contact.is_active:
        contact.is_active = True
        update_fields.append("is_active")

    # Jméno bych nepřepisoval agresivně.
    # Když už kontakt jméno má, nechal bych ho být.
    if name and not contact.name:
        contact.name = name
        update_fields.append("name")

    if update_fields:
        contact.save(update_fields=update_fields)

    contact.groups.add(group)

    messages.success(request, "Děkujeme, přihlášení k newsletteru je zaznamenané.", extra_tags="newsletter")
    return redirect(redirect_url)



#### Partneři ####


@staff_required
def partner_admin_list(request):
    partners = (
        Partner.objects
        .select_related("logo")
        .order_by("sort_order", "name", "id")
    )

    return render(request, "core/partner_admin_list.html", {
        "partners": partners,
    })


@staff_required
def partner_admin_create(request):
    if request.method == "POST":
        form = PartnerForm(request.POST)

        if form.is_valid():
            partner = form.save()
            messages.success(request, f"Partner „{partner.name}“ byl vytvořen.")
            return redirect("core:partner_admin_list")
    else:
        form = PartnerForm()

    return render(request, "core/partner_form.html", {
        "form": form,
        "page_title": "Nový partner",
        "submit_label": "Vytvořit partnera",
    })


@staff_required
def partner_admin_update(request, pk):
    partner = get_object_or_404(Partner, pk=pk)

    if request.method == "POST":
        form = PartnerForm(request.POST, instance=partner)

        if form.is_valid():
            partner = form.save()
            messages.success(request, f"Partner „{partner.name}“ byl upraven.")
            return redirect("core:partner_admin_list")
    else:
        form = PartnerForm(instance=partner)

    return render(request, "core/partner_form.html", {
        "form": form,
        "partner": partner,
        "page_title": f"Upravit partnera: {partner.name}",
        "submit_label": "Uložit změny",
    })


@staff_required
def partner_admin_delete(request, pk):
    partner = get_object_or_404(Partner, pk=pk)

    if request.method == "POST":
        partner_name = partner.name
        partner.delete()
        messages.success(request, f"Partner „{partner_name}“ byl smazán.")
        return redirect("core:partner_admin_list")

    return render(request, "core/partner_confirm_delete.html", {
        "partner": partner,
        "page_title": f"Smazat partnera: {partner.name}",
    })


#### KONEC PARTNEŘI #####


##### konec landing page #####



#### LOGIN a REGISTRACE ####

class VlastniLoginView(LoginView):
    template_name = "core/login.html"
    form_class = VlastniLoginForm


def registrace(request):
    if request.method == "POST":
        form = RegistraceForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)

            # ----- DEV REŽIM -----
            if settings.APP_ENV == "dev":
                user.is_active = True
                user.save()
                login(request, user)
                return redirect("core:home")

            # ----- PROD REŽIM -----
            user.is_active = False
            user.save()

            send_mail(
                subject="Nová registrace na Liederweb",
                message=f"Uživatel {user.username} si vytvořil novou registraci. Email: {user.email}",
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=["vanek.hv@gmail.com"],
                fail_silently=True,
            )

            uidb64 = urlsafe_base64_encode(force_bytes(user.pk))
            token = default_token_generator.make_token(user)

            activation_path = reverse("core:activate", args=[uidb64, token])
            activation_link = request.build_absolute_uri(activation_path)

            subject = "Aktivuj si účet"
            message = render_to_string(
                "registration/activation_email.txt",
                {
                    "user": user,
                    "activation_link": activation_link,
                },
            )

            email = EmailMessage(
                subject,
                message,
                settings.DEFAULT_FROM_EMAIL,
                to=[user.email],
            )
            email.send(fail_silently=False)

            return render(request, "core/registration_complete.html", {"form": form})

    else:
        form = RegistraceForm()

    return render(request, "core/registrace.html", {"form": form})

def activate(request, uidb64, token):
    try:
        uid = urlsafe_base64_decode(uidb64).decode()
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None

    if user is not None and default_token_generator.check_token(user, token):
        user.is_active = True
        user.save()
        messages.success(request, "Váš účet byl aktivován, nyní se můžete přihlásit.")
        return redirect("core:login")

    return render(request, "core/activation_invalid.html")

#### KONEC LOGIN a REGISTRACE ####


###### stránka lidé  #######

class PersonListView(ListView):
    model = Person
    template_name = "core/person_list.html"
    context_object_name = "people"

    def get_queryset(self):
        return (
            Person.objects
            .filter(is_published=True)
            .select_related("photo_asset")
            .order_by("sort_order", "name")
        )


class PersonDetailView(DetailView):
    model = Person
    template_name = "core/person_detail.html"
    context_object_name = "person"
    slug_field = "slug"
    slug_url_kwarg = "slug"

    def get_queryset(self):
        return (
            Person.objects
            .filter(is_published=True)
            .select_related("photo_asset")
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        published_people = list(
            Person.objects
            .filter(is_published=True)
            .only("id", "name", "slug", "sort_order")
            .order_by("sort_order", "name", "id")
        )

        current_index = next(
            (
                index
                for index, person in enumerate(published_people)
                if person.pk == self.object.pk
            ),
            None,
        )

        context["previous_person"] = None
        context["next_person"] = None

        if current_index is not None:
            if current_index > 0:
                context["previous_person"] = published_people[current_index - 1]

            if current_index < len(published_people) - 1:
                context["next_person"] = published_people[current_index + 1]

        return context


def get_recent_person_image_assets(selected_asset=None):
    assets = list(
        MediaAsset.objects.filter(
            asset_type=MediaAsset.AssetType.IMAGE,
            is_active=True,
        ).order_by("-uploaded_at", "-id")
    )

    if selected_asset and all(asset.pk != selected_asset.pk for asset in assets):
        assets.insert(0, selected_asset)

    return assets

@method_decorator(staff_required, name="dispatch")
class PersonAdminListView(ListView):
    model = Person
    template_name = "core/person_admin_list.html"
    context_object_name = "people"

    def get_queryset(self):
        return (
            Person.objects
            .all()
            .select_related("photo_asset")
            .order_by("sort_order", "name")
        )


@method_decorator(staff_required, name="dispatch")
class PersonCreateView(CreateView):
    model = Person
    form_class = PersonForm
    template_name = "core/person_form.html"

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, "Profil byl vytvořen.")
        return response

    def get_success_url(self):
        return reverse("core:person_update", kwargs={"slug": self.object.slug})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "Nový profil"
        context["submit_label"] = "Vytvořit profil"
        context["person"] = None
        context["recent_image_assets"] = get_recent_person_image_assets()
        context["selected_photo_asset_id"] = ""
        return context


@method_decorator(staff_required, name="dispatch")
class PersonUpdateView(UpdateView):
    model = Person
    form_class = PersonForm
    template_name = "core/person_form.html"
    context_object_name = "person"
    slug_field = "slug"
    slug_url_kwarg = "slug"

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, "Profil byl uložen.")
        return response

    def get_success_url(self):
        return reverse("core:person_update", kwargs={"slug": self.object.slug})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = f"Upravit profil: {self.object.name}"
        context["submit_label"] = "Uložit změny"
        context["public_url"] = self.object.get_absolute_url() if self.object.is_published else None
        context["recent_image_assets"] = get_recent_person_image_assets(self.object.photo_asset)
        context["selected_photo_asset_id"] = str(self.object.photo_asset_id or "")
        return context
    

##### konec stránky lidé  #######


# stránka kontakty bude jen statická #

def contact(request):
    return render(request, "core/contact.html")

# to je všechno :) #


########## další view pro statickou stránku kampaně k Agnes Tyrrell jen pro návštěvníky Tugendhatu.


def agnes_tyrrell_landing(request):
    support_levels = [
        {
            "title": "Přítel alba",
            "amount": "500 Kč",
            "darujme_amount": 500,
            "description": "CD a poděkování.",
        },
        {
            "title": "Podporovatel projektu",
            "amount": "1 000 Kč",
            "darujme_amount": 1000,
            "description": "Podepsané CD a osobní poděkování.",
        },
        {
            "title": "Mecenáš nahrávky",
            "amount": "2 000 Kč",
            "darujme_amount": 2000,
            "description": "Jméno v bookletu a pozvání na slavnostní křest.",
        },
        {
            "title": "Patron Agnes Tyrrell",
            "amount": "5 000 Kč",
            "darujme_amount": 5000,
            "description": "Jméno v bookletu, VIP pozvání na křest a setkání s umělci.",
        },
    ]

    timeline_items = [
        {
            "date": "29. května",
            "title": "Koncert ve Vile Tugendhat",
            "text": "Festival Meeting Brno.",
        },
        {
            "date": "Červen / červenec",
            "title": "Natáčení alba",
            "text": "První studiové zachycení vybraných skladeb Agnes Tyrrell.",
        },
        {
            "date": "Podzim",
            "title": "Postprodukce a booklet",
            "text": "Dokončení nahrávky, dramaturgických textů a grafického zpracování.",
        },
        {
            "date": "Podzim",
            "title": "Vydání CD",
            "text": "Uvedení alba do života a jeho představení veřejnosti.",
        },
        {
            "date": "9. prosince",
            "title": "Slavnostní křest",
            "text": "Setkání partnerů, podporovatelů a interpretů.",
        },
    ]

    artist_cards = [

        {
            "name": "Tamara Morozová",
            "role": "sopranistka",
            "url": "https://tamaramorozova.com/",
            "image_url": "/media/media_assets/image/2026/05/5ed7302f50ae4126b60d99a814ed6d67.jpg",
            "bio": (
                "Sopranistka slovenského původu, členka Národního divadla v Praze a předsedkyně "
                "Lieder Society. Je laureátkou a finalistkou významných pěveckých soutěží a věnuje se "
                "opernímu i koncertnímu repertoáru."
            ),
        },

        {
            "name": "Arnheiður Eiríksdóttir",
            "role": "mezzosopranistka",
            "url": "http://arnheidur.com/",
            "image_url": "/media/media_assets/image/2026/05/929581cc52bb42e9a65717e33b4f804c.jpg",
            "bio": (
                "Islandská mezzosopranistka známá českému publiku mimo jiné z Národního divadla v Praze. "
                "V projektu Agnes Tyrrell propůjčí hlas písňovému cyklu Schilflieder – Písně rákosí z roku 1878."
            ),
        },

        {
            "name": "Monika Jägerová",
            "role": "altistka",
            "url": "https://www.monikajagerova.com/cs",
            "image_url": "/media/media_assets/image/2026/05/4b1d7034a8634ee6bedfaa3a2101a534.jpg",
            "bio": (
                "Česká altistka oceňovaná pro podmanivý hluboký hlas a stylovou všestrannost. "
                "Vystupuje na předních evropských scénách a festivalech, spolupracuje s významnými "
                "orchestry a soubory a je jednou ze zakladatelek Lieder Society."
            ),
        },

        {
            "name": "Kristina Marková",
            "role": "klavíristka",
            "url": "https://lieder-society.cz/lide/kristina-markova-stepasjukova/",
            "image_url": "/media/media_assets/image/2026/05/58492b3dff204431a0c9edd0bbbbd980.jpg",
            "bio": (
                "Klavíristka a vyhledávaná komorní interpretka, absolventka HAMU a Universität für Musik "
                "und darstellende Kunst ve Vídni. Dlouhodobě se věnuje sólové i komorní hudbě a působí "
                "na Pražské konzervatoři a HAMU."
            ),
        },
    ]

    project_partners = [
        {
            "name": "Ministerstvo kultury",
            "url": "https://mk.gov.cz/",
            "logo_url": "/media/email_images/logo-mkcr.png",
        },
        {
            "name": "Mariann-Steegmann-Foundation",
            "url": "http://mariann-steegmann-foundation.org/",
            "logo_url": "/media/media_assets/image/2026/05/33fa4db704d248608660b5a56b7ad487.png",
        },
        {
            "name": "Meeting Brno",
            "url": "https://www.meetingbrno.cz/",
            "logo_url": "/media/media_assets/image/2026/05/66494f44d27c497ab05cde65387fd0ed.jpg",
        },
        {
            "name": "Universität Leipzig",
            "url": "https://www.uni-leipzig.de/",
            "logo_url": "/media/media_assets/image/2026/05/2d2101676fb04395a3ec76e69dedafd2.svg",
        },
        {
            "name": "Univerzita Palackého v Olomouci",
            "url": "https://www.upol.cz/",
            "logo_url": "/media/media_assets/image/2026/05/880243a0ef78413aba8231f1b41c162e.png",
        },
    ]


# tady funkce spojené s platební kampaní pro Agnes Tyrrell, možná se to nakonec nepoužije, ale zatím to tu nechám pro případný další vývoj.
    payment_intent = None
    payment_qr_svg = ""
    payment_payload = ""

    if request.method == "POST" and request.POST.get("form_type") == "agnes_support":
        support_form = AgnesSupportIntentForm(request.POST)

        if support_form.is_valid():
            payment_intent = support_form.save()

            payment_payload = build_spd_payload(
                iban=settings.LIEDER_DONATION_IBAN,
                amount=payment_intent.amount,
                message="Dar Agnes Tyrrell",
                variable_symbol=payment_intent.variable_symbol,
            )
            payment_qr_svg = make_qr_svg(payment_payload)
        else:
            payment_intent = None
    else:
        support_form = AgnesSupportIntentForm()
# pocaď se to dá vlastně smazat, pokud se nakonec rozhodne, že se žádný platební formulář na landing page dělat nebude. Ale zatím to tu nechám pro případný další vývoj.
    return render(
        request,
        "core/agnes_tyrrell.html",
        {
            "hide_header": True,
            "support_levels": support_levels,
            "timeline_items": timeline_items,
            "artist_cards": artist_cards,
            "project_partners": project_partners,
            "hero_image_url": "/media/media_assets/image/2026/05/8cfedb64afb84007bbdd3a41a758be84.jpg",
            "lieder_logo_url": "/media/media_assets/image/2026/05/2adc68f6908b4cf6b9934db24e34f53f.png",
            "video_url": "/media/media_assets/video/2026/05/7085f8be181542f28cff7e0d1f2e5ae9.mp4",
            "video_poster_url": "/media/media_assets/image/2026/05/6ead146bd9c94367b6dea89c515ee636.png",

            #následující 4 řádky bude možné později smazat, pokud se nakonec rozhodne, že se žádný platební formulář na landing page dělat nebude. Ale zatím to tu nechám pro případný další vývoj.
            "support_form": support_form,
            "payment_intent": payment_intent,
            "payment_qr_svg": payment_qr_svg,
            "payment_payload": payment_payload,
            "donation_recipient": settings.LIEDER_DONATION_RECIPIENT,
            "donation_account_display": settings.LIEDER_DONATION_ACCOUNT_DISPLAY,
        },
    )


def mlady_salon(request):
    return render(request, "core/mlady_salon.html")


#JS beacon prodetekci lidských návštěv:

def get_client_ip(request):
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0].strip()

    x_real_ip = request.META.get("HTTP_X_REAL_IP")
    if x_real_ip:
        return x_real_ip.strip()

    return request.META.get("REMOTE_ADDR", "")

def is_meta_infrastructure_ip(ip):
    ip = (ip or "").lower()
    return ip.startswith("2a03:2880:")


def is_meta_crawler_ua(user_agent):
    ua = (user_agent or "").lower()
    return any(part in ua for part in (
        "meta-externalads",
        "meta-externalagent",
        "meta-webindexer",
        "facebookexternalhit",
        "facebot",
        "developers.facebook.com/docs/sharing/webmasters/crawler",
    ))


def classify_engaged_source(source_referer, user_agent):
    referer = (source_referer or "").strip()
    ua = (user_agent or "").lower()

    host = ""

    if referer:
        try:
            host = (urlsplit(referer).hostname or "").lower()
        except Exception:
            host = ""

    # Primárně skutečný původní referer.
    if host == "instagram.com" or host.endswith(".instagram.com"):
        return DailyEngagedVisitor.Source.INSTAGRAM

    if (host == "facebook.com" or host.endswith(".facebook.com") or host == "fb.com" or host.endswith(".fb.com")):
        return DailyEngagedVisitor.Source.FACEBOOK

    google_domains = (
        "google.com",
        "google.cz",
        "google.sk",
        "google.de",
        "google.at",
        "google.pl",
        "google.co.uk",
    )

    if any(host == domain or host.endswith(f".{domain}") for domain in google_domains):
        return DailyEngagedVisitor.Source.GOOGLE

    # Fallback pro in-app browser, který referer neposlal.
    if "instagram/" in ua or "instagram " in ua:
        return DailyEngagedVisitor.Source.INSTAGRAM

    if ("fb_iab/" in ua or "fban/" in ua or "fbav/" in ua):
        return DailyEngagedVisitor.Source.FACEBOOK

    return DailyEngagedVisitor.Source.OTHER


def classify_engaged_page_source(source_referer, user_agent):
    referer = (source_referer or "").strip()

    host = ""

    if referer:
        try:
            host = (urlsplit(referer).hostname or "").lower()
        except Exception:
            host = ""

    # Přechod z jiné stránky našeho webu.
    if host in (
        "lieder-society.cz",
        "www.lieder-society.cz",
        "liedersociety.website",
        "www.liedersociety.website",
    ):
        return DailyEngagedPageVisitor.Source.OWN

    # Externí zdroje klasifikujeme stejně jako
    # u celkového engaged návštěvníka.
    source = classify_engaged_source(
        source_referer,
        user_agent,
    )

    if source == DailyEngagedVisitor.Source.INSTAGRAM:
        return DailyEngagedPageVisitor.Source.INSTAGRAM

    if source == DailyEngagedVisitor.Source.FACEBOOK:
        return DailyEngagedPageVisitor.Source.FACEBOOK

    if source == DailyEngagedVisitor.Source.GOOGLE:
        return DailyEngagedPageVisitor.Source.GOOGLE

    return DailyEngagedPageVisitor.Source.OTHER


def is_obvious_beacon_bot_ua(user_agent):
    ua = (user_agent or "").lower()

    return any(part in ua for part in (
        "bot",
        "crawler",
        "spider",
        "slurp",
        "headless",
        "python-requests",
        "python-urllib",
        "curl/",
        "wget/",
        "ct-wp-probe",
        "uk-nhs-data",
        "watchtowr",
    ))

logger = logging.getLogger("liederweb.traffic")

@csrf_exempt
@require_POST
def traffic_engaged(request):
    user = getattr(request, "user", None)

    if user and user.is_authenticated and user.is_staff:
        return HttpResponse(status=204)

    ip = get_client_ip(request)
    user_agent = request.META.get("HTTP_USER_AGENT", "")[:500]
    content_type = request.META.get("CONTENT_TYPE", "")
    referer = (
        request.META.get("HTTP_REFERER", "") or ""
    ).split("?", 1)[0][:300]

    try:
        raw_body = request.body[:200]
    except Exception:
        raw_body = b""

    stage = (
        request.POST.get("stage")
        or "engaged"
    ).strip().lower()

    if stage not in ("browser", "engaged"):
        logger.info(
            "TRAFFIC_BEACON_SKIP reason=bad_stage stage=%s ip=%s",
            stage[:30],
            ip,
        )
        return HttpResponse(status=204)

    skip_kind = (
        "BROWSER_SKIP"
        if stage == "browser"
        else "ENGAGED_SKIP"
    )

    if not ip:
        logger.debug("%s reason=no_ip", skip_kind)
        return HttpResponse(status=204)

    if not user_agent.strip():
        logger.debug(
            "%s reason=no_ua ip=%s",
            skip_kind,
            ip,
        )
        return HttpResponse(status=204)

    path = (request.POST.get("path") or "").strip()

    if not path.startswith("/"):
        logger.debug(
            "%s reason=bad_path ip=%s "
            "content_type=%s post=%s body=%s",
            skip_kind,
            ip,
            content_type,
            dict(request.POST),
            raw_body,
        )
        return HttpResponse(status=204)

    path = path.split("?", 1)[0][:500]

    if (
        path in (
            "/login/",
            "/password-reset/",
            "/registrace/",
        )
        or path.startswith("/rozesilac/")
    ):
        logger.debug(
            "%s reason=ignored_path path=%s",
            skip_kind,
            path,
        )
        return HttpResponse(status=204)

    if (
        is_meta_infrastructure_ip(ip)
        or is_meta_crawler_ua(user_agent)
    ):
        logger.info(
            "%s reason=meta_crawler "
            "ip=%s path=%s referer=%s ua=%s",
            skip_kind,
            ip,
            path[:300],
            referer,
            user_agent[:300],
        )
        return HttpResponse(status=204)

    today = timezone.localdate()

    raw_client_id = (
        f"{today}|{ip}|{settings.SECRET_KEY}"
    )
    client_hash = hashlib.sha256(
        raw_client_id.encode("utf-8")
    ).hexdigest()
    client_label = client_hash[:8]

    raw_visitor_id = (
        f"{today}|{ip}|{user_agent}|"
        f"{settings.SECRET_KEY}"
    )
    visitor_hash = hashlib.sha256(
        raw_visitor_id.encode("utf-8")
    ).hexdigest()
    visitor_label = visitor_hash[:8]

    source_info = cache.get(
        f"traffic_visit_source:"
        f"{today}:{client_hash}:{path}"
    ) or {}

    source_referer = ""
    source_visitor_label = ""

    if isinstance(source_info, dict):
        source_referer = (
            source_info.get("referer", "") or ""
        )
        source_visitor_label = (
            source_info.get("visitor", "") or ""
        )

    if is_obvious_beacon_bot_ua(user_agent):
        logger.info(
            "%s reason=bot_user_agent "
            "ip=%s client=%s visitor=%s "
            "path=%s referer=%s "
            "source_referer=%s ua=%s",
            skip_kind,
            ip,
            client_label,
            visitor_label,
            path[:300],
            referer,
            source_referer[:300],
            user_agent[:300],
        )
        return HttpResponse(status=204)

    sticky_reason = cache.get(
        f"traffic_bot_like_client:{client_label}"
    )
   
    if sticky_reason:
        # Když už jsme klienta překlasifikovali jako bota,
        # nesmí zůstat ani ve slabém ani silném JS signálu.
        DailyBrowserVisitor.objects.filter(
            day=today,
            client_hash=client_hash,
        ).delete()

        DailyEngagedVisitor.objects.filter(
            day=today,
            client_hash=client_hash,
        ).delete()

        DailyEngagedPageVisitor.objects.filter(
            day=today,
            client_hash=client_hash,
        ).delete()

        logger.info(
            "%s reason=sticky_bot_like:%s "
            "ip=%s client=%s visitor=%s "
            "path=%s referer=%s "
            "source_referer=%s ua=%s",
            skip_kind,
            sticky_reason,
            ip,
            client_label,
            visitor_label,
            path[:300],
            referer,
            source_referer[:300],
            user_agent[:300],
        )
        return HttpResponse(status=204)

    recent_cutoff = (
        timezone.now()
        - timedelta(minutes=15)
    )

    # Nejdřív zkusíme přesně stejného návštěvníka.
    # visitor_hash zahrnuje IP + User-Agent.
    matching_visit = (
        DailyPageVisitor.objects
        .filter(
            day=today,
            visitor_hash=visitor_hash,
            path=path,
            last_seen_at__gte=recent_cutoff,
        )
        .order_by("-last_seen_at")
        .first()
    )

    # Fallback přes client_hash.
    # Je důležitý hlavně pro FB/IG in-app browser,
    # kde se User-Agent může mezi requesty lehce změnit.
    if not matching_visit:
        matching_visit = (
            DailySiteVisitor.objects
            .filter(
                day=today,
                client_hash=client_hash,
                last_path=path,
                last_seen_at__gte=recent_cutoff,
            )
            .order_by("-last_seen_at")
            .first()
        )

    # U velmi rychlého odchodu může pagehide beacon
    # dorazit těsně poté, co už další GET změnil
    # DailySiteVisitor.last_path.
    #
    # Proto pro browser-stage dovolíme ještě fallback
    # přes konkrétní pageview stejného klienta.
    if not matching_visit and stage == "browser":
        matching_visit = (
            DailyPageVisitor.objects
            .filter(
                day=today,
                client_hash=client_hash,
                path=path,
                last_seen_at__gte=recent_cutoff,
            )
            .order_by("-last_seen_at")
            .first()
        )

    # U velmi rychlého odchodu může pagehide beacon
    # dorazit těsně poté, co už další GET změnil
    # DailySiteVisitor.last_path.
    #
    # Proto pro browser-stage dovolíme bezpečný fallback
    # přes konkrétní pageview.
    if not matching_visit and stage == "browser":
        matching_visit = (
            DailyPageVisitor.objects
            .filter(
                day=today,
                client_hash=client_hash,
                path=path,
                last_seen_at__gte=(
                    timezone.now()
                    - timedelta(minutes=15)
                ),
            )
            .order_by("-last_seen_at")
            .first()
        )

    if not matching_visit:
        logger.info(
            "%s reason=no_matching_visit "
            "ip=%s client=%s visitor=%s "
            "path=%s referer=%s "
            "source_referer=%s ua=%s",
            skip_kind,
            ip,
            client_label,
            visitor_label,
            path[:300],
            referer,
            source_referer[:300],
            user_agent[:300],
        )
        return HttpResponse(status=204)

    confirmed_visitor_hash = (
        matching_visit.visitor_hash
    )
    confirmed_visitor_label = (
        confirmed_visitor_hash[:8]
    )

    attribution_referer = source_referer

    if (
        source_visitor_label
        and source_visitor_label
        != confirmed_visitor_label
    ):
        attribution_referer = ""

    source = classify_engaged_source(
        attribution_referer,
        user_agent,
    )

    # --------------------------------------------
    # STAGE 1: skutečně spuštěný viditelný browser
    # --------------------------------------------
    if stage == "browser":
        trigger = (
            request.POST.get("trigger")
            or "unknown"
        ).strip().lower()[:30]

        defaults = {
            "client_hash": client_hash,
            "first_path": path,
            "last_path": path,
            "confirmations": 0,
            "source": source,
            "source_referer": (
                attribution_referer[:300]
            ),
        }

        try:
            browser, _created = (
                DailyBrowserVisitor.objects
                .get_or_create(
                    day=today,
                    visitor_hash=(
                        confirmed_visitor_hash
                    ),
                    defaults=defaults,
                )
            )
        except IntegrityError:
            browser = (
                DailyBrowserVisitor.objects.get(
                    day=today,
                    visitor_hash=(
                        confirmed_visitor_hash
                    ),
                )
            )

        DailyBrowserVisitor.objects.filter(
            pk=browser.pk
        ).update(
            client_hash=client_hash,
            last_seen_at=timezone.now(),
            last_path=path,
            confirmations=F("confirmations") + 1,
        )

        logger.info(
            "BROWSER_CONFIRMED "
            "ip=%s client=%s visitor=%s "
            "beacon_visitor=%s "
            "method=POST status=204 "
            "path=%s trigger=%s "
            "referer=%s source_referer=%s "
            "ua=%s",
            ip,
            client_label,
            confirmed_visitor_label,
            visitor_label,
            path[:300],
            trigger,
            referer,
            attribution_referer[:300],
            user_agent[:300],
        )

        return HttpResponse(status=204)

    # --------------------------------------------
    # STAGE 2: původní 3s engagement
    # --------------------------------------------
    defaults = {
        "client_hash": client_hash,
        "first_path": path,
        "last_path": path,
        "beacons": 0,
        "source": source,
        "source_referer": (
            attribution_referer[:300]
        ),
    }

    try:
        engaged, _created = (
            DailyEngagedVisitor.objects
            .get_or_create(
                day=today,
                visitor_hash=confirmed_visitor_hash,
                defaults=defaults,
            )
        )
    except IntegrityError:
        engaged = (
            DailyEngagedVisitor.objects.get(
                day=today,
                visitor_hash=confirmed_visitor_hash,
            )
        )

    DailyEngagedVisitor.objects.filter(
        pk=engaged.pk
    ).update(
        client_hash=client_hash,
        last_seen_at=timezone.now(),
        last_path=path,
        beacons=F("beacons") + 1,
    )


    # --------------------------------------------
    # 3s engagement pro konkrétní stránku
    # --------------------------------------------
    page_source = classify_engaged_page_source(
        attribution_referer,
        user_agent,
    )

    try:
        engaged_page, _created = (
            DailyEngagedPageVisitor.objects
            .get_or_create(
                day=today,
                path=path,
                visitor_hash=confirmed_visitor_hash,
                defaults={
                    "client_hash": client_hash,
                    "beacons": 0,
                    "source": page_source,
                    "source_referer": (
                        attribution_referer[:300]
                    ),
                },
            )
        )
    except IntegrityError:
        engaged_page = (
            DailyEngagedPageVisitor.objects
            .get(
                day=today,
                path=path,
                visitor_hash=confirmed_visitor_hash,
            )
        )

    DailyEngagedPageVisitor.objects.filter(
        pk=engaged_page.pk
    ).update(
        client_hash=client_hash,
        last_seen_at=timezone.now(),
        beacons=F("beacons") + 1,
    )

    logger.info(
        "ENGAGED "
        "ip=%s client=%s visitor=%s "
        "beacon_visitor=%s "
        "method=POST status=204 "
        "path=%s referer=%s "
        "source_referer=%s ua=%s",
        ip,
        client_label,
        confirmed_visitor_label,
        visitor_label,
        path[:300],
        referer,
        attribution_referer[:300],
        user_agent[:300],
    )

    return HttpResponse(status=204)