from django.shortcuts import render, redirect
from django.contrib.auth.views import LoginView
from django.views.generic import ListView, DetailView, CreateView, UpdateView
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.contrib.auth.models import User
from django.contrib.auth.tokens import default_token_generator
from django.utils.encoding import force_bytes
from django.urls import reverse
from django.template.loader import render_to_string
from django.core.mail import EmailMessage, send_mail
from django.utils.decorators import method_decorator

from .forms import VlastniLoginForm, RegistraceForm, PersonForm
from .models import Person
from .decorators import staff_required

from media_assets.models import MediaAsset


def home(request):
    return render(request, "core/home.html")


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


class PersonListView(ListView):
    model = Person
    template_name = "core/person_list.html"
    context_object_name = "people"

    def get_queryset(self):
        return Person.objects.filter(is_published=True).order_by("sort_order", "name")


class PersonDetailView(DetailView):
    model = Person
    template_name = "core/person_detail.html"
    context_object_name = "person"
    slug_field = "slug"
    slug_url_kwarg = "slug"

    def get_queryset(self):
        return Person.objects.filter(is_published=True)


def get_recent_person_image_assets(selected_asset=None, limit=24):
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
        return Person.objects.all().order_by("sort_order", "name")


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