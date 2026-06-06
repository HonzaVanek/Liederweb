from django.core.validators import RegexValidator
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.text import slugify

from rozesilac.models import EmailImage, EmailCampaign, Contact
from media_assets.models import MediaAsset



HEX_COLOR_VALIDATOR = RegexValidator(
    regex=r"^#[0-9A-Fa-f]{6}$",
    message="Zadej barvu ve formátu #RRGGBB.",
)


class Event(models.Model):
    HERO_POSITION_CHOICES = [("top", "Nahoře"), ("center", "Uprostřed"), ("bottom", "Dole"),]
    
    title = models.CharField(max_length=255)
    subtitle = models.CharField(max_length=255, blank=True)

    slug = models.SlugField(unique=True)
    starts_at = models.DateTimeField(null=True, blank=True)
    venue = models.CharField(max_length=255, blank=True)
    venue_address = models.CharField(max_length=255, blank=True)
    venue_map_url = models.URLField(blank=True)

    duration_text = models.CharField(max_length=120, blank=True)

    public_text = models.TextField(blank=True)
    program_intro = models.TextField(blank=True)
    educational_text = models.TextField(blank=True)

    theme_color = models.CharField(max_length=7, default="#7B2738", validators=[HEX_COLOR_VALIDATOR])

    poster_image = models.ForeignKey(EmailImage, null=True, blank=True, on_delete=models.SET_NULL, related_name="events_as_poster",)
    hero_image = models.ForeignKey(EmailImage, null=True, blank=True, on_delete=models.SET_NULL, related_name="events_as_hero",)
    hero_image_position = models.CharField(max_length=10, choices=HERO_POSITION_CHOICES, default="center")
    hero_parallax_enabled = models.BooleanField(default=False)
    secondary_image = models.ForeignKey(EmailImage, null=True, blank=True, on_delete=models.SET_NULL, related_name="events_as_secondary",)

    youtube_url = models.URLField(blank=True)

    tickets_url = models.URLField(blank=True)
    tickets_label = models.CharField(max_length=80, blank=True, default="Koupit vstupenky")

    vip_enabled = models.BooleanField(default=False)
    is_published = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    poster_asset = models.ForeignKey(
        MediaAsset,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="events_as_poster_asset",
        limit_choices_to={"asset_type": "image", "is_active": True},
    )

    hero_asset = models.ForeignKey(
        MediaAsset,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="events_as_hero_asset",
        limit_choices_to={"asset_type": "image", "is_active": True},
    )

    secondary_asset = models.ForeignKey(
        MediaAsset,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="events_as_secondary_asset",
        limit_choices_to={"asset_type": "image", "is_active": True},
    )

    class Meta:
        ordering = ["-starts_at", "-created_at"]

    def __str__(self):
        return self.title
    
    @property
    def poster_media(self):
        return self.poster_asset or self.poster_image

    @property
    def hero_media(self):
        return self.hero_asset or self.hero_image

    @property
    def secondary_media(self):
        return self.secondary_asset or self.secondary_image

    @property
    def youtube_embed_url(self):
        url = (self.youtube_url or "").strip()
        if not url:
            return ""

        if "youtube.com/watch?v=" in url:
            video_id = url.split("watch?v=")[1].split("&")[0]
            return f"https://www.youtube.com/embed/{video_id}"

        if "youtu.be/" in url:
            video_id = url.split("youtu.be/")[1].split("?")[0]
            return f"https://www.youtube.com/embed/{video_id}"

        if "youtube.com/embed/" in url:
            return url

        return ""


class EventProgramItem(models.Model):
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="program_items")
    sort_order = models.PositiveSmallIntegerField(default=0)
    composer = models.CharField(max_length=200, blank=True)
    work_title = models.CharField(max_length=255)
    note = models.TextField(blank=True)
    info_url = models.URLField(blank=True)

    class Meta:
        ordering = ["sort_order", "id"]

    def __str__(self):
        if self.composer:
            return f"{self.composer} – {self.work_title}"
        return self.work_title


