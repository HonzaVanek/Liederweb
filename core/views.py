from urllib.parse import urldefrag
from django.shortcuts import render, redirect
from django.contrib.auth.views import LoginView
from django.views.generic import ListView, DetailView, CreateView, UpdateView
from django.views.decorators.http import require_POST
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.utils import timezone
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode, url_has_allowed_host_and_scheme
from django.contrib.auth.models import User
from django.contrib.auth.tokens import default_token_generator
from django.utils.encoding import force_bytes
from django.urls import reverse
from django.template.loader import render_to_string
from django.core.mail import EmailMessage, send_mail
from django.utils.decorators import method_decorator

from .forms import VlastniLoginForm, RegistraceForm, PersonForm, NewsletterSignupForm
from .models import Person
from events.models import Event
from media_assets.models import MediaAsset
from social_feed.models import SocialPost, SocialSource
from .decorators import staff_required
from rozesilac.models import Contact
from rozesilac.services import get_web_contacts_group






### hlavní landing page ####

def home(request):
    now = timezone.now()

    upcoming_event = (
        Event.objects.filter(is_published=True, starts_at__gte=now)
        .order_by("starts_at")
        .first()
    )

    latest_past_event = (
        Event.objects.filter(is_published=True, starts_at__lt=now)
        .order_by("-starts_at")
        .first()
    )

    featured_event = upcoming_event or latest_past_event

    featured_facebook_post = (
        SocialPost.objects.select_related("source")
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

    # Zatím jednoduché ruční řešení:
    # sem si můžeš dát konkrétní ID assetu, který chceš na homepage.
    MANUAL_HOME_ASSET_ID = None

    manual_home_asset = None

    if MANUAL_HOME_ASSET_ID:
        manual_home_asset = (
            MediaAsset.objects.filter(
                pk=MANUAL_HOME_ASSET_ID,
                asset_type=MediaAsset.AssetType.IMAGE,
                is_active=True,
            )
            .first()
        )

    if not manual_home_asset:
        manual_home_asset = (
            MediaAsset.objects.filter(
                asset_type=MediaAsset.AssetType.IMAGE,
                is_active=True,
            )
            .order_by("-uploaded_at")
            .first()
        )

    return render(
        request,
        "core/home.html",
        {
            "featured_event": featured_event,
            "featured_facebook_post": featured_facebook_post,
            "recent_facebook_posts": recent_facebook_posts,
            "manual_home_asset": manual_home_asset,
            "now": now,
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


def get_recent_person_image_assets(selected_asset=None, limit=16):
    assets = list(
        MediaAsset.objects.filter(
            asset_type=MediaAsset.AssetType.IMAGE,
            is_active=True,
        ).order_by("-uploaded_at")[:limit]
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
