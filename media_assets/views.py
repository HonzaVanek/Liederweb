from django.contrib import messages
from django.db.models import Q, Sum
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views.generic import ListView, CreateView, UpdateView
from django.db import transaction
from django.db.models.deletion import ProtectedError
from urllib.parse import unquote

from core.decorators import staff_required
from .forms import MediaAssetForm, MEDIA_ASSETS_TOTAL_LIMIT, MediaAssetBulkImageUploadForm
from .models import MediaAsset

from django.apps import apps
from django.conf import settings
from django.db import models

from pathlib import Path
from django.template.defaultfilters import filesizeformat
from django.views.generic.edit import FormView


def get_media_assets_total_size():
    return MediaAsset.objects.aggregate(total=Sum("file_size"))["total"] or 0


def get_asset_reference_needles(asset):
    """
    Vrací různé podoby odkazu/cesty k assetu, které můžou být někde uložené
    v databázi nebo natvrdo v šabloně.
    """
    needles = set()

    if not asset.file:
        return needles

    if asset.file.name:
        # Např. media_assets/document/2026/07/soubor.pdf
        needles.add(asset.file.name)

        # Např. /media_assets/document/2026/07/soubor.pdf
        needles.add("/" + asset.file.name.lstrip("/"))

        # Samotný uložený název souboru, typicky hash.pdf
        needles.add(Path(asset.file.name).name)

    try:
        file_url = asset.file.url
    except ValueError:
        file_url = ""

    if file_url:
        # Např. /media/media_assets/document/2026/07/soubor.pdf
        needles.add(file_url)
        needles.add(unquote(file_url))

    return {needle for needle in needles if needle}


def get_asset_relation_usage(asset):
    """
    Najde použití přes skutečné databázové vazby na MediaAsset.
    Tedy ForeignKey, OneToOneField a ManyToManyField.
    """
    usage_items = []
    asset_model = asset.__class__

    for model in apps.get_models():
        if model == asset_model:
            continue

        for field in model._meta.get_fields():
            if field.auto_created and not field.concrete:
                continue

            if not getattr(field, "is_relation", False):
                continue

            if not getattr(field, "remote_field", None):
                continue

            if field.remote_field.model != asset_model:
                continue

            if isinstance(field, (models.ForeignKey, models.OneToOneField)):
                count = model.objects.filter(**{field.name: asset}).count()
            elif isinstance(field, models.ManyToManyField):
                count = model.objects.filter(**{field.name: asset}).distinct().count()
            else:
                continue

            if count:
                label = f"{model._meta.verbose_name_plural} – {field.verbose_name}"
                usage_items.append((label, count))

    return usage_items


def get_asset_database_text_usage(asset):
    """
    Najde výskyty cesty/URL assetu v textových polích databáze.
    Hodí se pro HTML obsah, textové bloky, ručně vložené odkazy atd.
    """
    usage_items = []
    needles = get_asset_reference_needles(asset)

    if not needles:
        return usage_items

    text_field_types = (
        models.CharField,
        models.TextField,
        models.URLField,
    )

    for model in apps.get_models():
        # Nechceme najít asset sám v MediaAsset tabulce.
        if model == asset.__class__:
            continue

        q = Q()

        for field in model._meta.fields:
            if isinstance(field, text_field_types):
                for needle in needles:
                    q |= Q(**{f"{field.name}__icontains": needle})

        if not q.children:
            continue

        try:
            count = model.objects.filter(q).distinct().count()
        except Exception:
            continue

        if count:
            label = f"{model._meta.verbose_name_plural} – textový/HTML odkaz"
            usage_items.append((label, count))

    return usage_items


