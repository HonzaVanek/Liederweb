from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from media_assets.models import MediaAsset
from .models import Person, Partner, HomeCarouselManualSlide, AgnesSupportIntent, HomeSupportPromo, HomeQuoteSlide

from decimal import Decimal

class VlastniLoginForm(AuthenticationForm):
    username = forms.CharField(label="Uživatelské jméno")
    password = forms.CharField(label="Heslo", widget=forms.PasswordInput)

    def clean(self):
        username = self.cleaned_data.get('username')
        password = self.cleaned_data.get('password')

        if username and password:
            try:
                user = User.objects.get(username=username)
                if not user.check_password(password):
                    raise forms.ValidationError("Zadané heslo není správné.")
            except User.DoesNotExist:
                raise forms.ValidationError("Uživatel s tímto jménem neexistuje.")

        return super().clean()
    

class RegistraceForm(UserCreationForm):
    username = forms.CharField(label="Uživatelské jméno", widget=forms.TextInput(attrs={"placeholder": " "}))
    email = forms.EmailField(required=True, label='Email', widget=forms.EmailInput(attrs={"placeholder": " "}))
    password1 = forms.CharField(label="Heslo", widget=forms.PasswordInput(attrs={"placeholder": " "}))
    password2 = forms.CharField(label="Potvrzení hesla", widget=forms.PasswordInput(attrs={"placeholder": " "}))

    class Meta:
        model = User
        fields = ['username', 'email', 'password1', 'password2']

class PersonForm(forms.ModelForm):
    photo_asset = forms.ModelChoiceField(
        queryset=MediaAsset.objects.filter(
            asset_type=MediaAsset.AssetType.IMAGE,
            is_active=True,
        ).order_by("-uploaded_at"),
        required=False,
        label="Fotografie z mediální knihovny",
        empty_label="— Bez fotografie —",
    )

    class Meta:
        model = Person
        fields = [
            "name",
            "slug",
            "photo_asset",
            "photo_list_position",
            "photo_detail_layout",
            "photo_detail_position",
            "role_short",
            "bio",
            "contact_email",
            "website_url",
            "facebook_url",
            "instagram_url",
            "linkedin_url",
            "x_url",
            "sort_order",
            "is_published",
        ]
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["bio"].help_text = (
            "V případě samotných předložek na konci řádku (například „a“, „i“, „s“ apod.) se nezlomitelná mezera doplní automaticky. Možná ale někdy bude potřeba i jinde - manuálně ji tedy lze vložit jako &nbsp;, například J.&nbsp;Křička."
        )


class NewsletterSignupForm(forms.Form):
    email = forms.EmailField(label="E-mail", max_length=254,)
    name = forms.CharField(label="Jméno", max_length=200, required=False)
    website = forms.CharField(required=False, widget=forms.HiddenInput)

    def clean_email(self):
        return self.cleaned_data["email"].strip().lower()
    
