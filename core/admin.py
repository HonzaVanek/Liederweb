from django.contrib import admin
from django.utils import timezone

from .models import AgnesSupportIntent


@admin.register(AgnesSupportIntent)
class AgnesSupportIntentAdmin(admin.ModelAdmin):
    list_display = (
        "created_at",
        "donor_name",
        "donor_email",
        "donor_phone",
        "amount",
        "variable_symbol",
        "wants_receipt",
        "status",
        "paid_at",
    )
    list_filter = (
        "status",
        "wants_receipt",
        "created_at",
    )
    search_fields = (
        "donor_name",
        "donor_email",
        "donor_phone",
        "variable_symbol",
        "note",
    )
    readonly_fields = (
        "created_at",
        "paid_at",
        "variable_symbol",
    )
    ordering = ("-created_at",)

    actions = (
        "mark_as_paid",
        "mark_as_created",
        "mark_as_cancelled",
    )

    @admin.action(description="Označit jako zaplacené")
    def mark_as_paid(self, request, queryset):
        updated = queryset.update(
            status=AgnesSupportIntent.Status.PAID,
            paid_at=timezone.now(),
        )
        self.message_user(request, f"Označeno jako zaplacené: {updated}")

    @admin.action(description="Vrátit do stavu vytvořeno")
    def mark_as_created(self, request, queryset):
        updated = queryset.update(
            status=AgnesSupportIntent.Status.CREATED,
            paid_at=None,
        )
        self.message_user(request, f"Vráceno do stavu vytvořeno: {updated}")

    @admin.action(description="Označit jako zrušené")
    def mark_as_cancelled(self, request, queryset):
        updated = queryset.update(
            status=AgnesSupportIntent.Status.CANCELLED,
            paid_at=None,
        )
        self.message_user(request, f"Označeno jako zrušené: {updated}")