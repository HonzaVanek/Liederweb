from django import forms
from django.core.exceptions import ValidationError
import re
from bs4 import BeautifulSoup
from django.utils import timezone
from rozesilac.models import EmailTemplate, EmailImage, ContactGroup, Contact
from events.models import Event
from django.conf import settings
from django.db.models import Sum

from pathlib import Path
from media_assets.models import MediaAsset
from .scheduling import (find_scheduled_campaign_conflict, get_min_allowed_scheduled_at, get_scheduled_campaign_min_gap_minutes)


#přepis html emailu do plaintextu:
def html_to_plain_text(html: str) -> str:
    if not html:
        return ""

    soup = BeautifulSoup(html, "html.parser")

    # zachovat základní zalomení
    for br in soup.find_all("br"):
        br.replace_with("\n")

    for p in soup.find_all("p"):
        p.append("\n\n")

    for li in soup.find_all("li"):
        li.insert_before("• ")
        li.append("\n")

    text = soup.get_text()

    # úklid whitespace
    text = text.replace("\xa0", " ")
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)

    return text.strip()

class EmailTemplateForm(forms.ModelForm):
    class Meta:
        model = EmailTemplate
        fields = ["name", "subject", "preheader", "fallback_salutation", "html_body", "text_body"]
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "Např. Newsletter březen 2026"}),
            "subject": forms.TextInput(attrs={"placeholder": "Předmět emailu"}),
            "preheader": forms.Textarea(attrs={"rows": 1, "placeholder": "Krátký text náhledu emailu v inboxu"}),
            "html_body": forms.Textarea(attrs={"rows": 18, "required": False}),
            "text_body": forms.Textarea(attrs={"rows": 8}),
            "fallback_salutation": forms.TextInput(attrs={"placeholder": "Např. Vážení přátelé písně, Dobrý den, Milí přátelé, apod."}),
        }

    def clean_html_body(self):
        html = self.cleaned_data.get("html_body", "").strip()

        # TinyMCE někdy pošle "prázdné" HTML typu <p>&nbsp;</p>
        normalized = (
            html.replace("&nbsp;", "")
                .replace("<p></p>", "")
                .replace("<p><br></p>", "")
                .replace("<p> </p>", "")
                .strip()
        )

        if not normalized:
            raise forms.ValidationError("HTML tělo emailu nesmí být prázdné.")

        return html
    
    def clean(self):
        cleaned_data = super().clean()

        html_body = cleaned_data.get("html_body", "")
        text_body = (cleaned_data.get("text_body") or "").strip()

        if html_body and not text_body:
            cleaned_data["text_body"] = html_to_plain_text(html_body)

        return cleaned_data
    
    def clean_fallback_salutation(self):
        value = (self.cleaned_data.get("fallback_salutation") or "").strip()

        if not value:
            raise forms.ValidationError("Vyplň prosím fallback oslovení.")

        return value
    

# pro nahrávání obrázků na server v rozesílači emailů (aby šablony mohly používat obrázky, které jsou na našem serveru a ne někde jinde na internetu):
class EmailImageUploadForm(forms.ModelForm):
    class Meta:
        model = EmailImage
        fields = ["title", "image"]
        widgets = {
            "title": forms.TextInput(attrs={"placeholder": "Volitelný název obrázku"}),
        }

    def clean(self):
        cleaned_data = super().clean()
        image = cleaned_data.get("image")

        if image:
            current_total = EmailImage.objects.aggregate(total=Sum("file_size"))["total"] or 0

            max_total = 100 * 1024 * 1024  # 100 MB

            if current_total + image.size > max_total:
                raise ValidationError(
                    "Nelze nahrát další obrázek. Úložiště pro emailové obrázky překročilo limit 100 MB. "
                    "Nejdříve je potřeba z galerie smazat alespoň pár nepotřebných obrázků."
                )

        return cleaned_data
    

# přechod na MediaAsset pro správu obrázků v rozesílači:
EMAIL_IMAGE_ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "webp", "gif"}
EMAIL_IMAGE_MAX_SIZE = 3 * 1024 * 1024
EMAIL_IMAGE_TOTAL_LIMIT = 500 * 1024 * 1024

