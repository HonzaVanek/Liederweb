from django.contrib import admin
from .models import (ContactGroup, Contact, EmailTemplate, EmailCampaign, EmailDelivery, EmailCampaignTrackedLink, EmailClickEvent, EmailImage,)

@admin.register(ContactGroup)
class ContactGroupAdmin(admin.ModelAdmin):
    list_display = ("name", "created_at")
    search_fields = ("name",)
    ordering = ("name",)


@admin.register(Contact)
class ContactAdmin(admin.ModelAdmin):
    list_display = ("email", "name", "salutation", "is_active")
    list_filter = ("is_active", "groups")
    search_fields = ("email", "name", "salutation")
    filter_horizontal = ("groups",)
    ordering = ("email",)


@admin.register(EmailTemplate)
class EmailTemplateAdmin(admin.ModelAdmin):
    list_display = ("name", "subject", "preheader", "created_at", "updated_at")
    search_fields = ("name", "subject", "preheader")
    ordering = ("-updated_at",)


@admin.register(EmailCampaign)
class EmailCampaignAdmin(admin.ModelAdmin):
    list_display = ("subject", "template", "created_by", "is_test", "created_at")
    list_filter = ("is_test", "created_at", "created_by")
    search_fields = ("subject", "note")
    ordering = ("-created_at",)


@admin.register(EmailDelivery)
class EmailDeliveryAdmin(admin.ModelAdmin):
    list_display = ("to_email", "to_name", "campaign", "status", "sent_at", "created_at")
    list_filter = ("status", "created_at", "sent_at")
    search_fields = ("to_email", "to_name", "tracking_token", "error")
    ordering = ("-created_at",)
    readonly_fields = ("tracking_token", "clicked_at", "click_count", "unique_click_count")


@admin.register(EmailCampaignTrackedLink)
class EmailCampaignTrackedLinkAdmin(admin.ModelAdmin):
    list_display = ("campaign", "url")
    search_fields = ("url",)
    ordering = ("campaign", "id")


@admin.register(EmailClickEvent)
class EmailClickEventAdmin(admin.ModelAdmin):
    list_display = ("delivery", "original_url", "created_at", "is_suspected_bot", "is_duplicate")
    list_filter = ("is_suspected_bot", "is_duplicate", "created_at")
    search_fields = ("original_url", "delivery__to_email", "user_agent", "ip_address")
    ordering = ("-created_at",)


@admin.register(EmailImage)
class EmailImageAdmin(admin.ModelAdmin):
    list_display = ("title", "uploaded_by", "file_size", "uploaded_at")
    list_filter = ("uploaded_at", "uploaded_by")
    search_fields = ("title", "image")
    ordering = ("-uploaded_at",)