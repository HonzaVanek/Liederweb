# events/admin.py

from django.contrib import admin
from .models import Event, VipReservation


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ("title", "starts_at", "venue", "vip_enabled", "is_published")
    prepopulated_fields = {"slug": ("title",)}


@admin.register(VipReservation)
class VipReservationAdmin(admin.ModelAdmin):
    list_display = ("event", "contact", "created_at")