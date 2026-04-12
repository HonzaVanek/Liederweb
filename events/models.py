from django.core.validators import RegexValidator
from django.db import models
from django.utils.text import slugify

from rozesilac.models import EmailImage, EmailCampaign, Contact



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

    class Meta:
        ordering = ["-starts_at", "-created_at"]

    def __str__(self):
        return self.title

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
    note = models.CharField(max_length=255, blank=True)
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

    class Meta:
        ordering = ["sort_order", "id"]

    def __str__(self):
        return self.name


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
    url = models.URLField(blank=True)

    class Meta:
        ordering = ["sort_order", "id"]

    def __str__(self):
        return self.name
    


class VipReservation(models.Model):
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="vip_reservations")
    contact = models.ForeignKey("rozesilac.Contact", on_delete=models.CASCADE, related_name="vip_reservations")

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