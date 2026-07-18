from django.db import models


class Product(models.Model):
    name = models.CharField("název", max_length=200)
    slug = models.SlugField("slug", max_length=220, unique=True)

    short_description = models.CharField(
        "krátký popis",
        max_length=300,
        blank=True,
    )
    description = models.TextField("popis", blank=True)

    main_image = models.ForeignKey(
        "media_assets.MediaAsset",
        verbose_name="hlavní obrázek",
        on_delete=models.PROTECT,
        related_name="shop_products_as_main_image",
        null=True,
        blank=True,
    )

    is_published = models.BooleanField("zveřejněno", default=False)
    sort_order = models.PositiveIntegerField("pořadí", default=0)

    created_at = models.DateTimeField("vytvořeno", auto_now_add=True)
    updated_at = models.DateTimeField("upraveno", auto_now=True)

    class Meta:
        ordering = ("sort_order", "name")
        verbose_name = "produkt"
        verbose_name_plural = "produkty"

    def __str__(self):
        return self.name


class ProductVariant(models.Model):
    class FulfilmentType(models.TextChoices):
        PHYSICAL = "physical", "Fyzický produkt"
        DIGITAL = "digital", "Digitální obsah"
        TICKET = "ticket", "Vstupenka"

    product = models.ForeignKey(
        Product,
        verbose_name="produkt",
        on_delete=models.CASCADE,
        related_name="variants",
    )

    name = models.CharField("název varianty", max_length=120)
    sku = models.CharField(
        "kód produktu",
        max_length=64,
        unique=True,
    )

    fulfilment_type = models.CharField(
        "způsob vyřízení",
        max_length=20,
        choices=FulfilmentType.choices,
    )

    price = models.DecimalField(
        "cena",
        max_digits=10,
        decimal_places=2,
    )

    track_stock = models.BooleanField(
        "sledovat sklad",
        default=True,
    )
    stock_quantity = models.PositiveIntegerField(
        "počet kusů skladem",
        default=0,
    )

    is_active = models.BooleanField("aktivní", default=True)
    sort_order = models.PositiveIntegerField("pořadí", default=0)

    created_at = models.DateTimeField("vytvořeno", auto_now_add=True)
    updated_at = models.DateTimeField("upraveno", auto_now=True)

    class Meta:
        ordering = ("sort_order", "name")
        verbose_name = "varianta produktu"
        verbose_name_plural = "varianty produktů"
        constraints = [
            models.UniqueConstraint(
                fields=("product", "name"),
                name="unique_shop_variant_name_per_product",
            ),
        ]

    def __str__(self):
        return f"{self.product.name} – {self.name}"

    @property
    def requires_shipping(self):
        return self.fulfilment_type == self.FulfilmentType.PHYSICAL

    @property
    def is_digital(self):
        return self.fulfilment_type == self.FulfilmentType.DIGITAL


class ProductImage(models.Model):
    product = models.ForeignKey(
        Product,
        verbose_name="produkt",
        on_delete=models.CASCADE,
        related_name="additional_images",
    )
    image = models.ForeignKey(
        "media_assets.MediaAsset",
        verbose_name="obrázek",
        on_delete=models.PROTECT,
        related_name="shop_product_images",
    )

    alt_text = models.CharField(
        "alternativní text",
        max_length=250,
        blank=True,
    )
    sort_order = models.PositiveIntegerField("pořadí", default=0)

    class Meta:
        ordering = ("sort_order", "id")
        verbose_name = "obrázek produktu"
        verbose_name_plural = "obrázky produktu"
        constraints = [
            models.UniqueConstraint(
                fields=("product", "image"),
                name="unique_shop_image_per_product",
            ),
        ]

    def __str__(self):
        return f"{self.product.name} – obrázek"