def get_asset_template_usage(asset):
    """
    Najde natvrdo vložené odkazy v Django šablonách.
    Tohle pokryje přesně případy typu contact.html.
    """
    usage_items = []
    needles = get_asset_reference_needles(asset)

    if not needles:
        return usage_items

    roots = set()

    # Globální template dirs ze settings.py
    for template_config in settings.TEMPLATES:
        for template_dir in template_config.get("DIRS", []):
            roots.add(Path(template_dir))

        # App templates: app/templates/...
        if template_config.get("APP_DIRS"):
            for app_config in apps.get_app_configs():
                roots.add(Path(app_config.path) / "templates")

    allowed_suffixes = {".html", ".txt"}

    for root in roots:
        if not root.exists():
            continue

        for path in root.rglob("*"):
            if not path.is_file():
                continue

            if path.suffix.lower() not in allowed_suffixes:
                continue

            try:
                content = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                try:
                    content = path.read_text(encoding="utf-8", errors="ignore")
                except Exception:
                    continue
            except Exception:
                continue

            if any(needle in content for needle in needles):
                try:
                    display_path = path.relative_to(settings.BASE_DIR)
                except ValueError:
                    display_path = path

                usage_items.append((f"Šablona – {display_path}", 1))

    return usage_items



def path_is_inside(child, parent):
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


def get_asset_python_source_usage(asset):
    """
    Najde natvrdo vložené odkazy na asset v Python kódu.
    Tohle pokryje případy, kdy se URL skládá ve view a do šablony jde jen jako proměnná.
    """
    usage_items = []
    needles = get_asset_reference_needles(asset)

    if not needles:
        return usage_items

    base_dir = Path(settings.BASE_DIR).resolve()
    roots = set()

    # Projdeme jen lokální appky projektu, ne celý site-packages.
    for app_config in apps.get_app_configs():
        app_path = Path(app_config.path).resolve()

        if path_is_inside(app_path, base_dir):
            roots.add(app_path)

    ignored_parts = {
        "__pycache__",
        "migrations",
        ".git",
        ".venv",
        "venv",
        "env",
        "node_modules",
    }

    for root in roots:
        if not root.exists():
            continue

        for path in root.rglob("*.py"):
            if not path.is_file():
                continue

            if any(part in ignored_parts for part in path.parts):
                continue

            try:
                content = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                try:
                    content = path.read_text(encoding="utf-8", errors="ignore")
                except Exception:
                    continue
            except Exception:
                continue

            if any(needle in content for needle in needles):
                try:
                    display_path = path.relative_to(base_dir)
                except ValueError:
                    display_path = path

                usage_items.append((f"Python kód – {display_path}", 1))

    return usage_items


def get_asset_usage(asset):
    usage_items = []

    usage_items.extend(get_asset_relation_usage(asset))
    usage_items.extend(get_asset_database_text_usage(asset))
    usage_items.extend(get_asset_template_usage(asset))
    usage_items.extend(get_asset_python_source_usage(asset))

    total = sum(count for _, count in usage_items)

    return {
        "usage_rows": usage_items,
        "total": total,
        "is_used": total > 0,
    }


@method_decorator(staff_required, name="dispatch")
class MediaAssetAdminListView(ListView):
    model = MediaAsset
    template_name = "media_assets/media_asset_list.html"
    context_object_name = "assets"
    paginate_by = 30

    def get_queryset(self):
        queryset = (
            MediaAsset.objects
            .select_related("uploaded_by")
            .order_by("-uploaded_at")
        )

        q = (self.request.GET.get("q") or "").strip()
        asset_type = (self.request.GET.get("type") or "").strip()
        status = (self.request.GET.get("status") or "").strip()

        if q:
            queryset = queryset.filter(
                Q(title__icontains=q)
                | Q(original_filename__icontains=q)
                | Q(description__icontains=q)
                | Q(credit__icontains=q)
                | Q(alt_text__icontains=q)
            )

        valid_types = {choice[0] for choice in MediaAsset.AssetType.choices}
        if asset_type in valid_types:
            queryset = queryset.filter(asset_type=asset_type)

        if status == "active":
            queryset = queryset.filter(is_active=True)
        elif status == "inactive":
            queryset = queryset.filter(is_active=False)

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        total_size = get_media_assets_total_size()
        context["page_title"] = "Mediální knihovna"
        context["current_q"] = (self.request.GET.get("q") or "").strip()
        context["current_type"] = (self.request.GET.get("type") or "").strip()
        context["current_status"] = (self.request.GET.get("status") or "").strip()
        context["asset_type_choices"] = MediaAsset.AssetType.choices
        context["total_size"] = total_size
        context["limit_size"] = MEDIA_ASSETS_TOTAL_LIMIT
        context["remaining_size"] = max(MEDIA_ASSETS_TOTAL_LIMIT - total_size, 0)
        context["storage_percent"] = min(round((total_size / MEDIA_ASSETS_TOTAL_LIMIT) * 100), 100) if MEDIA_ASSETS_TOTAL_LIMIT else 0
        return context