class EventArtist(models.Model):
    PHOTO_POSITION_CHOICES = [
        ("top", "Nahoře"),
        ("center", "Uprostřed"),
        ("bottom", "Dole"),
    ]
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="artists")
    sort_order = models.PositiveSmallIntegerField(default=0)
    name = models.CharField(max_length=200)
    role = models.CharField(max_length=200, blank=True)
    url = models.URLField(blank=True)
    photo_image = models.ForeignKey(
        EmailImage,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="event_artist_photos",
    )
    photo_position = models.CharField(
        max_length=10,
        choices=PHOTO_POSITION_CHOICES,
        default="center",
    )

    photo_asset = models.ForeignKey(
        MediaAsset,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="event_artist_photo_assets",
        limit_choices_to={"asset_type": "image", "is_active": True},
    )

    class Meta:
        ordering = ["sort_order", "id"]

    def __str__(self):
        return self.name
    
    @property
    def photo_media(self):
        return self.photo_asset or self.photo_image


class EventGalleryImage(models.Model):
    event = models.ForeignKey(
        Event,
        on_delete=models.CASCADE,
        related_name="gallery_images",
    )
    sort_order = models.PositiveSmallIntegerField(default=0)
    image_asset = models.ForeignKey(
        MediaAsset,
        on_delete=models.CASCADE,
        related_name="event_gallery_images",
        limit_choices_to={"asset_type": "image", "is_active": True},
    )
    caption = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["sort_order", "id"]

    def __str__(self):
        return f"{self.event.title} – {self.image_asset}"


class EventResource(models.Model):
    RESOURCE_TYPES = [
        ("wiki", "Wikipedia"),
        ("article", "Článek"),
        ("video", "Video"),
        ("playlist", "Playlist"),
        ("other", "Jiný odkaz"),
    ]

    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="resources")
    sort_order = models.PositiveSmallIntegerField(default=0)
    title = models.CharField(max_length=255)
    url = models.URLField()
    resource_type = models.CharField(max_length=20, choices=RESOURCE_TYPES, default="article")

    class Meta:
        ordering = ["sort_order", "id"]

    def __str__(self):
        return self.title


class EventPracticalInfo(models.Model):
    INFO_TYPES = [
        ("drinks", "Nápoje do sálu"),
        ("clap", "Tleskejte, když chcete"),
        ("phones", "Mobily na silent"),
        ("arrival", "Přijďte včas"),
        ("dress", "Dress code není nutný"),
        ("other", "Jiné"),
    ]

    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="practical_infos")
    sort_order = models.PositiveSmallIntegerField(default=0)
    info_type = models.CharField(max_length=20, choices=INFO_TYPES, default="other")
    title = models.CharField(max_length=120)
    text = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["sort_order", "id"]

    def __str__(self):
        return self.title


class EventSponsor(models.Model):
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="sponsors")
    sort_order = models.PositiveSmallIntegerField(default=0)
    name = models.CharField(max_length=200)
    logo_image = models.ForeignKey(
        EmailImage,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="event_sponsor_logos",
    )

    logo_asset = models.ForeignKey(
        MediaAsset,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="event_sponsor_logo_assets",
        limit_choices_to={"asset_type": "image", "is_active": True},
    )

    url = models.URLField(blank=True)

    class Meta:
        ordering = ["sort_order", "id"]

    def __str__(self):
        return self.name
    
    @property
    def logo_media(self):
        return self.logo_asset or self.logo_image
    


class VipReservation(models.Model):
    STATUS_CHOICES = [("active", "Aktivní"), ("cancelled", "Zrušeno hostem"),]
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="vip_reservations")
    contact = models.ForeignKey("rozesilac.Contact", on_delete=models.CASCADE, related_name="vip_reservations")
    
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="active",
        db_index=True,
        verbose_name="Stav",
    )
    cancelled_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Zrušeno",
    )

    campaign = models.ForeignKey(
        "rozesilac.EmailCampaign",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="vip_reservations",
    )
    delivery = models.ForeignKey(
        "rozesilac.EmailDelivery",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="vip_reservations",
    )
    ticket_count = models.PositiveSmallIntegerField(default=1, verbose_name="Počet vstupenek")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["event", "contact"], name="unique_vip_reservation_per_event_contact")
        ]

    def __str__(self):
        return f"{self.contact.email} – {self.event.title}"
    


