from django import forms
from django.core.exceptions import ValidationError

from rozesilac.models import EmailTemplate, EmailImage, ContactGroup, Contact


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
        fields = ["name", "subject", "preheader", "html_body", "text_body"]
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "Např. Newsletter březen 2026"}),
            "subject": forms.TextInput(attrs={"placeholder": "Předmět emailu"}),
            "preheader": forms.Textarea(attrs={"rows": 1, "placeholder": "Krátký text náhledu emailu v inboxu"}),
            "html_body": forms.Textarea(attrs={"rows": 18, "required": False}),
            "text_body": forms.Textarea(attrs={"rows": 8}),
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