from django.db import models
from django.db.models import Q


class SocialSource(models.Model):
    class Platform(models.TextChoices):
        FACEBOOK = "facebook", "Facebook"
        INSTAGRAM = "instagram", "Instagram"

    platform = models.CharField(
        max_length=20,
        choices=Platform.choices,
        verbose_name="Platforma",
    )
    name = models.CharField(
        max_length=255,
        verbose_name="Název zdroje",
        help_text="Např. Lieder Society Facebook nebo Lieder Society Instagram",
    )
    external_account_id = models.CharField(
        max_length=255,
        unique=True,
        verbose_name="Externí ID účtu / stránky",
        help_text="Např. Facebook Page ID nebo Instagram User ID.",
    )
    profile_url = models.URLField(
        blank=True,
        max_length=1000,
        verbose_name="URL profilu / stránky",
    )
    is_active = models.BooleanField(
        default=True,
        db_index=True,
        verbose_name="Aktivní",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Vytvořeno",
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Upraveno",
    )

    class Meta:
        ordering = ["platform", "name"]
        verbose_name = "Zdroj sociálního obsahu"
        verbose_name_plural = "Zdroje sociálního obsahu"

    def __str__(self):
        return f"{self.get_platform_display()} – {self.name}"


class SocialPost(models.Model):
    class MediaType(models.TextChoices):
        IMAGE = "image", "Obrázek"
        VIDEO = "video", "Video"
        CAROUSEL = "carousel", "Carousel"
        TEXT = "text", "Text"
        OTHER = "other", "Ostatní"

    source = models.ForeignKey(
        SocialSource,
        on_delete=models.CASCADE,
        related_name="posts",
        verbose_name="Zdroj",
    )
    external_post_id = models.CharField(
        max_length=255,
        verbose_name="Externí ID postu",
    )

    message = models.TextField(
        blank=True,
        verbose_name="Text postu",
    )
    permalink_url = models.URLField(
        blank=True,
        max_length=1000,
        verbose_name="Odkaz na originální post",
    )

    media_type = models.CharField(
        max_length=20,
        choices=MediaType.choices,
        default=MediaType.OTHER,
        verbose_name="Typ média",
    )
    image_url = models.URLField(
        blank=True,
        max_length=1500,
        verbose_name="URL náhledového obrázku",
    )
    thumbnail_url = models.URLField(
        blank=True,
        max_length=1500,
        verbose_name="URL thumbnailu",
    )
    published_at = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        verbose_name="Publikováno",
    )

    is_visible = models.BooleanField(
        default=True,
        db_index=True,
        verbose_name="Viditelný",
        help_text="Když vypneš, post zůstane v databázi, ale nebude se nabízet na webu.",
    )
    raw_payload = models.JSONField(
        blank=True,
        null=True,
        verbose_name="Raw odpověď API",
        help_text="Pro debug a případné budoucí rozšíření.",
    )

    fetched_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Naposledy synchronizováno",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Vytvořeno v databázi",
    )

    class Meta:
        ordering = ["-published_at", "-id"]
        verbose_name = "Post ze sociální sítě"
        verbose_name_plural = "Posty ze sociálních sítí"
        constraints = [
            models.UniqueConstraint(
                fields=["source", "external_post_id"],
                name="unique_social_post_per_source",
            )
        ]

    @property
    def media_count(self):
        prefetched = getattr(self, "_prefetched_objects_cache", {})
        if "media_items" in prefetched:
            return len(prefetched["media_items"])
        return self.media_items.count()

    @property
    def has_gallery(self):
        return self.media_count > 1

    def __str__(self):
        return f"{self.source} | {self.external_post_id}"


class SocialPostMedia(models.Model):
    class MediaType(models.TextChoices):
        IMAGE = "image", "Obrázek"
        VIDEO = "video", "Video"
        OTHER = "other", "Ostatní"

    post = models.ForeignKey(
        SocialPost,
        on_delete=models.CASCADE,
        related_name="media_items",
        verbose_name="Post",
    )
    external_media_id = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name="Externí ID média",
    )
    media_type = models.CharField(
        max_length=20,
        choices=MediaType.choices,
        default=MediaType.IMAGE,
        verbose_name="Typ média",
    )
    media_url = models.URLField(
        max_length=1500,
        blank=True,
        verbose_name="URL média",
    )
    thumbnail_url = models.URLField(
        max_length=1500,
        blank=True,
        verbose_name="URL thumbnailu",
    )
    sort_order = models.PositiveSmallIntegerField(
        default=0,
        verbose_name="Pořadí",
    )

    class Meta:
        ordering = ["sort_order", "id"]
        verbose_name = "Médium postu"
        verbose_name_plural = "Média postů"
        constraints = [
            models.UniqueConstraint(
                fields=["post", "external_media_id"],
                condition=Q(external_media_id__isnull=False),
                name="unique_social_media_per_post",
            )
        ]

    def __str__(self):
        return f"{self.post.external_post_id} | {self.media_type} | {self.sort_order}"