class EventTicketSettings(models.Model):
    TICKETS_PER_PAGE_CHOICES = [(4, "4 vstupenky na A4"), (5, "5 vstupenek na A4"),]

    event = models.OneToOneField(Event, on_delete=models.CASCADE, related_name="ticket_settings")
    enabled = models.BooleanField(default=False, verbose_name="Generování vstupenek povoleno")

    logo_image = models.ForeignKey(
        EmailImage,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="events_as_ticket_logo",
        verbose_name="Logo na vstupence",
        help_text="Když nevyplníš, při generování se použije výchozí logo LS (takže asi nevyplňuj - jenom kdybys chtěla jiné logo).",
    )

    logo_asset = models.ForeignKey(
        MediaAsset,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="events_as_ticket_logo_asset",
        limit_choices_to={"asset_type": "image", "is_active": True},
        verbose_name="Logo na vstupence",
        help_text="Když nevyplníš, při generování se použije výchozí logo LS (takže asi nevyplňuj - jenom kdybys chtěla jiné logo).",
    )

    header_text = models.CharField(
        max_length=80,
        default="VSTUPENKA",
        verbose_name="Nadpis na vstupence (defaultně prostě 'VSTUPENKA')",
    )

    ticket_title = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Název akce na vstupence",
        # help_text="Finální text pro tisk. Při založení se může předvyplnit z názvu koncertu.",
    )

    ticket_artists_text = models.TextField(
        blank=True,
        verbose_name="Interpreti na vstupence",
        help_text="Finální text pro tisk. Může být na jeden nebo dva řádky",
    )

    ticket_venue_text = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Místo konání koncertu na vstupence",
        help_text="Např. „Muzeum Bedřicha Smetany“",
    )

    ticket_datetime_text = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Datum a čas na vstupence",
        help_text="Např. „15. března 2026 od 18:00 hod“",
    )

    default_tickets_per_page = models.PositiveSmallIntegerField(
        choices=TICKETS_PER_PAGE_CHOICES,
        default=5,
        verbose_name="Výchozí počet vstupenek na stránku (asi podle počtu řádku interpretů aby se to vešlo na A4)",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Nastavení vstupenek koncertu"
        verbose_name_plural = "Nastavení vstupenek koncertů"

    def __str__(self):
        return f"Vstupenky – {self.event.title}"
    
    @property
    def logo_media(self):
        return self.logo_asset or self.logo_image

    def clean(self):
        errors = {}

        if self.enabled:
            if not (self.ticket_title or "").strip():
                errors["ticket_title"] = "Vyplň název koncertu na vstupence."

            if not (self.ticket_venue_text or "").strip():
                errors["ticket_venue_text"] = "Vyplň místo konání."

            if not (self.ticket_datetime_text or "").strip():
                errors["ticket_datetime_text"] = "Vyplň datum a čas akce."

        if errors:
            raise ValidationError(errors)
        


class EventTicketVariant(models.Model):
    VARIANT_CODE_CHOICES = [
        ("discounted", "Zlevněná"),
        ("full", "Plná"),
        ("honorary", "Čestná"),
    ]

    event = models.ForeignKey(
        Event,
        on_delete=models.CASCADE,
        related_name="ticket_variants",
    )

    code = models.CharField(
        max_length=20,
        choices=VARIANT_CODE_CHOICES,
        verbose_name="Typ vstupenky",
    )

    name = models.CharField(
        max_length=100,
        verbose_name="Název varianty",
        help_text="Např. „Zlevněné vstupné“, „Plné vstupné“, „Čestná vstupenka“.",
    )

    price = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Cena",
        help_text="Volitelné. U čestné vstupenky může zůstat prázdné.",
    )

    ticket_price_text = models.CharField(
        max_length=120,
        blank=True,
        verbose_name="Text na vstupence",
        help_text="Např. „Cena: 150 Kč“ nebo „Čestná vstupenka“.",
    )

    allow_personalization = models.BooleanField(
        default=False,
        verbose_name="Povolit personalizaci",
        help_text="Zapni u varianty, která se může generovat se jménem hosta.",
    )

    sort_order = models.PositiveSmallIntegerField(
        default=0,
        verbose_name="Pořadí",
    )

    is_active = models.BooleanField(
        default=True,
        verbose_name="Aktivní",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_order", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["event", "code"],
                name="unique_ticket_variant_per_event_code",
            )
        ]
        verbose_name = "Varianta vstupenky"
        verbose_name_plural = "Varianty vstupenek"

    def __str__(self):
        return f"{self.event.title} – {self.name}"

    def clean(self):
        errors = {}

        if not (self.ticket_price_text or "").strip():
            errors["ticket_price_text"] = "Vyplň text, který se má tisknout na vstupence."

        if errors:
            raise ValidationError(errors)