class NewsletterImageUploadForm(forms.Form):
    title = forms.CharField(
        required=False,
        max_length=255,
        widget=forms.TextInput(attrs={"placeholder": "Volitelný název obrázku"}),
        label="Název",
    )
    image = forms.ImageField(label="Obrázek")

    def clean_image(self):
        image = self.cleaned_data.get("image")
        if not image:
            return image

        ext = Path(image.name).suffix.lower().lstrip(".")
        if ext not in EMAIL_IMAGE_ALLOWED_EXTENSIONS:
            raise ValidationError(
                "Povolené formáty jsou pouze JPG, JPEG, PNG, WEBP a GIF."
            )

        if image.size > EMAIL_IMAGE_MAX_SIZE:
            raise ValidationError(
                "Maximální povolená velikost obrázku je pouze 3 MB."
            )

        return image

    def clean(self):
        cleaned_data = super().clean()
        image = cleaned_data.get("image")

        if image:
            current_total = (
                MediaAsset.objects.filter(asset_type=MediaAsset.AssetType.IMAGE)
                .aggregate(total=Sum("file_size"))["total"]
                or 0
            )

            if current_total + image.size > EMAIL_IMAGE_TOTAL_LIMIT:
                raise ValidationError(
                    "Nelze nahrát další obrázek. Úložiště pro obrázky překročilo limit 500 MB. "
                    "Nejdříve je potřeba z galerie smazat alespoň pár nepotřebných obrázků."
                )

        return cleaned_data

    def save(self, uploaded_by=None):
        image = self.cleaned_data["image"]
        title = (self.cleaned_data.get("title") or "").strip()

        asset = MediaAsset(
            title=title,
            file=image,
            alt_text=title,
            uploaded_by=uploaded_by,
            is_active=True,
        )
        asset.save()
        return asset
    
class ContactGroupForm(forms.ModelForm):
    class Meta:
        model = ContactGroup
        fields = ["name"]
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "Např. Lidi pro newsletter, Testovací skupina, Partneři, VIP", "class": "full-width-input"}),
        }

class ContactForm(forms.ModelForm):
    class Meta:
        model = Contact
        fields = ["name", "salutation","email", "is_active", "groups"]
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "Jméno (volitelné)"}),
            "email": forms.EmailInput(attrs={"placeholder": "email@domena.cz"}),
            "salutation": forms.TextInput(attrs={"placeholder": "Např. Vážený pane Nováku"}),
            "is_active": forms.CheckboxInput,
            "groups": forms.CheckboxSelectMultiple,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["groups"].required = True
        self.fields["groups"].error_messages = {"required": "Kontakt musí být přiřazen do jedné nebo více skupin."}

    def clean_groups(self):
        groups = self.cleaned_data.get("groups")
        if not groups or groups.count() == 0:
            raise forms.ValidationError("Kontakt musí být přiřazen alespoň do jedné skupiny.")
        return groups


class ContactImportForm(forms.Form):
    file = forms.FileField(help_text="XLSX se sloupci: jméno, email")
    group = forms.ModelChoiceField(
        queryset=ContactGroup.objects.all().order_by("name"),
        required=True,
        label="Přiřadit do skupiny",
        empty_label="-- bez skupiny --",
        error_messages={"required": "Musíš vybrat skupinu, do které se importované kontakty přiřadí."},
    )

    def clean_file(self):
        f = self.cleaned_data["file"]
        name = (f.name or "").lower()
        if not name.endswith(".xlsx"):
            raise ValidationError("Tohle nevypadá jako xlsx soubor. Nahraj prosím soubor s příponou .xlsx, který má dva sloupce se záhlavím jméno a email")
        return f
    