@method_decorator(staff_required, name="dispatch")
class MediaAssetCreateView(CreateView):
    model = MediaAsset
    form_class = MediaAssetForm
    template_name = "media_assets/media_asset_form.html"

    def form_valid(self, form):
        if not form.instance.uploaded_by:
            form.instance.uploaded_by = self.request.user

        response = super().form_valid(form)
        messages.success(self.request, "Soubor byl nahrán.")
        return response

    def get_success_url(self):
        return reverse("media_assets:asset_update", kwargs={"pk": self.object.pk})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "Nahrát nový asset"
        context["submit_label"] = "Nahrát soubor"
        context["asset"] = None
        return context


@method_decorator(staff_required, name="dispatch")
class MediaAssetUpdateView(UpdateView):
    model = MediaAsset
    form_class = MediaAssetForm
    template_name = "media_assets/media_asset_form.html"
    context_object_name = "asset"
    pk_url_kwarg = "pk"

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, "Asset byl uložen.")
        return response

    def get_success_url(self):
        return reverse("media_assets:asset_update", kwargs={"pk": self.object.pk})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = f"Upravit asset: {self.object.title or self.object.filename}"
        context["submit_label"] = "Uložit změny"
        context["asset_usage"] = get_asset_usage(self.object)
        return context


@staff_required
def asset_delete(request, pk):
    if request.method != "POST":
        return HttpResponseForbidden("Pouze POST.")

    asset = get_object_or_404(MediaAsset, pk=pk)

    asset_usage = get_asset_usage(asset)
    if asset_usage["is_used"]:
        messages.error(
            request,
            "Soubor nelze smazat, protože se stále používá jinde na webu."
        )
        return redirect("media_assets:asset_update", pk=asset.pk)

    storage = asset.file.storage if asset.file else None
    file_name = asset.file.name if asset.file else None

    try:
        asset.delete()
    except ProtectedError:
        messages.error(
            request,
            "Soubor nelze smazat, protože se stále používá jinde na webu."
        )
        return redirect("media_assets:asset_update", pk=asset.pk)

    if storage and file_name:
        transaction.on_commit(lambda: storage.delete(file_name))

    messages.success(request, "Soubor byl smazán.")
    return redirect("media_assets:asset_list")


@method_decorator(staff_required, name="dispatch")
class MediaAssetBulkImageUploadView(FormView):
    template_name = "media_assets/media_asset_bulk_upload.html"
    form_class = MediaAssetBulkImageUploadForm

    def form_valid(self, form):
        files = form.cleaned_data["files"]
        credit = form.cleaned_data["credit"]
        description = form.cleaned_data["description"]
        is_active = form.cleaned_data["is_active"]

        current_total_size = get_media_assets_total_size()
        upload_total_size = sum(uploaded_file.size for uploaded_file in files)

        if MEDIA_ASSETS_TOTAL_LIMIT and current_total_size + upload_total_size > MEDIA_ASSETS_TOTAL_LIMIT:
            remaining_size = max(MEDIA_ASSETS_TOTAL_LIMIT - current_total_size, 0)

            form.add_error(
                "files",
                (
                    "Vybrané soubory se nevejdou do limitu knihovny. "
                    f"Zbývá {filesizeformat(remaining_size)}, "
                    f"vybrané soubory mají {filesizeformat(upload_total_size)}."
                ),
            )
            return self.form_invalid(form)

        created_count = 0

        with transaction.atomic():
            for uploaded_file in files:
                title = Path(uploaded_file.name).stem.replace("_", " ").replace("-", " ").strip()

                asset = MediaAsset(
                    title=title,
                    file=uploaded_file,
                    credit=credit,
                    description=description,
                    is_active=is_active,
                    uploaded_by=self.request.user,
                )

                asset.save()
                created_count += 1

        messages.success(
            self.request,
            f"Nahráno souborů: {created_count}."
        )

        return redirect("media_assets:asset_list")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "Nahrát více fotek"
        context["submit_label"] = "Nahrát fotky"
        return context