from django.db import models
from django.urls import reverse
from django.utils.text import slugify
from django.core.exceptions import ValidationError


import hashlib

from django.conf import settings
from django.db import models
from django.utils import timezone

from media_assets.models import MediaAsset

from decimal import Decimal

def person_photo_upload_to(instance, filename):
    return f"people/{instance.slug or 'unsorted'}/{filename}"


class Person(models.Model):
    name = models.CharField(max_length=200, verbose_name="Jméno")
    slug = models.SlugField(
        max_length=220,
        unique=True,
        blank=True,
        verbose_name="Slug",
        help_text="Nech prázdné pro automatické vytvoření z jména.",
    )

    # staré pole zatím ponecháme
    photo = models.ImageField(
        upload_to=person_photo_upload_to,
        blank=True,
        null=True,
        verbose_name="Fotografie (staré)",
    )

    # nové pole do centrální knihovny
    photo_asset = models.ForeignKey(
        "media_assets.MediaAsset",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="person_profiles",
        limit_choices_to={"asset_type": "image", "is_active": True},
        verbose_name="Fotografie z mediální knihovny",
    )

    class PhotoListPosition(models.TextChoices):
        TOP = "top", "Nahoře"
        CENTER = "center", "Uprostřed"
        BOTTOM = "bottom", "Dole"

    photo_list_position = models.CharField(
        max_length=10,
        choices=PhotoListPosition.choices,
        default=PhotoListPosition.CENTER,
        verbose_name="Zarovnání náhledu fotky",
        help_text="Použije se ve veřejném výpisu umělců (ne na stránce s detailem umělce). Hodí se u fotek oříznutých moc vysoko nebo nízko.",
    )


    class PhotoDetailLayout(models.TextChoices):
        STRETCH = "stretch", "Podle výšky textu"
        CONTAINED = "contained", "Omezená výška"

    class PhotoDetailPosition(models.TextChoices):
        LEFT = "left", "Vlevo"
        CENTER_LEFT = "center-left", "Mírně vlevo"
        CENTER = "center", "Uprostřed"
        CENTER_RIGHT = "center-right", "Mírně vpravo"
        RIGHT = "right", "Vpravo"

    photo_detail_layout = models.CharField(
        max_length=20,
        choices=PhotoDetailLayout.choices,
        default=PhotoDetailLayout.STRETCH,
        verbose_name="Chování detailové fotky",
        help_text="Výchozí volba zachová na stránce s detailem umělce vysoký výřez fotky podle délky textu - vypadá to fakt dobře imho. Alternativně volbu \"omezená výška\" vyber u dlouhých profilů, kde je hodně textu a kde je tudíž fotka až příliš přiblížená a nevypadá to dobře. Ale dycky bych nejdřív zkusil tu první variantu.",
    )

    photo_detail_position = models.CharField(
        max_length=20,
        choices=PhotoDetailPosition.choices,
        default=PhotoDetailPosition.CENTER,
        verbose_name="Zarovnání detailové fotky",
        help_text="Použije se na stránce s detailem umělce. Pomáhá u fotek, kde je obličej moc vlevo nebo vpravo. Pokud máš v poli výš vybráno \"podle výšky textu \" (což doporučuju), ale obličej není dobře vidět, tak tady můžeš zkusit nastavit zarovnání detailové fotky. Pokud ani to nepomůže, tak pak v tom poli výš holt vyber \"omezená výška\".",
    )

    role_short = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Role / krátký popis",
        help_text="Např. sopranistka, klavírista, dramaturgyně, produkce…",
    )
    bio = models.TextField(blank=True, verbose_name="Text profilu")
    contact_email = models.EmailField(blank=True, verbose_name="Kontaktní e-mail")
    website_url = models.URLField(blank=True, verbose_name="Osobní web")
    facebook_url = models.URLField(blank=True, verbose_name="Facebook")
    instagram_url = models.URLField(blank=True, verbose_name="Instagram")
    linkedin_url = models.URLField(blank=True, verbose_name="LinkedIn")
    x_url = models.URLField(blank=True, verbose_name="X")
    sort_order = models.PositiveIntegerField(default=0, verbose_name="Pořadí", help_text="Nižší číslo = zobrazí se dříve.")
    is_published = models.BooleanField(default=True, verbose_name="Publikováno")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Vytvořeno")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Naposledy upraveno")

    class Meta:
        ordering = ["sort_order", "name"]
        verbose_name = "Osoba"
        verbose_name_plural = "Lidé"

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("core:person_detail", kwargs={"slug": self.slug})

    @property
    def primary_photo(self):
        if self.photo_asset and self.photo_asset.file:
            return self.photo_asset.file
        return self.photo

    @property
    def photo_url(self):
        photo = self.primary_photo
        return photo.url if photo else ""

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.name)
            slug = base_slug
            counter = 2

            while Person.objects.exclude(pk=self.pk).filter(slug=slug).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1

            self.slug = slug

        super().save(*args, **kwargs)


