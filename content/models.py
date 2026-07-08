from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.urls import reverse
from django.utils import timezone
from urllib.parse import parse_qs, urlparse
from django.core.validators import RegexValidator


class ContentPost(models.Model):
    """
    Redakční příspěvek / blogpost.

    Může být navázaný na koncert, ale nemusí.
    Později z těchto položek půjde skládat stránka Objevujte.
    """

    IMAGE_FIT_COVER = "cover"
    IMAGE_FIT_CONTAIN = "contain"

    IMAGE_FIT_CHOICES = [
        (IMAGE_FIT_COVER, "Vyplnit prostor / oříznout"),
        (IMAGE_FIT_CONTAIN, "Zobrazit celý obrázek"),
    ]

    IMAGE_POSITION_CENTER = "center center"
    IMAGE_POSITION_TOP = "center top"
    IMAGE_POSITION_BOTTOM = "center bottom"
    IMAGE_POSITION_LEFT = "left center"
    IMAGE_POSITION_RIGHT = "right center"

    IMAGE_POSITION_CHOICES = [
        (IMAGE_POSITION_CENTER, "Střed"),
        (IMAGE_POSITION_TOP, "Nahoře"),
        (IMAGE_POSITION_BOTTOM, "Dole"),
        (IMAGE_POSITION_LEFT, "Vlevo uprostřed"),
        (IMAGE_POSITION_RIGHT, "Vpravo uprostřed"),
    ]

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

    cover_image_fit = models.CharField(
            "Zobrazení úvodního obrázku",
            max_length=20,
            choices=IMAGE_FIT_CHOICES,
            default=IMAGE_FIT_COVER,
        )

    cover_image_position = models.CharField(
            "Pozice úvodního obrázku",
            max_length=30,
            choices=IMAGE_POSITION_CHOICES,
            default=IMAGE_POSITION_CENTER,
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

    button_color = models.CharField(
        "Barva tlačítka",
        max_length=7,
        blank=True,
        default="#111111",
        validators=[
            RegexValidator(
                regex=r"^#[0-9A-Fa-f]{6}$",
                message="Barva musí být ve formátu #RRGGBB, například #111111.",
            )
        ],
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

    @property
    def button_foreground_color(self):
        """
        Vrátí černou nebo bílou barvu textu podle světlosti vybrané barvy tlačítka.
        """
        color = (self.button_color or "#111111").strip()

        if not color.startswith("#") or len(color) != 7:
            return "#ffffff"

        try:
            red = int(color[1:3], 16)
            green = int(color[3:5], 16)
            blue = int(color[5:7], 16)
        except ValueError:
            return "#ffffff"

        def channel_luminance(channel):
            channel = channel / 255
            if channel <= 0.03928:
                return channel / 12.92
            return ((channel + 0.055) / 1.055) ** 2.4

        luminance = (
            0.2126 * channel_luminance(red)
            + 0.7152 * channel_luminance(green)
            + 0.0722 * channel_luminance(blue)
        )

        return "#111111" if luminance > 0.55 else "#ffffff"


class ContentBlockImage(models.Model):
    """
    Obrázek vložený do galerijního bloku.

    Samotný soubor je v media_assets.MediaAsset.
    Tady řešíme jen použití obrázku v konkrétním bloku článku.
    """

    IMAGE_FIT_COVER = "cover"
    IMAGE_FIT_CONTAIN = "contain"

    IMAGE_FIT_CHOICES = [
        (IMAGE_FIT_COVER, "Vyplnit prostor / oříznout"),
        (IMAGE_FIT_CONTAIN, "Zobrazit celý obrázek"),
    ]

    IMAGE_POSITION_CENTER = "center center"
    IMAGE_POSITION_TOP = "center top"
    IMAGE_POSITION_BOTTOM = "center bottom"
    IMAGE_POSITION_LEFT = "left center"
    IMAGE_POSITION_RIGHT = "right center"

    IMAGE_POSITION_CHOICES = [
        (IMAGE_POSITION_CENTER, "Střed"),
        (IMAGE_POSITION_TOP, "Nahoře"),
        (IMAGE_POSITION_BOTTOM, "Dole"),
        (IMAGE_POSITION_LEFT, "Vlevo"),
        (IMAGE_POSITION_RIGHT, "Vpravo"),
    ]

    image_fit = models.CharField(
        "Zobrazení obrázku",
        max_length=20,
        choices=IMAGE_FIT_CHOICES,
        default=IMAGE_FIT_COVER,
    )

    image_position = models.CharField(
        "Pozice obrázku",
        max_length=30,
        choices=IMAGE_POSITION_CHOICES,
        default=IMAGE_POSITION_CENTER,
    )

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


class ContentGallery(models.Model):
    """
    Samostatná redakční fotogalerie pro sekci Objevujte.

    Může být volitelně navázaná na koncert.
    Samotné obrázky jsou pořád v media_assets.MediaAsset.
    """

    IMAGE_FIT_COVER = "cover"
    IMAGE_FIT_CONTAIN = "contain"

    IMAGE_FIT_CHOICES = [
        (IMAGE_FIT_COVER, "Vyplnit prostor / oříznout"),
        (IMAGE_FIT_CONTAIN, "Zobrazit celý obrázek"),
    ]

    IMAGE_POSITION_CENTER = "center center"
    IMAGE_POSITION_TOP = "center top"
    IMAGE_POSITION_BOTTOM = "center bottom"
    IMAGE_POSITION_LEFT = "left center"
    IMAGE_POSITION_RIGHT = "right center"

    IMAGE_POSITION_CHOICES = [
        (IMAGE_POSITION_CENTER, "Střed"),
        (IMAGE_POSITION_TOP, "Nahoře"),
        (IMAGE_POSITION_BOTTOM, "Dole"),
        (IMAGE_POSITION_LEFT, "Vlevo"),
        (IMAGE_POSITION_RIGHT, "Vpravo"),
    ]

    title = models.CharField("Název galerie", max_length=255)

    slug = models.SlugField(
        "Slug",
        max_length=255,
        unique=True,
        help_text="Používá se v URL. Např. agnes-tyrrell-fotogalerie.",
    )

    event = models.ForeignKey(
        "events.Event",
        verbose_name="Související koncert",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="content_galleries",
    )

    cover_image = models.ForeignKey(
        "media_assets.MediaAsset",
        verbose_name="Úvodní obrázek galerie",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="content_gallery_covers",
        limit_choices_to={
            "asset_type": "image",
            "is_active": True,
        },
        help_text="Nepovinné. Když zůstane prázdné, můžeme jako náhled použít první obrázek z galerie.",
    )

    cover_image_fit = models.CharField(
        "Zobrazení úvodního obrázku",
        max_length=20,
        choices=IMAGE_FIT_CHOICES,
        default=IMAGE_FIT_COVER,
    )

    cover_image_position = models.CharField(
        "Pozice úvodního obrázku",
        max_length=30,
        choices=IMAGE_POSITION_CHOICES,
        default=IMAGE_POSITION_CENTER,
    )

    description = models.TextField(
        "Popis galerie",
        blank=True,
        help_text="Krátký úvodní text k fotogalerii.",
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
        related_name="created_content_galleries",
    )

    created_at = models.DateTimeField("Vytvořeno", auto_now_add=True)
    updated_at = models.DateTimeField("Upraveno", auto_now=True)

    class Meta:
        verbose_name = "Fotogalerie"
        verbose_name_plural = "Fotogalerie"
        ordering = ["-published_at", "-created_at"]

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse("content:gallery_detail", kwargs={"slug": self.slug})

    def clean(self):
        super().clean()

        if self.cover_image_id and not self.cover_image.is_image:
            raise ValidationError({
                "cover_image": "Úvodní obrázek galerie musí být asset typu obrázek."
            })

    def save(self, *args, **kwargs):
        if self.is_published and self.published_at is None:
            self.published_at = timezone.now()

        super().save(*args, **kwargs)

    @property
    def effective_cover_image(self):
        if self.cover_image:
            return self.cover_image

        first_image = self.images.select_related("image").first()

        if first_image:
            return first_image.image

        return None


class ContentGalleryImage(models.Model):
    """
    Jeden obrázek v redakční fotogalerii.
    """

    IMAGE_FIT_COVER = "cover"
    IMAGE_FIT_CONTAIN = "contain"

    IMAGE_FIT_CHOICES = [
        (IMAGE_FIT_COVER, "Vyplnit prostor / oříznout"),
        (IMAGE_FIT_CONTAIN, "Zobrazit celý obrázek"),
    ]

    IMAGE_POSITION_CENTER = "center center"
    IMAGE_POSITION_TOP = "center top"
    IMAGE_POSITION_BOTTOM = "center bottom"
    IMAGE_POSITION_LEFT = "left center"
    IMAGE_POSITION_RIGHT = "right center"

    IMAGE_POSITION_CHOICES = [
        (IMAGE_POSITION_CENTER, "Střed"),
        (IMAGE_POSITION_TOP, "Nahoře"),
        (IMAGE_POSITION_BOTTOM, "Dole"),
        (IMAGE_POSITION_LEFT, "Vlevo"),
        (IMAGE_POSITION_RIGHT, "Vpravo"),
    ]

    gallery = models.ForeignKey(
        ContentGallery,
        verbose_name="Galerie",
        on_delete=models.CASCADE,
        related_name="images",
    )

    image = models.ForeignKey(
        "media_assets.MediaAsset",
        verbose_name="Obrázek",
        on_delete=models.PROTECT,
        related_name="content_gallery_image_usages",
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
        help_text="Když zůstane prázdné, použije se alt text z media assetu.",
    )

    image_fit = models.CharField(
        "Zobrazení obrázku",
        max_length=20,
        choices=IMAGE_FIT_CHOICES,
        default=IMAGE_FIT_COVER,
    )

    image_position = models.CharField(
        "Pozice obrázku",
        max_length=30,
        choices=IMAGE_POSITION_CHOICES,
        default=IMAGE_POSITION_CENTER,
    )

    position = models.PositiveIntegerField("Pořadí", default=0)

    created_at = models.DateTimeField("Vytvořeno", auto_now_add=True)

    class Meta:
        verbose_name = "Obrázek ve fotogalerii"
        verbose_name_plural = "Obrázky ve fotogaleriích"
        ordering = ["position", "id"]

    def __str__(self):
        return f"{self.gallery.title} – obrázek #{self.position}"

    def clean(self):
        super().clean()

        if self.image_id and not self.image.is_image:
            raise ValidationError({
                "image": "Vybraný asset musí být obrázek."
            })

    @property
    def effective_alt_text(self):
        return self.alt_text or self.image.alt_text or self.image.title or self.gallery.title