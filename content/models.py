from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.urls import reverse
from django.utils import timezone
from urllib.parse import parse_qs, urlparse


class ContentPost(models.Model):
    """
    Redakční příspěvek / blogpost.

    Může být navázaný na koncert, ale nemusí.
    Později z těchto položek půjde skládat stránka Objevujte.
    """

    title = models.CharField("Název", max_length=255)

    slug = models.SlugField(
        "Slug",
        max_length=255,
        unique=True,
        help_text="Používá se v URL. Např. agnes-tyrrell-pribeh-pisne.",
    )

    event = models.ForeignKey(
        "events.Event",
        verbose_name="Související koncert",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="content_posts",
    )

    cover_image = models.ForeignKey(
        "media_assets.MediaAsset",
        verbose_name="Úvodní obrázek",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="content_post_covers",
        limit_choices_to={
            "asset_type": "image",
            "is_active": True,
        },
        help_text="Nepovinné. Hodí se později pro výpis na stránce Objevujte.",
    )

    author_name = models.CharField(
        "Autor/ka textu",
        max_length=255,
        blank=True,
    )

    perex = models.TextField(
        "Perex",
        blank=True,
        help_text="Krátký úvod nebo anotace článku.",
    )

    keywords = models.TextField(
        "Klíčová slova",
        blank=True,
        help_text=(
            "Volitelně zadejte výrazy pro vyhledávání. "
            "Např. Agnes Tyrrell, Tyrell, Tyrel, Schumannovi."
        ),
    )

    is_published = models.BooleanField("Publikováno", default=False)

    published_at = models.DateTimeField(
        "Datum publikace",
        null=True,
        blank=True,
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Vytvořil/a",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_content_posts",
    )

    created_at = models.DateTimeField("Vytvořeno", auto_now_add=True)
    updated_at = models.DateTimeField("Upraveno", auto_now=True)

    class Meta:
        verbose_name = "Obsahový příspěvek"
        verbose_name_plural = "Obsahové příspěvky"
        ordering = ["-published_at", "-created_at"]

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse("content:post_detail", kwargs={"slug": self.slug})

    def clean(self):
        super().clean()

        if self.cover_image and not self.cover_image.is_image:
            raise ValidationError({
                "cover_image": "Úvodní obrázek musí být asset typu obrázek."
            })

    def save(self, *args, **kwargs):
        if self.is_published and self.published_at is None:
            self.published_at = timezone.now()

        super().save(*args, **kwargs)


class ContentBlock(models.Model):
    """
    Jeden řazený blok uvnitř článku.

    První jednoduchá verze:
    - text
    - galerie / obrázek
    - YouTube video
    - tlačítko
    """

    BLOCK_TEXT = "text"
    BLOCK_GALLERY = "gallery"
    BLOCK_YOUTUBE = "youtube"
    BLOCK_CTA = "cta"

    BLOCK_TYPES = [
        (BLOCK_TEXT, "Text"),
        (BLOCK_GALLERY, "Obrázek / galerie"),
        (BLOCK_YOUTUBE, "YouTube video"),
        (BLOCK_CTA, "Tlačítko"),
    ]

    post = models.ForeignKey(
        ContentPost,
        verbose_name="Příspěvek",
        on_delete=models.CASCADE,
        related_name="blocks",
    )

    block_type = models.CharField(
        "Typ bloku",
        max_length=20,
        choices=BLOCK_TYPES,
    )

    position = models.PositiveIntegerField("Pořadí", default=0)

    text = models.TextField(
        "Text",
        blank=True,
        help_text="Používá se u textového bloku.",
    )

    youtube_url = models.URLField(
        "YouTube URL",
        blank=True,
        help_text="Používá se u YouTube bloku.",
    )

    button_label = models.CharField(
        "Text tlačítka",
        max_length=120,
        blank=True,
        help_text="Používá se u tlačítkového bloku.",
    )

    button_url = models.URLField(
        "URL tlačítka",
        blank=True,
        help_text="Používá se u tlačítkového bloku.",
    )

    created_at = models.DateTimeField("Vytvořeno", auto_now_add=True)
    updated_at = models.DateTimeField("Upraveno", auto_now=True)

    class Meta:
        verbose_name = "Obsahový blok"
        verbose_name_plural = "Obsahové bloky"
        ordering = ["position", "id"]

    def __str__(self):
        return f"{self.post.title} – {self.get_block_type_display()} #{self.position}"
    
    @property
    def youtube_embed_url(self):
        """
        Z běžné YouTube URL udělá embed URL.
        Podporuje:
        - https://www.youtube.com/watch?v=...
        - https://youtu.be/...
        - https://www.youtube.com/embed/...
        - https://www.youtube.com/shorts/...
        """
        url = (self.youtube_url or "").strip()

        if not url:
            return ""

        parsed = urlparse(url)
        host = parsed.netloc.lower().replace("www.", "")
        path = parsed.path.strip("/")

        if "youtube.com" in host and path.startswith("embed/"):
            return url

        video_id = ""

        if "youtu.be" in host:
            video_id = path.split("/")[0]

        elif "youtube.com" in host:
            if path == "watch":
                video_id = parse_qs(parsed.query).get("v", [""])[0]
            elif path.startswith("shorts/"):
                video_id = path.split("/")[1] if len(path.split("/")) > 1 else ""

        if not video_id:
            return ""

        return f"https://www.youtube-nocookie.com/embed/{video_id}"    


class ContentBlockImage(models.Model):
    """
    Obrázek vložený do galerijního bloku.

    Samotný soubor je v media_assets.MediaAsset.
    Tady řešíme jen použití obrázku v konkrétním bloku článku.
    """

    block = models.ForeignKey(
        ContentBlock,
        verbose_name="Blok",
        on_delete=models.CASCADE,
        related_name="images",
    )

    image = models.ForeignKey(
        "media_assets.MediaAsset",
        verbose_name="Obrázek",
        on_delete=models.PROTECT,
        related_name="content_block_image_usages",
        limit_choices_to={
            "asset_type": "image",
            "is_active": True,
        },
    )

    caption = models.CharField(
        "Popisek",
        max_length=255,
        blank=True,
    )

    alt_text = models.CharField(
        "Alternativní text",
        max_length=255,
        blank=True,
        help_text="Když zůstane prázdné, můžeme použít alt text z media assetu.",
    )

    position = models.PositiveIntegerField("Pořadí", default=0)

    created_at = models.DateTimeField("Vytvořeno", auto_now_add=True)

    class Meta:
        verbose_name = "Obrázek v obsahovém bloku"
        verbose_name_plural = "Obrázky v obsahových blocích"
        ordering = ["position", "id"]

    def __str__(self):
        return f"Obrázek #{self.position} – {self.block}"

    def clean(self):
        super().clean()

        if self.block_id and self.block.block_type != ContentBlock.BLOCK_GALLERY:
            raise ValidationError({
                "block": "Obrázky lze přidávat pouze do galerijního bloku."
            })

        if self.image_id and not self.image.is_image:
            raise ValidationError({
                "image": "Vybraný asset musí být obrázek."
            })

    @property
    def effective_alt_text(self):
        return self.alt_text or self.image.alt_text or self.image.title