class Partner(models.Model):
    name = models.CharField(max_length=160, verbose_name="Název partnera")
    logo = models.ForeignKey(
        "media_assets.MediaAsset",
        on_delete=models.PROTECT,
        related_name="partner_logos",
        verbose_name="Logo",
        help_text="Vyber logo z mediální knihovny.",
    )
    website_url = models.URLField(blank=True, verbose_name="Web partnera")
    alt_text = models.CharField(max_length=200, blank=True, verbose_name="Alternativní text loga", help_text="Pokud zůstane prázdné, použije se název partnera.")
    sort_order = models.PositiveIntegerField(default=0, db_index=True, verbose_name="Pořadí")
    is_active = models.BooleanField(default=True, verbose_name="Zobrazovat na webu")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Vytvořeno")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Upraveno")

    class Meta:
        ordering = ["sort_order", "name", "id"]
        verbose_name = "Partner"
        verbose_name_plural = "Partneři"

    def __str__(self):
        return self.name

    @property
    def effective_alt_text(self):
        return self.alt_text or self.name
    




# statistiky přístupů na web:

class DailySiteVisitor(models.Model):
    day = models.DateField(db_index=True)
    visitor_hash = models.CharField(max_length=64, db_index=True)

    pageviews = models.PositiveIntegerField(default=0)

    first_seen_at = models.DateTimeField(default=timezone.now)
    last_seen_at = models.DateTimeField(default=timezone.now)

    first_path = models.CharField(max_length=500, blank=True)
    last_path = models.CharField(max_length=500, blank=True)

    class Meta:
        unique_together = ("day", "visitor_hash")
        ordering = ["-day", "visitor_hash"]
        verbose_name = "Denní návštěvník"
        verbose_name_plural = "Denní návštěvníci"

    def __str__(self):
        return f"{self.day} — {self.visitor_hash[:8]} — {self.pageviews} views"
    



    # custom image v carouselu:
     
class HomeCarouselManualSlide(models.Model):
    class Layout(models.TextChoices):
        SIDE = "side", "Obrázek vlevo, text vpravo"
        STACKED = "stacked", "Obrázek nahoře, text dole"

    image_asset = models.ForeignKey(
        MediaAsset,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        limit_choices_to={
            "asset_type": MediaAsset.AssetType.IMAGE,
            "is_active": True,
        },
        verbose_name="Obrázek z mediální knihovny",
    )

    layout = models.CharField(
        "Rozložení slidu",
        max_length=20,
        choices=Layout.choices,
        default=Layout.STACKED,
        help_text="Pro široké fotografie většinou použijte variantu obrázek nahoře, text dole.",
    )

    eyebrow = models.CharField("Horní štítek", max_length=120, blank=True, default="Lieder Society")
    title = models.CharField("Nadpis", max_length=180, blank=True, default="Vybraný vizuál")
    subtitle = models.CharField("Doplňující řádek", max_length=220, blank=True, default="")
    body = models.TextField("Popisek", blank=True, default="")

    updated_at = models.DateTimeField(auto_now=True)

    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    class Meta:
        verbose_name = "ruční blok homepage carouselu"
        verbose_name_plural = "ruční blok homepage carouselu"

    def __str__(self):
        return self.title or "Ruční blok homepage carouselu"

    def clean(self):
        super().clean()

        if self.image_asset:
            if self.image_asset.asset_type != MediaAsset.AssetType.IMAGE:
                raise ValidationError({
                    "image_asset": "Na homepage do carouselu lze vybrat jen obrázek."
                })

            if not self.image_asset.is_active:
                raise ValidationError({
                    "image_asset": "Vybraný obrázek není aktivní."
                })

    @classmethod
    def get_solo(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj
    


##### tohle je model jen pro platbu přes bankovní údaje, případně QR code spojenou s landing page Tyrrell. Možná ten model pak zas smažem jestli se to nepoužije.

class AgnesSupportIntent(models.Model):
    class Status(models.TextChoices):
        CREATED = "created", "Vytvořeno"
        PAID = "paid", "Zaplaceno"
        CANCELLED = "cancelled", "Zrušeno"

    amount = models.DecimalField(
        "částka",
        max_digits=10,
        decimal_places=2,
    )
    donor_name = models.CharField(
        "jméno dárce",
        max_length=255,
        blank=True,
    )
    donor_email = models.EmailField(
        "e-mail dárce",
        blank=True,
    )
    donor_phone = models.CharField(
        "telefon",
        max_length=50,
        blank=True,
    )
    wants_receipt = models.BooleanField(
        "chce potvrzení o daru",
        default=False,
    )
    note = models.TextField(
        "poznámka",
        blank=True,
    )
    variable_symbol = models.CharField(
        "variabilní symbol",
        max_length=20,
        unique=True,
        blank=True,
    )
    status = models.CharField(
        "stav",
        max_length=20,
        choices=Status.choices,
        default=Status.CREATED,
    )
    created_at = models.DateTimeField(
        "vytvořeno",
        auto_now_add=True,
    )
    paid_at = models.DateTimeField(
        "zaplaceno",
        null=True,
        blank=True,
    )

    class Meta:
        verbose_name = "zájem o podporu Agnes Tyrrell"
        verbose_name_plural = "zájmy o podporu Agnes Tyrrell"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.amount} Kč – {self.donor_name or self.donor_email or 'anonym'}"

    def mark_paid(self):
        self.status = self.Status.PAID
        self.paid_at = timezone.now()
        self.save(update_fields=["status", "paid_at"])

#### konec platby přes bankovní údaje, případně QR code spojenou s landing page Tyrrell. Možná ten model pak zas smažem jestli se to nepoužije.