import mimetypes
from pathlib import Path
from uuid import uuid4

from django.conf import settings
from django.core.files.images import get_image_dimensions
from django.core.validators import FileExtensionValidator
from django.db import models
from django.utils import timezone


ALLOWED_ASSET_EXTENSIONS = [
    "jpg", "jpeg", "png", "webp", "gif", "svg",
    "pdf",
    "mp3", "wav", "ogg", "m4a",
    "mp4", "webm", "mov",
    "xls", "xlsx", "csv",
    "doc", "docx", "txt",
]


def guess_asset_type(filename, mime_type=""):
    ext = Path(filename).suffix.lower().lstrip(".")

    if mime_type.startswith("image/") or ext in {"jpg", "jpeg", "png", "webp", "gif", "svg"}:
        return MediaAsset.AssetType.IMAGE

    if mime_type.startswith("audio/") or ext in {"mp3", "wav", "ogg", "m4a"}:
        return MediaAsset.AssetType.AUDIO

    if mime_type.startswith("video/") or ext in {"mp4", "webm", "mov"}:
        return MediaAsset.AssetType.VIDEO

    if ext in {"xls", "xlsx", "csv"}:
        return MediaAsset.AssetType.SPREADSHEET

    if mime_type == "application/pdf" or ext in {"pdf", "doc", "docx", "txt"}:
        return MediaAsset.AssetType.DOCUMENT

    return MediaAsset.AssetType.OTHER


def media_asset_upload_to(instance, filename):
    ext = Path(filename).suffix.lower()
    asset_type = guess_asset_type(filename)
    now = timezone.now()
    return f"media_assets/{asset_type}/{now:%Y/%m}/{uuid4().hex}{ext}"


class MediaAsset(models.Model):
    class AssetType(models.TextChoices):
        IMAGE = "image", "Obrázek"
        DOCUMENT = "document", "Dokument"
        AUDIO = "audio", "Audio"
        SPREADSHEET = "spreadsheet", "Tabulka"
        VIDEO = "video", "Video"
        OTHER = "other", "Ostatní"

    title = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Název",
        help_text="Nepovinné. Když necháš prázdné, doplní se podle názvu souboru.",
    )
    file = models.FileField(
        upload_to=media_asset_upload_to,
        verbose_name="Soubor",
        validators=[FileExtensionValidator(allowed_extensions=ALLOWED_ASSET_EXTENSIONS)],
    )
    asset_type = models.CharField(
        max_length=20,
        choices=AssetType.choices,
        default=AssetType.OTHER,
        db_index=True,
        verbose_name="Typ assetu",
        help_text="Doplňuje se automaticky podle souboru.",
    )

    alt_text = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Alt text",
        help_text="Používá se hlavně pro obrázky na webu.",
    )
    description = models.TextField(
        blank=True,
        verbose_name="Popis",
    )
    credit = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Autor / kredit",
        help_text="Např. jméno fotografa, autora ilustrace apod.",
    )

    original_filename = models.CharField(
        max_length=255,
        blank=True,
        editable=False,
        verbose_name="Původní název souboru",
    )
    mime_type = models.CharField(
        max_length=120,
        blank=True,
        editable=False,
        verbose_name="MIME typ",
    )
    file_size = models.PositiveBigIntegerField(
        default=0,
        editable=False,
        verbose_name="Velikost souboru (B)",
    )

    image_width = models.PositiveIntegerField(
        blank=True,
        null=True,
        editable=False,
        verbose_name="Šířka obrázku",
    )
    image_height = models.PositiveIntegerField(
        blank=True,
        null=True,
        editable=False,
        verbose_name="Výška obrázku",
    )

    is_active = models.BooleanField(
        default=True,
        db_index=True,
        verbose_name="Aktivní",
        help_text="Umožňuje asset skrýt bez smazání.",
    )
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="uploaded_media_assets",
        verbose_name="Nahrál",
    )
    uploaded_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        verbose_name="Nahráno",
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Naposledy upraveno",
    )

    class Meta:
        ordering = ["-uploaded_at"]
        verbose_name = "Mediální asset"
        verbose_name_plural = "Mediální assety"

    def __str__(self):
        return self.title or self.original_filename or Path(self.file.name).name

    @property
    def filename(self):
        return Path(self.file.name).name if self.file else ""

    @property
    def extension(self):
        return Path(self.file.name).suffix.lower().lstrip(".") if self.file else ""

    @property
    def is_image(self):
        return self.asset_type == self.AssetType.IMAGE

    @property
    def is_document(self):
        return self.asset_type == self.AssetType.DOCUMENT

    @property
    def is_audio(self):
        return self.asset_type == self.AssetType.AUDIO

    @property
    def is_video(self):
        return self.asset_type == self.AssetType.VIDEO

    @property
    def is_spreadsheet(self):
        return self.asset_type == self.AssetType.SPREADSHEET

    def save(self, *args, **kwargs):
        if self.file:
            current_name = getattr(self.file, "name", "") or ""
            old_file_name = None

            if self.pk:
                old_file_name = (
                    type(self).objects
                    .filter(pk=self.pk)
                    .values_list("file", flat=True)
                    .first()
                )

            file_was_replaced = bool(self.pk and old_file_name and current_name != old_file_name)

            if not self.original_filename or file_was_replaced:
                self.original_filename = Path(current_name).name

            guessed_mime_type, _ = mimetypes.guess_type(current_name)
            self.mime_type = guessed_mime_type or ""
            self.asset_type = guess_asset_type(current_name, self.mime_type)

            try:
                self.file_size = self.file.size or 0
            except Exception:
                self.file_size = 0

            if not self.title:
                stem = Path(self.original_filename or current_name).stem
                self.title = stem.replace("_", " ").replace("-", " ").strip()

            if self.asset_type == self.AssetType.IMAGE:
                try:
                    self.image_width, self.image_height = get_image_dimensions(self.file)
                except Exception:
                    self.image_width = None
                    self.image_height = None
            else:
                self.image_width = None
                self.image_height = None

        super().save(*args, **kwargs)