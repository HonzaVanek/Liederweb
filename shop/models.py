from django.db import models
import uuid

from django.conf import settings
from django.utils import timezone


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
    



class Order(models.Model):
    class Status(models.TextChoices):
        NEW = "new", "Nová"
        CONFIRMED = "confirmed", "Potvrzená"
        CANCELLED = "cancelled", "Stornovaná"
        COMPLETED = "completed", "Dokončená"

    class PaymentMethod(models.TextChoices):
        BANK_TRANSFER = "bank_transfer", "Bankovní převod"
        STRIPE = "stripe", "Platební karta"

    class PaymentStatus(models.TextChoices):
        AWAITING = "awaiting", "Čeká na platbu"
        PAID = "paid", "Zaplaceno"
        FAILED = "failed", "Platba selhala"
        REFUNDED = "refunded", "Vráceno"
        CANCELLED = "cancelled", "Platba zrušena"

    class FulfilmentStatus(models.TextChoices):
        UNFULFILLED = "unfulfilled", "Nevyřízeno"
        PROCESSING = "processing", "Zpracovává se"
        SHIPPED = "shipped", "Odesláno"
        COMPLETED = "completed", "Vyřízeno"

    number = models.CharField(
        "číslo objednávky",
        max_length=40,
        unique=True,
        null=True,
        blank=True,
        editable=False,
    )

    public_token = models.UUIDField(
        "veřejný token",
        default=uuid.uuid4,
        unique=True,
        editable=False,
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="uživatelský účet",
        on_delete=models.SET_NULL,
        related_name="shop_orders",
        null=True,
        blank=True,
    )

    status = models.CharField(
        "stav objednávky",
        max_length=20,
        choices=Status.choices,
        default=Status.NEW,
    )

    payment_status = models.CharField(
        "stav platby",
        max_length=20,
        choices=PaymentStatus.choices,
        default=PaymentStatus.AWAITING,
    )

    fulfilment_status = models.CharField(
        "stav vyřízení",
        max_length=20,
        choices=FulfilmentStatus.choices,
        default=FulfilmentStatus.UNFULFILLED,
    )

    first_name = models.CharField("jméno", max_length=100)
    last_name = models.CharField("příjmení", max_length=100)

    email = models.EmailField(
        "e-mail",
        db_index=True,
    )

    phone = models.CharField(
        "telefon",
        max_length=40,
        blank=True,
    )

    address_line1 = models.CharField(
        "ulice a číslo",
        max_length=200,
        blank=True,
    )

    address_line2 = models.CharField(
        "doplnění adresy",
        max_length=200,
        blank=True,
    )

    city = models.CharField(
        "město",
        max_length=120,
        blank=True,
    )

    postal_code = models.CharField(
        "PSČ",
        max_length=20,
        blank=True,
    )

    country = models.CharField(
        "země",
        max_length=2,
        default="CZ",
    )

    customer_note = models.TextField(
        "poznámka zákazníka",
        blank=True,
    )

    requires_shipping = models.BooleanField(
        "vyžaduje dopravu",
        default=False,
    )

    contains_digital_content = models.BooleanField(
        "obsahuje digitální obsah",
        default=False,
    )

    subtotal = models.DecimalField(
        "mezisoučet",
        max_digits=12,
        decimal_places=2,
        default=0,
    )

    shipping_price = models.DecimalField(
        "cena dopravy",
        max_digits=12,
        decimal_places=2,
        default=0,
    )

    total = models.DecimalField(
        "celková cena",
        max_digits=12,
        decimal_places=2,
        default=0,
    )

    currency = models.CharField(
        "měna",
        max_length=3,
        default="CZK",
    )

    newsletter_consent = models.BooleanField(
        "souhlas s newsletterem",
        default=False,
    )

    newsletter_consent_at = models.DateTimeField(
        "souhlas s newsletterem udělen",
        null=True,
        blank=True,
    )

    terms_accepted_at = models.DateTimeField(
        "obchodní podmínky přijaty",
        null=True,
        blank=True,
    )

    created_at = models.DateTimeField(
        "vytvořeno",
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        "upraveno",
        auto_now=True,
    )

    payment_method = models.CharField(
        "způsob platby",
        max_length=30,
        choices=PaymentMethod.choices,
        default=PaymentMethod.BANK_TRANSFER,
    )

    confirmation_email_sent_at = models.DateTimeField(
        "potvrzovací e-mail odeslán",
        null=True,
        blank=True,
    )

    confirmation_email_error = models.TextField(
        "chyba potvrzovacího e-mailu",
        blank=True,
    )

    class Meta:
        ordering = ("-created_at",)
        verbose_name = "objednávka"
        verbose_name_plural = "objednávky"

    def __str__(self):
        return self.number or f"Objednávka #{self.pk}"

    @property
    def customer_name(self):
        return f"{self.first_name} {self.last_name}".strip()

    def ensure_number(self):
        if self.number:
            return

        if not self.pk:
            raise ValueError(
                "Číslo lze přidělit až uložené objednávce."
            )

        self.number = (
            f"LS-{self.created_at:%Y}-{self.pk:06d}"
        )

        self.save(update_fields=["number"])

    @property
    def variable_symbol(self):
        if not self.pk or not self.created_at:
            return ""

        return f"{self.created_at:%Y}{self.pk:06d}"


