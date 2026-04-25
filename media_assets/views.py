from django.contrib import messages
from django.db.models import Q
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views.generic import ListView, CreateView, UpdateView

from core.decorators import staff_required
from .models import MediaAsset


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
        context["page_title"] = "Mediální knihovna"
        context["current_q"] = (self.request.GET.get("q") or "").strip()
        context["current_type"] = (self.request.GET.get("type") or "").strip()
        context["current_status"] = (self.request.GET.get("status") or "").strip()
        context["asset_type_choices"] = MediaAsset.AssetType.choices
        return context


@method_decorator(staff_required, name="dispatch")
class MediaAssetCreateView(CreateView):
    model = MediaAsset
    template_name = "media_assets/media_asset_form.html"
    fields = [
        "title",
        "file",
        "alt_text",
        "description",
        "credit",
        "is_active",
    ]

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
    template_name = "media_assets/media_asset_form.html"
    context_object_name = "asset"
    pk_url_kwarg = "pk"
    fields = [
        "title",
        "file",
        "alt_text",
        "description",
        "credit",
        "is_active",
    ]

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
        return context