class PartnerForm(forms.ModelForm):
    logo = forms.ModelChoiceField(
        queryset=MediaAsset.objects.filter(
            asset_type=MediaAsset.AssetType.IMAGE,
            is_active=True,
        ).order_by("title", "-uploaded_at"),
        label="Logo",
        help_text="Vyber aktivní obrázek z mediální knihovny.",
        empty_label="Vyber logo partnera",
        widget=forms.Select(attrs={
            "class": "form-control",
        }),
    )

    class Meta:
        model = Partner
        fields = [
            "name",
            "logo",
            "website_url",
            "alt_text",
            "sort_order",
            "is_active",
        ]

        widgets = {
            "name": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Např. Ministerstvo kultury",
            }),
            "website_url": forms.URLInput(attrs={
                "class": "form-control",
                "placeholder": "https://www.example.cz/",
            }),
            "alt_text": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Volitelné, jinak se použije název partnera",
            }),
            "sort_order": forms.NumberInput(attrs={
                "class": "form-control",
                "min": "0",
            }),
            "is_active": forms.CheckboxInput(attrs={
                "class": "form-check-input",
            }),
        }

        labels = {
            "name": "Název partnera",
            "website_url": "Web partnera",
            "alt_text": "Alternativní text",
            "sort_order": "Pořadí",
            "is_active": "Zobrazovat na webu",
        }

        help_texts = {
            "sort_order": "Nižší číslo znamená dřívější zobrazení.",
            "alt_text": "Kvůli přístupnosti. Když zůstane prázdné, použije se název partnera.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["logo"].label_from_instance = self.logo_label_from_instance

    @staticmethod
    def logo_label_from_instance(obj):
        title = obj.title or obj.original_filename or obj.filename or str(obj)
        dimensions = ""

        if obj.image_width and obj.image_height:
            dimensions = f" — {obj.image_width}×{obj.image_height}px"

        return f"{title}{dimensions}"

    def clean_logo(self):
        logo = self.cleaned_data["logo"]

        if logo.asset_type != MediaAsset.AssetType.IMAGE:
            raise forms.ValidationError("Logo musí být obrázek.")

        if not logo.is_active:
            raise forms.ValidationError("Vybrané logo není aktivní.")

        return logo
    


class HomeCarouselManualSlideForm(forms.ModelForm):
    class Meta:
        model = HomeCarouselManualSlide
        fields = [
            "image_asset",
            "layout",
            "eyebrow",
            "title",
            "subtitle",
            "body",
        ]
        widgets = {
            "image_asset": forms.HiddenInput(attrs={
                "data-image-picker-input": "true",
            }),
            "body": forms.Textarea(attrs={"rows": 5}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["image_asset"].queryset = (
            MediaAsset.objects.filter(
                asset_type=MediaAsset.AssetType.IMAGE,
                is_active=True,
            )
            .order_by("-uploaded_at", "-id")
        )

        self.fields["image_asset"].required = False




##### tohle je formulář jen pro platbu přes bankovní údaje, případně QR code spojenou s landing page Tyrrell. Možná ten form pak zas smažem jestli se to nepoužije.

class AgnesSupportIntentForm(forms.ModelForm):
    PRESET_AMOUNTS = {
        "500": Decimal("500.00"),
        "1000": Decimal("1000.00"),
        "2000": Decimal("2000.00"),
        "5000": Decimal("5000.00"),
    }

    amount_choice = forms.ChoiceField(
        choices=[
            ("500", "500 Kč"),
            ("1000", "1 000 Kč"),
            ("2000", "2 000 Kč"),
            ("5000", "5 000 Kč"),
            ("other", "Jiná částka"),
        ],
        initial="1000",
    )

    custom_amount = forms.DecimalField(
        required=False,
        min_value=Decimal("100.00"),
        max_digits=10,
        decimal_places=2,
    )

    class Meta:
        model = AgnesSupportIntent
        fields = [
            "donor_name",
            "donor_email",
            "donor_phone",
            "wants_receipt",
            "note",
        ]

    def clean(self):
        cleaned = super().clean()
        amount_choice = cleaned.get("amount_choice")
        custom_amount = cleaned.get("custom_amount")

        if amount_choice == "other":
            if not custom_amount:
                raise forms.ValidationError("Vyplňte prosím vlastní částku.")
            cleaned["amount"] = custom_amount
        else:
            cleaned["amount"] = self.PRESET_AMOUNTS[amount_choice]

        return cleaned

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.amount = self.cleaned_data["amount"]

        if commit:
            instance.save()

            if not instance.variable_symbol:
                instance.variable_symbol = f"2605{instance.id:06d}"
                instance.save(update_fields=["variable_symbol"])

        return instance
    
##### konec formuláře jen pro platbu přes bankovní údaje, případně QR code spojenou s landing page Tyrrell. Možná ten form pak zas smažem jestli se to nepoužije.




#### home pod carouselem a nad partnery ####

class HomeSupportPromoForm(forms.ModelForm):
    class Meta:
        model = HomeSupportPromo
        fields = [
            "is_enabled",
            "eyebrow",
            "title",
            "body",
            "button_label",
            "button_url",
            "open_in_new_tab",
            "background_media",
            "background_position",
        ]
        widgets = {
            "body": forms.Textarea(attrs={"rows": 5}),
        }


#### home další carousel s těma citacema ####

class HomeQuoteSlideForm(forms.ModelForm):
    class Meta:
        model = HomeQuoteSlide
        fields = [
            "is_active",
            "sort_order",
            "kicker",
            "quote_text",
            "author_name",
            "source_name",
            "source_url",
            "button_label",
            "button_url",
            "open_in_new_tab",
            "background_media",
            "background_position",
        ]

        widgets = {
            "quote_text": forms.Textarea(attrs={
                "rows": 5,
                "placeholder": "Text citace bez uvozovek…",
            }),
            "kicker": forms.TextInput(attrs={
                "placeholder": "Např. Koncerty, Sláva! Naše první písňové CD, Mladý salón",
            }),
            "author_name": forms.TextInput(attrs={
                "placeholder": "Např. Anna Šerých",
            }),
            "source_name": forms.TextInput(attrs={
                "placeholder": "Např. OperaPlus.cz",
            }),
            "source_url": forms.TextInput(attrs={
                "placeholder": "Volitelné: odkaz na recenzi",
            }),
            "button_label": forms.TextInput(attrs={
                "placeholder": "Např. Přejít na koncerty",
            }),
            "button_url": forms.TextInput(attrs={
                "placeholder": "Např. /koncerty/ nebo https://eshop.lieder-society.cz/",
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["background_media"].queryset = (
            MediaAsset.objects
            .filter(
                asset_type=MediaAsset.AssetType.IMAGE,
                is_active=True,
            )
            .order_by("-uploaded_at", "-id")
        )