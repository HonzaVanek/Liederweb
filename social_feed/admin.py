from django.contrib import admin
from .models import SocialSource, SocialPost


@admin.register(SocialSource)
class SocialSourceAdmin(admin.ModelAdmin):
    list_display = ("name", "platform", "external_account_id", "is_active")
    list_filter = ("platform", "is_active")
    search_fields = ("name", "external_account_id")


@admin.register(SocialPost)
class SocialPostAdmin(admin.ModelAdmin):
    list_display = ("source", "external_post_id", "media_type", "published_at", "is_visible")
    list_filter = ("source__platform", "media_type", "is_visible")
    search_fields = ("external_post_id", "message", "permalink_url")
    readonly_fields = ("created_at", "fetched_at")