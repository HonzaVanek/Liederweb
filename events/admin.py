# events/admin.py

from django.contrib import admin

from .models import (
    Event,
    VipReservation,
    EventTicketSettings,
    EventTicketVariant,
)


class EventTicketSettingsInline(admin.StackedInline):
    model = EventTicketSettings
    extra = 0
    max_num = 1
    fk_name = "event"
    raw_id_fields = ("logo_image",)
    readonly_fields = ("created_at", "updated_at")

    fieldsets = (
        (
            "Vstupenky",
            {
                "fields": (
                    "enabled",
                    "logo_image",
                    "header_text",
                    "default_tickets_per_page",
                )
            },
        ),
        (
            "Texty pro tisk",
            {
                "fields": (
                    "ticket_title",
                    "ticket_artists_text",
                    "ticket_venue_text",
                    "ticket_datetime_text",
                )
            },
        ),
        (
            "Systémové údaje",
            {
                "classes": ("collapse",),
                "fields": ("created_at", "updated_at"),
            },
        ),
    )

    def get_extra(self, request, obj=None, **kwargs):
        if obj and hasattr(obj, "ticket_settings"):
            return 0
        return 1


class EventTicketVariantInline(admin.TabularInline):
    model = EventTicketVariant
    extra = 0
    fk_name = "event"
    readonly_fields = ("created_at", "updated_at")
    fields = (
        "code",
        "name",
        "price",
        "ticket_price_text",
        "allow_personalization",
        "sort_order",
        "is_active",
        "created_at",
        "updated_at",
    )
    ordering = ("sort_order", "id")


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "starts_at",
        "venue",
        "vip_enabled",
        "is_published",
    )
    list_filter = (
        "vip_enabled",
        "is_published",
        "starts_at",
    )
    search_fields = (
        "title",
        "subtitle",
        "venue",
        "slug",
    )
    prepopulated_fields = {"slug": ("title",)}
    date_hierarchy = "starts_at"
    inlines = [EventTicketSettingsInline, EventTicketVariantInline]


@admin.register(VipReservation)
class VipReservationAdmin(admin.ModelAdmin):
    list_display = (
        "event",
        "contact",
        "ticket_count",
        "created_at",
    )
    list_filter = (
        "event",
        "created_at",
    )
    search_fields = (
        "event__title",
        "contact__email",
        "contact__name",
    )
    readonly_fields = ("created_at",)


@admin.register(EventTicketSettings)
class EventTicketSettingsAdmin(admin.ModelAdmin):
    list_display = (
        "event",
        "enabled",
        "default_tickets_per_page",
        "updated_at",
    )
    list_filter = (
        "enabled",
        "default_tickets_per_page",
        "updated_at",
    )
    search_fields = (
        "event__title",
        "ticket_title",
        "ticket_venue_text",
        "ticket_datetime_text",
    )
    raw_id_fields = ("event", "logo_image")
    readonly_fields = ("created_at", "updated_at")


@admin.register(EventTicketVariant)
class EventTicketVariantAdmin(admin.ModelAdmin):
    list_display = (
        "event",
        "code",
        "name",
        "price",
        "allow_personalization",
        "is_active",
        "sort_order",
    )
    list_filter = (
        "code",
        "allow_personalization",
        "is_active",
    )
    search_fields = (
        "event__title",
        "name",
        "ticket_price_text",
    )
    raw_id_fields = ("event",)
    readonly_fields = ("created_at", "updated_at")
    ordering = ("event", "sort_order", "id")