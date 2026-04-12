from django import forms
from django.forms import inlineformset_factory
from django.utils import timezone
from .models import (Event, EventArtist, EventProgramItem, EventPracticalInfo, EventResource, EventSponsor)
from rozesilac.models import EmailImage


class EventForm(forms.ModelForm):
    starts_at = forms.DateTimeField(
        required=False,
        input_formats=["%Y-%m-%dT%H:%M"],
        widget=forms.DateTimeInput(
            attrs={"type": "datetime-local"},
            format="%Y-%m-%dT%H:%M",
        ),
    )

    class Meta:
        model = Event
        fields = [
            "title",
            "subtitle",
            "slug",
            "starts_at",
            "venue",
            "venue_address",
            "venue_map_url",
            "duration_text",
            "theme_color",
            "poster_image",
            "hero_image",
            "hero_image_position",
            "hero_parallax_enabled",
            "secondary_image",
            "public_text",
            "program_intro",
            "educational_text",
            "youtube_url",
            "tickets_url",
            "tickets_label",
            "vip_enabled",
            "is_published",
        ]
        widgets = {
            "title": forms.TextInput(attrs={"placeholder": "Název koncertu"}),
            "subtitle": forms.TextInput(attrs={"placeholder": "Krátký podtitul koncertu"}),
            "slug": forms.TextInput(attrs={"placeholder": "např. krasna-magelona"}),
            "venue": forms.TextInput(attrs={"placeholder": "Místo konání"}),
            "venue_address": forms.TextInput(attrs={"placeholder": "Adresa pro mapy"}),
            "hero_image_position": forms.Select(),
            "venue_map_url": forms.URLInput(attrs={"placeholder": "Odkaz na Mapy.cz"}),
            "duration_text": forms.TextInput(attrs={"placeholder": "např. 1 hod 45 min včetně přestávky"}),
            "theme_color": forms.TextInput(attrs={"type": "color"}),
            "public_text": forms.Textarea(attrs={"rows": 5}),
            "program_intro": forms.Textarea(attrs={"rows": 4}),
            "educational_text": forms.Textarea(attrs={"rows": 6}),
            "youtube_url": forms.URLInput(attrs={"placeholder": "https://youtu.be/... nebo https://www.youtube.com/watch?v=..."}),
            "tickets_url": forms.URLInput(attrs={"placeholder": "https://..."}),
            "tickets_label": forms.TextInput(attrs={"placeholder": "např. Koupit vstupenky"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        image_qs = EmailImage.objects.all().order_by("-uploaded_at")

        for field_name in ["poster_image", "hero_image", "secondary_image"]:
            self.fields[field_name].queryset = image_qs
            self.fields[field_name].required = False

        if self.instance and self.instance.pk and self.instance.starts_at:
            self.initial["starts_at"] = timezone.localtime(
                self.instance.starts_at
            ).strftime("%Y-%m-%dT%H:%M")

    def clean_slug(self):
        slug = self.cleaned_data["slug"].lower()
        reserved = {"create", "edit", "koncerty", "vip", "public", "detail"}
        if slug in reserved:
            raise forms.ValidationError("Tento slug nelze použít.")
        return slug

EventProgramItemFormSet = inlineformset_factory(
    Event,
    EventProgramItem,
    fields=["sort_order", "composer", "work_title", "note", "info_url"],
    extra=3,
    can_delete=True,
)

EventArtistFormSet = inlineformset_factory(
    Event,
    EventArtist,
    fields=["sort_order", "name", "role", "url", "photo_image", "photo_position"],
    extra=3,
    can_delete=True,
)

EventResourceFormSet = inlineformset_factory(
    Event,
    EventResource,
    fields=["sort_order", "title", "url", "resource_type"],
    extra=3,
    can_delete=True,
)

EventPracticalInfoFormSet = inlineformset_factory(
    Event,
    EventPracticalInfo,
    fields=["sort_order", "info_type", "title", "text"],
    extra=3,
    can_delete=True,
)

EventSponsorFormSet = inlineformset_factory(
    Event,
    EventSponsor,
    fields=["sort_order", "name", "logo_image", "url"],
    extra=3,
    can_delete=True,
)

class VipReservationForm(forms.Form):
    TICKET_COUNT_CHOICES = [
        (1, "1 vstupenka"),
        (2, "2 vstupenky"),
        (3, "3 vstupenky"),
        (4, "4 vstupenky"),
    ]

    ticket_count = forms.TypedChoiceField(
        choices=TICKET_COUNT_CHOICES,
        coerce=int,
        initial=1,
        label="Počet vstupenek",
        widget=forms.RadioSelect,
    )