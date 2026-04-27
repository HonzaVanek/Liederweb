from django.contrib import messages
from django.db.models import Q, Sum
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views.generic import ListView, CreateView, UpdateView

from core.decorators import staff_required
from .forms import MediaAssetForm, MEDIA_ASSETS_TOTAL_LIMIT
from .models import MediaAsset


def get_media_assets_total_size():
    return MediaAsset.objects.aggregate(total=Sum("file_size"))["total"] or 0


def get_asset_usage(asset):
    usage_items = []

    checks = [
        ("Profily lidí", asset.person_profiles.count()),
        ("Koncerty – plakát", asset.events_as_poster_asset.count()),
        ("Koncerty – hero", asset.events_as_hero_asset.count()),
        ("Koncerty – sekundární obrázek", asset.events_as_secondary_asset.count()),
        ("Interpreti koncertů", asset.event_artist_photo_assets.count()),
        ("Loga sponzorů", asset.event_sponsor_logo_assets.count()),
        ("Loga na vstupenkách", asset.events_as_ticket_logo_asset.count()),
    ]

    for label, count in checks:
        if count:
            usage_items.append((label, count))

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
    usage = get_asset_usage(asset)

    if usage["is_used"]:
        messages.error(
            request,
            "Soubor nelze smazat, protože se stále používá jinde na webu."
        )
        return redirect("media_assets:asset_update", pk=asset.pk)

    if asset.file:
        asset.file.delete(save=False)
    asset.delete()

    messages.success(request, "Soubor byl smazán.")
    return redirect("media_assets:asset_list")