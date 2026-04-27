from django import forms
from django.forms import inlineformset_factory, BaseInlineFormSet
from django.utils import timezone
from .models import (Event, EventArtist, EventProgramItem, EventPracticalInfo, EventResource, EventSponsor, EventTicketSettings, EventTicketVariant)
from rozesilac.models import EmailImage
from media_assets.models import MediaAsset



def get_event_image_assets_queryset():
    return MediaAsset.objects.filter(
        asset_type=MediaAsset.AssetType.IMAGE,
        is_active=True,
    ).order_by("-uploaded_at")

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
            "poster_asset",
            "hero_asset",
            "hero_image_position",
            "hero_parallax_enabled",
            "secondary_asset",
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

        image_qs = get_event_image_assets_queryset()

        for field_name in ["poster_asset", "hero_asset", "secondary_asset"]:
            self.fields[field_name].queryset = image_qs
            self.fields[field_name].required = False
            self.fields["poster_asset"].label = "Poster Image"
            self.fields["hero_asset"].label = "Hero Image"
            self.fields["secondary_asset"].label = "Secondary Image"

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
    fields=["sort_order", "name", "role", "url", "photo_asset", "photo_position"],
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
    fields=["sort_order", "name", "logo_asset", "url"],
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



#vstupenky:

def build_ticket_title_from_event(event):
    return (event.title or "").strip()


def build_ticket_artists_text_from_event(event):
    artist_names = [
        artist.name.strip()
        for artist in event.artists.all().order_by("sort_order", "id")
        if (artist.name or "").strip()
    ]
    return " | ".join(artist_names)


def build_ticket_venue_text_from_event(event):
    return (event.venue or "").strip()


def build_ticket_datetime_text_from_event(event):
    if not event.starts_at:
        return ""

    dt = timezone.localtime(event.starts_at)
    return f"{dt.day}. {dt.month}. {dt.year} od {dt:%H:%M}"


def get_default_ticket_variant_initials():
    return [
        {
            "code": "discounted",
            "name": "Zlevněné vstupné",
            "price": 150,
            "ticket_price_text": "Cena: 150 Kč",
            "allow_personalization": False,
            "sort_order": 10,
            "is_active": True,
        },
        {
            "code": "full",
            "name": "Plné vstupné",
            "price": 300,
            "ticket_price_text": "Cena: 300 Kč",
            "allow_personalization": False,
            "sort_order": 20,
            "is_active": True,
        },
        {
            "code": "honorary",
            "name": "Čestná vstupenka",
            "price": "",
            "ticket_price_text": "Čestná vstupenka",
            "allow_personalization": True,
            "sort_order": 30,
            "is_active": True,
        },
    ]


class EventTicketSettingsForm(forms.ModelForm):
    class Meta:
        model = EventTicketSettings
        fields = [
            "enabled",
            "logo_asset",
            "header_text",
            "ticket_title",
            "ticket_artists_text",
            "ticket_venue_text",
            "ticket_datetime_text",
            "default_tickets_per_page",
        ]
        widgets = {
            "header_text": forms.TextInput(attrs={"placeholder": "Např. VSTUPENKA"}),
            "ticket_title": forms.TextInput(attrs={"placeholder": "Název akce pro tisk na vstupenku"}),
            "ticket_artists_text": forms.Textarea(
                attrs={
                    "rows": 3,
                    "placeholder": "Např. Tamara Morozová | Demian Ewig | Adam Born",
                }
            ),
            "ticket_venue_text": forms.TextInput(attrs={"placeholder": "Např. Muzeum Bedřicha Smetany"}),
            "ticket_datetime_text": forms.TextInput(attrs={"placeholder": "Např. 15. 3. 2026 od 18:00"}),
        }

    def __init__(self, *args, event=None, **kwargs):
        super().__init__(*args, **kwargs)

        self.event = event
        self.fields["logo_asset"].queryset = get_event_image_assets_queryset()
        self.fields["logo_asset"].required = False
        self.fields["logo_asset"].label = "Logo pro vstupenky"

        # Předvyplnění jen při prvním založení.
        # Jakmile záznam existuje, nic automaticky nepřepisujeme.
        if event and not (self.instance and self.instance.pk):
            self.initial.setdefault("enabled", True)
            self.initial.setdefault("header_text", "VSTUPENKA")
            self.initial.setdefault("ticket_title", build_ticket_title_from_event(event))
            self.initial.setdefault("ticket_artists_text", build_ticket_artists_text_from_event(event))
            self.initial.setdefault("ticket_venue_text", build_ticket_venue_text_from_event(event))
            self.initial.setdefault("ticket_datetime_text", build_ticket_datetime_text_from_event(event))

    def clean_ticket_title(self):
        return (self.cleaned_data.get("ticket_title") or "").strip()

    def clean_ticket_artists_text(self):
        return (self.cleaned_data.get("ticket_artists_text") or "").strip()

    def clean_ticket_venue_text(self):
        return (self.cleaned_data.get("ticket_venue_text") or "").strip()

    def clean_ticket_datetime_text(self):
        return (self.cleaned_data.get("ticket_datetime_text") or "").strip()


class EventTicketVariantForm(forms.ModelForm):
    class Meta:
        model = EventTicketVariant
        fields = [
            "code",
            "name",
            "price",
            "ticket_price_text",
            "allow_personalization",
            "sort_order",
            "is_active",
        ]
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "Např. Zlevněné vstupné"}),
            "price": forms.NumberInput(attrs={"step": "0.01", "placeholder": "Např. 150"}),
            "ticket_price_text": forms.TextInput(
                attrs={"placeholder": "Např. Cena: 150 Kč nebo Čestná vstupenka"}
            ),
        }

    def clean_name(self):
        return (self.cleaned_data.get("name") or "").strip()

    def clean_ticket_price_text(self):
        return (self.cleaned_data.get("ticket_price_text") or "").strip()


class BaseEventTicketVariantFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()

        used_codes = set()

        for form in self.forms:
            if not hasattr(form, "cleaned_data"):
                continue

            if not form.cleaned_data or form.cleaned_data.get("DELETE"):
                continue

            code = form.cleaned_data.get("code")
            if code in used_codes:
                raise forms.ValidationError("Každý typ varianty může být u koncertu jen jednou.")
            if code:
                used_codes.add(code)


EventTicketVariantFormSet = inlineformset_factory(
    Event,
    EventTicketVariant,
    form=EventTicketVariantForm,
    formset=BaseEventTicketVariantFormSet,
    fields=[
        "code",
        "name",
        "price",
        "ticket_price_text",
        "allow_personalization",
        "sort_order",
        "is_active",
    ],
    extra=0,
    can_delete=True,
)

InitialEventTicketVariantFormSet = inlineformset_factory(
    Event,
    EventTicketVariant,
    form=EventTicketVariantForm,
    formset=BaseEventTicketVariantFormSet,
    fields=[
        "code",
        "name",
        "price",
        "ticket_price_text",
        "allow_personalization",
        "sort_order",
        "is_active",
    ],
    extra=3,
    can_delete=True,
)