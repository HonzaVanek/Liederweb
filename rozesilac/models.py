from django.db import models
from django.core.validators import FileExtensionValidator
from django.core.exceptions import ValidationError
from django.db.models.deletion import ProtectedError
from django.db.models.signals import pre_delete
from django.conf import settings
from django.dispatch import receiver
import uuid
import secrets

# Create your models here.


WEB_CONTACT_GROUP_CODE = "web_newsletter"
WEB_CONTACT_GROUP_NAME = "Kontakty z webu"

DEFAULT_FALLBACK_SALUTATION = "Vážení přátelé písně"

class ContactGroup(models.Model):
    name = models.CharField(max_length=100, unique=True, verbose_name="Název skupiny")
    created_at = models.DateTimeField(auto_now_add=True)
    system_code = models.SlugField(
        max_length=80,
        blank=True,
        null=True,
        unique=True,
        verbose_name="Systémový kód",
        help_text="Interní kód pro systémové skupiny. Běžně nevyplňovat.",
    )
    is_protected = models.BooleanField(default=False, verbose_name="Chráněná skupina", help_text="Chráněnou skupinu nelze smazat.",)

    class Meta:
        ordering = ["name"]
        verbose_name = "Skupina kontaktů"
        verbose_name_plural = "Skupiny kontaktů"

    def __str__(self):
        return self.name

@receiver(pre_delete, sender=ContactGroup)
def prevent_protected_contact_group_delete(sender, instance, **kwargs):
    if instance.is_protected:
        raise ProtectedError(
            "Tuto systémovou skupinu nelze smazat.",
            [instance],
        )    

class Contact(models.Model):
    email = models.EmailField(unique=True)
    name = models.CharField(max_length=200, blank=True)
    is_active = models.BooleanField(default=True)
    salutation = models.CharField(max_length=100, blank=True, verbose_name="Oslovení", help_text="Oslovení (např. 'Vážený pane Nováku')")
    groups = models.ManyToManyField(
        ContactGroup,
        blank=True,
        related_name="contacts",
        verbose_name="Skupiny",
    )
    unsubscribe_token = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)

    def __str__(self) -> str:
        return f"{self.name} <{self.email}>" if self.name else self.email
    
    class Meta:
        ordering = ["email"]
        verbose_name = "Kontakt"
        verbose_name_plural = "Kontakty"
    

class EmailTemplate(models.Model):
    name = models.CharField(max_length=200)
    subject = models.CharField(max_length=250)
    html_body = models.TextField()
    text_body = models.TextField(blank=True, help_text="Volitelné: plain-text fallback.")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    preheader = models.CharField(
        max_length=200,
        blank=True,
        help_text="Krátký text zobrazovaný jako náhled emailu v inboxu",
    )
    fallback_salutation = models.CharField(
        max_length=120,
        default=DEFAULT_FALLBACK_SALUTATION,
        verbose_name="Oslovení pro kontakty bez oslovení",
        help_text="Použije se jako {{ osloveni }}, pokud kontakt nemá vlastní oslovení.",
    )

    def __str__(self) -> str:
        return self.name
    