class OrderItem(models.Model):
    order = models.ForeignKey(
        Order,
        verbose_name="objednávka",
        on_delete=models.CASCADE,
        related_name="items",
    )

    variant = models.ForeignKey(
        ProductVariant,
        verbose_name="varianta produktu",
        on_delete=models.SET_NULL,
        related_name="order_items",
        null=True,
        blank=True,
    )

    product_name = models.CharField(
        "název produktu",
        max_length=200,
    )

    variant_name = models.CharField(
        "název varianty",
        max_length=120,
    )

    sku = models.CharField(
        "kód produktu",
        max_length=64,
        blank=True,
    )

    fulfilment_type = models.CharField(
        "způsob vyřízení",
        max_length=20,
        choices=ProductVariant.FulfilmentType.choices,
    )

    unit_price = models.DecimalField(
        "jednotková cena",
        max_digits=12,
        decimal_places=2,
    )

    quantity = models.PositiveIntegerField(
        "množství",
    )

    line_total = models.DecimalField(
        "celkem za položku",
        max_digits=12,
        decimal_places=2,
    )

    class Meta:
        ordering = ("id",)
        verbose_name = "položka objednávky"
        verbose_name_plural = "položky objednávky"

    def __str__(self):
        return (
            f"{self.product_name} – "
            f"{self.variant_name} × {self.quantity}"
        )



class OrderStatusHistory(models.Model):
    class Action(models.TextChoices):
        CREATED = "created", "Vytvoření objednávky"
        STATE_CHANGE = "state_change", "Změna stavů"
        CANCELLED = "cancelled", "Storno objednávky"

    order = models.ForeignKey(
        Order,
        verbose_name="objednávka",
        on_delete=models.CASCADE,
        related_name="status_history",
    )

    action = models.CharField(
        "akce",
        max_length=30,
        choices=Action.choices,
    )

    description = models.CharField(
        "popis",
        max_length=500,
    )

    order_status = models.CharField(
        "stav objednávky",
        max_length=20,
        choices=Order.Status.choices,
    )

    payment_status = models.CharField(
        "stav platby",
        max_length=20,
        choices=Order.PaymentStatus.choices,
    )

    fulfilment_status = models.CharField(
        "stav vyřízení",
        max_length=20,
        choices=Order.FulfilmentStatus.choices,
    )

    note = models.TextField(
        "poznámka",
        blank=True,
    )

    performed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="provedl",
        on_delete=models.SET_NULL,
        related_name="shop_order_status_changes",
        null=True,
        blank=True,
    )

    created_at = models.DateTimeField(
        "vytvořeno",
        auto_now_add=True,
    )

    class Meta:
        ordering = ("-created_at", "-id")
        verbose_name = "historie objednávky"
        verbose_name_plural = "historie objednávek"

    def __str__(self):
        return f"{self.order} – {self.get_action_display()}"


class Invoice(models.Model):
    class Status(models.TextChoices):
        ISSUED = "issued", "Vystavená"
        CANCELLED = "cancelled", "Stornovaná"

    order = models.OneToOneField(
        Order,
        verbose_name="objednávka",
        on_delete=models.PROTECT,
        related_name="invoice",
    )

    number = models.CharField(
        "číslo faktury",
        max_length=40,
        unique=True,
        null=True,
        blank=True,
        editable=False,
    )

    status = models.CharField(
        "stav",
        max_length=20,
        choices=Status.choices,
        default=Status.ISSUED,
    )

    issued_at = models.DateTimeField(
        "datum vystavení",
        default=timezone.now,
    )

    due_date = models.DateField(
        "datum splatnosti",
    )

    cancelled_at = models.DateTimeField(
        "datum storna",
        null=True,
        blank=True,
    )

    # Snapshot prodávajícího
    seller_name = models.CharField(
        "prodávající",
        max_length=200,
    )
    seller_address = models.TextField(
        "adresa prodávajícího",
    )
    seller_company_id = models.CharField(
        "IČO prodávajícího",
        max_length=30,
    )
    seller_vat_id = models.CharField(
        "DIČ prodávajícího",
        max_length=30,
        blank=True,
    )
    seller_is_vat_payer = models.BooleanField(
        "prodávající je plátce DPH",
        default=False,
    )

    # Snapshot zákazníka
    customer_name = models.CharField(
        "zákazník",
        max_length=200,
    )
    customer_email = models.EmailField(
        "e-mail zákazníka",
    )
    customer_address = models.TextField(
        "adresa zákazníka",
        blank=True,
    )

    subtotal = models.DecimalField(
        "mezisoučet",
        max_digits=12,
        decimal_places=2,
    )
    shipping_price = models.DecimalField(
        "doprava",
        max_digits=12,
        decimal_places=2,
    )
    total = models.DecimalField(
        "celkem",
        max_digits=12,
        decimal_places=2,
    )
    currency = models.CharField(
        "měna",
        max_length=3,
        default="CZK",
    )

    payment_method = models.CharField(
        "způsob platby",
        max_length=30,
        default="bank_transfer",
    )
    bank_account = models.CharField(
        "číslo účtu",
        max_length=100,
    )
    iban = models.CharField(
        "IBAN",
        max_length=100,
    )
    variable_symbol = models.CharField(
        "variabilní symbol",
        max_length=20,
    )

    created_at = models.DateTimeField(
        "vytvořeno",
        auto_now_add=True,
    )
    updated_at = models.DateTimeField(
        "upraveno",
        auto_now=True,
    )

    class Meta:
        ordering = ("-issued_at", "-id")
        verbose_name = "faktura"
        verbose_name_plural = "faktury"

    def __str__(self):
        return self.number or f"Faktura objednávky {self.order}"

    def ensure_number(self):
        if self.number:
            return self.number

        year = timezone.localtime(self.issued_at).year
        number = f"FV-{year}-{self.pk:06d}"

        type(self).objects.filter(
            pk=self.pk,
            number__isnull=True,
        ).update(number=number)

        self.number = number
        return number