# odesílání kampaní:
class SendCampaignForm(forms.Form):
    SEND_MODE_CHOICES = [
        ("test", "Testovací email"),
        ("live", "Ostré rozeslání"),
    ]

    DELIVERY_MODE_CHOICES = [
        ("now", "Odeslat hned"),
        ("scheduled", "Naplánovat na později"),
    ]

    template = forms.ModelChoiceField(
        queryset=EmailTemplate.objects.all().order_by("name"),
        label="Šablona",
        empty_label="-- vyber šablonu --",
    )

    event = forms.ModelChoiceField(
        queryset=Event.objects.all().order_by("-starts_at"),
        required=False,
        label="Koncert",
        help_text="Volitelné: propojí kampaň s konkrétním koncertem (umožní přehled, filtrování, VIP vstupenky apod.). Pokud to není kampaň k nějakému konkrétnímu koncertu, nevyplňuj.",
        empty_label="-- bez navázání na koncert --",
    )

    from_email = forms.ChoiceField(
        label="Odesílatel",
        choices=[
            (email, f"{name} <{email}>")
            for email, name in settings.ALLOWED_FROM_EMAILS
        ]
    )

    send_mode = forms.ChoiceField(
        choices=SEND_MODE_CHOICES,
        widget=forms.RadioSelect,
        initial="test",
        label="Režim odeslání",
    )

    delivery_mode = forms.ChoiceField(
        choices=DELIVERY_MODE_CHOICES,
        widget=forms.RadioSelect,
        initial="now",
        label="Kdy odeslat",
    )

    scheduled_at = forms.DateTimeField(
        required=False,
        label="Naplánovat na",
        input_formats=["%Y-%m-%dT%H:%M"],
        widget=forms.DateTimeInput(
            attrs={
                "type": "datetime-local",
            }
        ),
    )

    test_email = forms.EmailField(
        required=False,
        label="Testovací email",
        widget=forms.EmailInput(attrs={"placeholder": "test@example.com"}),
    )

    groups = forms.ModelMultipleChoiceField(
        queryset=ContactGroup.objects.all().order_by("name"),
        required=False,
        label="Skupiny kontaktů",
        widget=forms.CheckboxSelectMultiple,
    )

    contacts = forms.ModelMultipleChoiceField(
        queryset=Contact.objects.filter(is_active=True).prefetch_related("groups").order_by("email"),
        required=False,
        label="Kontakty",
        widget=forms.CheckboxSelectMultiple,
    )

    note = forms.CharField(
        required=False,
        label="Poznámka",
        widget=forms.Textarea(attrs={"rows": 3, "placeholder": "Volitelná interní poznámka ke kampani"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # popisek skupiny s počtem aktivních kontaktů
        self.fields["groups"].label_from_instance = (
            lambda obj: f"{obj.name} ({obj.contacts.filter(is_active=True).count()})"
        )

        min_scheduled_at = timezone.localtime(get_min_allowed_scheduled_at()).strftime("%Y-%m-%dT%H:%M")

        self.fields["scheduled_at"].widget.attrs.update({
            "min": min_scheduled_at,
            "step": "60",
        })

    def clean(self):
        cleaned_data = super().clean()

        send_mode = cleaned_data.get("send_mode")
        delivery_mode = cleaned_data.get("delivery_mode")
        scheduled_at = cleaned_data.get("scheduled_at")
        test_email = cleaned_data.get("test_email")
        groups = cleaned_data.get("groups")
        contacts = cleaned_data.get("contacts")

        if send_mode == "test":
            if not test_email:
                self.add_error(
                    "test_email",
                    "U testovacího režimu musíš vyplnit testovací email.",
                )

        elif send_mode == "live":
            if not groups or groups.count() == 0:
                self.add_error(
                    "groups",
                    "Pro ostré rozeslání musíš vybrat aspoň jednu skupinu.",
                )

            if not contacts or contacts.count() == 0:
                self.add_error(
                    "contacts",
                    "Pro ostré rozeslání musíš nechat vybraný aspoň jeden kontakt.",
                )

        if delivery_mode == "scheduled":
            if send_mode != "live":
                self.add_error(
                    "delivery_mode",
                    "Naplánovat lze jen ostré rozeslání, ne testovací email.",
                )

            if not scheduled_at:
                self.add_error(
                    "scheduled_at",
                    "Pro naplánované odeslání musíš vyplnit datum a čas.",
                )

            else:
                if timezone.is_naive(scheduled_at):
                    scheduled_at = timezone.make_aware(
                        scheduled_at,
                        timezone.get_current_timezone(),
                    )
                    cleaned_data["scheduled_at"] = scheduled_at

                min_gap_minutes = get_scheduled_campaign_min_gap_minutes()
                min_allowed_scheduled_at = get_min_allowed_scheduled_at()

                if scheduled_at < min_allowed_scheduled_at:
                    self.add_error(
                        "scheduled_at",
                        f"Kampaň lze naplánovat nejdřív za {min_gap_minutes} minut.",
                    )

                else:
                    conflict = find_scheduled_campaign_conflict(scheduled_at)

                    if conflict:
                        conflict_time = timezone.localtime(
                            conflict.scheduled_at
                        ).strftime("%d.%m.%Y %H:%M")

                        self.add_error(
                            "scheduled_at",
                            (
                                f"V okolí tohoto času už je naplánovaná kampaň "
                                f"„{conflict.subject}“ na {conflict_time}. "
                                f"Mezi naplánovanými kampaněmi musí být aspoň "
                                f"{min_gap_minutes} minut rozdíl."
                            ),
                        )

        return cleaned_data