class EmailCampaign(models.Model):
    STATUS_CHOICES = [("draft", "Rozpracováno"), ("scheduled", "Naplánováno"), ("sending", "Odesílá se"), ("sent", "Odesláno"), ("failed", "Selhalo"), ("cancelled", "Zrušeno"),]
    
    template = models.ForeignKey(EmailTemplate, on_delete=models.PROTECT)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="email_campaigns")
    created_at = models.DateTimeField(auto_now_add=True)
    event = models.ForeignKey(
                "events.Event",
                on_delete=models.SET_NULL,
                null=True,
                blank=True,
                related_name="campaigns",
                verbose_name="Koncert",
            )

    # co se poslalo (snapshot – ať to nezmění pozdější editace šablony)
    subject = models.CharField(max_length=250)
    preheader = models.CharField(max_length=200, blank=True)
    fallback_salutation = models.CharField(max_length=120, default=DEFAULT_FALLBACK_SALUTATION, verbose_name="Oslovení pro kontakty bez oslovení")
    html_body = models.TextField()
    text_body = models.TextField(blank=True)
    from_email = models.EmailField(null=True, blank=True, verbose_name="Odesílatel")

    is_test = models.BooleanField(default=False)
    note = models.CharField(max_length=250, blank=True)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="draft", db_index=True, verbose_name="Stav",)
    scheduled_at = models.DateTimeField(null=True, blank=True, db_index=True, verbose_name="Naplánováno na",)
    started_at = models.DateTimeField(null=True, blank=True, verbose_name="Odesílání spuštěno",)
    finished_at = models.DateTimeField(null=True, blank=True, verbose_name="Odesílání dokončeno",)
    
    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Emailová kampaň"
        verbose_name_plural = "Emailové kampaně"

    def __str__(self) -> str:
        return f"{'TEST ' if self.is_test else ''}{self.subject} ({self.created_at:%Y-%m-%d %H:%M})"
    

def generate_tracking_token():
    return secrets.token_urlsafe(32)

class EmailDelivery(models.Model):
    STATUS_CHOICES = [("queued", "Queued"), ("sent", "Sent"), ("failed", "Failed"),]
    campaign = models.ForeignKey(EmailCampaign, on_delete=models.CASCADE, related_name="deliveries")
    to_email = models.EmailField()
    to_name = models.CharField(max_length=200, blank=True)
    contact = models.ForeignKey(
        Contact,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="email_deliveries",
        verbose_name="Kontakt",
    )

    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="queued")
    error = models.TextField(blank=True)

    sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    tracking_token = models.CharField(max_length=64, unique=True, db_index=True, default=generate_tracking_token, editable=False)
    clicked_at = models.DateTimeField(null=True, blank=True)
    click_count = models.PositiveIntegerField(default=0)
    unique_click_count = models.PositiveIntegerField(default=0)

    class Meta:
        indexes = [models.Index(fields=["campaign", "status"]), models.Index(fields=["to_email"]),]  

    def __str__(self) -> str:
        return f"{self.to_email} - {self.status}"
    


class EmailCampaignTrackedLink(models.Model):
    campaign = models.ForeignKey("EmailCampaign", on_delete=models.CASCADE, related_name="tracked_links",)
    url = models.TextField()

    class Meta:
        unique_together = ("campaign", "url")
        ordering = ["id"]

    def __str__(self):
        return self.url
    

class EmailClickEvent(models.Model):
    delivery = models.ForeignKey(EmailDelivery, on_delete=models.CASCADE, related_name="click_events",)
    original_url = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    user_agent = models.TextField(blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    is_suspected_bot = models.BooleanField(default=False)
    is_duplicate = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.delivery.to_email} -> {self.original_url}"
    

# model pro ukládání obrázků, které můžeme vkládat do rozesílače emailů (abychom nemuseli používat externí hosting a riskovat, že se nám obrázky ztratí):
def validate_email_image_size(image):
    max_size_mb = 2
    if image.size > max_size_mb * 1024 * 1024:
        raise ValidationError(f"Maximální povolená velikost obrázku je pouze {max_size_mb} MB.")

class EmailImage(models.Model):
    title = models.CharField(max_length=255, blank=True, verbose_name="Název")
    image = models.ImageField(
        upload_to="email_images/",
        verbose_name="Obrázek",
        validators=[
            FileExtensionValidator(allowed_extensions=["jpg", "jpeg", "png", "webp", "gif"]),
            validate_email_image_size,
        ],
    )
    file_size = models.PositiveIntegerField(default=0, verbose_name="Velikost souboru (B)")
    uploaded_at = models.DateTimeField(auto_now_add=True, verbose_name="Nahráno")
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Nahrál",
    )

    class Meta:
        ordering = ["-uploaded_at"]
        verbose_name = "Obrázek do emailu"
        verbose_name_plural = "Obrázky do emailu"

    def __str__(self):
        return self.title or self.image.name