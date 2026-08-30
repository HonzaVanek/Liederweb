from django import forms
from django.forms import inlineformset_factory, BaseInlineFormSet
from pathlib import Path

from .models import Product, ProductVariant, Order, ShippingMethod, ProductVariantImage, AlbumTrack
from .cart import SessionCart

class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = [
            "name",
            "slug",
            "short_description",
            "description",
            "main_image",
            "is_published",
            "sort_order",
        ]
        widgets = {
            "short_description": forms.Textarea(
                attrs={
                    "rows": 3,
                    "placeholder": "Krátký text pro kartu produktu.",
                }
            ),
            "description": forms.Textarea(
                attrs={
                    "rows": 8,
                    "placeholder": "Podrobný popis produktu.",
                }
            ),
            "sort_order": forms.NumberInput(
                attrs={
                    "min": 0,
                }
            ),
        }
        help_texts = {
            "slug": (
                "Část URL produktu, například slava-vorlova-pisne. "
                "Používej malá písmena, čísla a pomlčky."
            ),
            "main_image": "Hlavní obrázek produktu z Media Assets.",
            "is_published": (
                "Produkt se zobrazí ve veřejném katalogu až po zveřejnění e-shopu."
            ),
        }


class ProductVariantForm(forms.ModelForm):
    class Meta:
        model = ProductVariant
        fields = [
            "name",
            "sku",
            "fulfilment_type",
            "price",
            "is_full_album_download",
            "track_stock",
            "stock_quantity",
            "is_active",
            "sort_order",
        ]
        widgets = {
            "price": forms.NumberInput(
                attrs={
                    "min": 0,
                    "step": "0.01",
                }
            ),
            "stock_quantity": forms.NumberInput(
                attrs={
                    "min": 0,
                }
            ),
            "sort_order": forms.NumberInput(
                attrs={
                    "min": 0,
                }
            ),
        }
        help_texts = {
            "sku": (
                "Jedinečný interní kód varianty, například "
                "ALBUM-VORLOVA-CD nebo PLACKA-BILA."
            ),
            "track_stock": (
                "U digitálních produktů obvykle vypnuto. "
                "U CD, knih a merche zapnuto."
            ),
            "is_full_album_download": (
                "Zaškrtněte u digitální varianty, jejímž "
                "zakoupením zákazník získá všechny MP3 "
                "tohoto alba."
            ),
        }

    def clean(self):
        cleaned_data = super().clean()

        fulfilment_type = cleaned_data.get("fulfilment_type")
        track_stock = cleaned_data.get("track_stock")
        stock_quantity = cleaned_data.get("stock_quantity")
        is_full_album_download = cleaned_data.get("is_full_album_download")

        if (
            is_full_album_download
            and fulfilment_type
            != ProductVariant.FulfilmentType.DIGITAL
        ):
            self.add_error(
                "is_full_album_download",
                (
                    "Celé album ke stažení lze nastavit "
                    "pouze u digitální varianty."
                ),
            )

        if (
            fulfilment_type == ProductVariant.FulfilmentType.DIGITAL
            and track_stock
        ):
            self.add_error(
                "track_stock",
                "U digitální varianty obvykle nemá smysl sledovat sklad.",
            )

        if track_stock and stock_quantity is None:
            self.add_error(
                "stock_quantity",
                "Zadejte počet kusů skladem.",
            )

        return cleaned_data


class ProductVariantBaseFormSet(BaseInlineFormSet):
    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .filter(album_track__isnull=True)
        )


ProductVariantFormSet = inlineformset_factory(
    parent_model=Product,
    model=ProductVariant,
    form=ProductVariantForm,
    formset=ProductVariantBaseFormSet,
    fields=[
        "name",
        "sku",
        "fulfilment_type",
        "price",
        "is_full_album_download",
        "track_stock",
        "stock_quantity",
        "is_active",
        "sort_order",
    ],
    extra=1,
    min_num=1,
    validate_min=True,
    can_delete=True,
)

class MediaAssetPreviewSelect(forms.Select):
    def create_option(
        self,
        name,
        value,
        label,
        selected,
        index,
        subindex=None,
        attrs=None,
    ):
        option = super().create_option(
            name,
            value,
            label,
            selected,
            index,
            subindex=subindex,
            attrs=attrs,
        )

        instance = getattr(value, "instance", None)

        if instance and getattr(instance, "file", None):
            try:
                option["attrs"]["data-preview-url"] = instance.file.url
            except ValueError:
                pass

        return option


class ProductVariantImageForm(forms.ModelForm):
    class Meta:
        model = ProductVariantImage
        fields = [
            "image",
            "alt_text",
            "sort_order",
        ]
        widgets = {
            "image": MediaAssetPreviewSelect(
                attrs={
                    "data-variant-image-select": "",
                }
            ),
            "alt_text": forms.TextInput(
                attrs={
                    "placeholder": "Např. Růžová placka zepředu",
                }
            ),
            "sort_order": forms.NumberInput(
                attrs={
                    "min": 0,
                }
            ),
        }
        help_texts = {
            "image": "Obrázek z Media Assets.",
            "alt_text": (
                "Volitelný popis obrázku pro přístupnost. "
                "Pokud zůstane prázdný, můžeme na webu použít název varianty."
            ),
            "sort_order": (
                "Určuje pořadí obrázků. Nejnižší číslo bude první."
            ),
        }


ProductVariantImageFormSet = inlineformset_factory(
    parent_model=ProductVariant,
    model=ProductVariantImage,
    form=ProductVariantImageForm,
    fields=[
        "image",
        "alt_text",
        "sort_order",
    ],
    extra=0,
    can_delete=True,
)



class AlbumTrackForm(forms.ModelForm):
    single_track_price = forms.DecimalField(
        label="Cena samostatné MP3",
        min_value=0,
        decimal_places=2,
        max_digits=10,
        required=False,
        widget=forms.NumberInput(
            attrs={
                "min": "0",
                "step": "0.01",
            }
        ),
        help_text=(
            "Pokud je cena vyplněna, lze tuto stopu "
            "koupit samostatně. Prázdné = samostatně "
            "se neprodává."
        ),
    )

    class Meta:
        model = AlbumTrack
        fields = [
            "disc_number",
            "track_number",
            "title",
            "full_audio",
            "preview_start_seconds",
            "is_active",
        ]

        widgets = {
            "disc_number": forms.NumberInput(
                attrs={
                    "min": 1,
                }
            ),
            "track_number": forms.NumberInput(
                attrs={
                    "min": 1,
                }
            ),
            "title": forms.TextInput(
                attrs={
                    "placeholder": (
                        "Pokud zůstane prázdné, "
                        "použije se název souboru."
                    ),
                }
            ),
            "full_audio": forms.ClearableFileInput(
                attrs={
                    "accept": ".mp3,audio/mpeg",
                }
            ),
            "preview_start_seconds": forms.NumberInput(
                attrs={
                    "min": 0,
                    "step": 1,
                }
            ),
        }

        help_texts = {
            "disc_number": (
                "Číslo CD / disku. U běžného alba ponechte 1."
            ),
            "track_number": (
                "Pořadové číslo skladby na daném disku."
            ),
            "full_audio": (
                "Nahrajte celou skladbu ve formátu MP3. "
                "Plný soubor zůstane neveřejný; "
                "30sekundová ukázka se vytvoří automaticky."
            ),
            "preview_start_seconds": (
                "Sekunda, od které začne veřejná "
                "30sekundová ukázka. Například 45 "
                "znamená ukázku přibližně 0:45–1:15."
            ),
            "is_active": (
                "Určuje, zda se stopa zobrazí "
                "ve veřejném tracklistu."
            ),
        }

    def __init__(
        self,
        *args,
        product,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)

        self.product = product
        self.fields["title"].required = False

        if (
            self.instance
            and self.instance.pk
            and self.instance.purchase_variant
        ):
            self.fields[
                "single_track_price"
            ].initial = (
                self.instance.purchase_variant.price
            )

    def clean_full_audio(self):
        audio = self.cleaned_data.get("full_audio")

        if not audio:
            return audio

        filename = audio.name.lower()

        if not filename.endswith(".mp3"):
            raise forms.ValidationError(
                "Nahrajte soubor ve formátu MP3."
            )

        return audio

    def clean(self):
        cleaned_data = super().clean()

        title = (
            cleaned_data.get("title") or ""
        ).strip()

        audio = cleaned_data.get("full_audio")

        if not title:
            if audio:
                title = Path(audio.name).stem

            elif (
                self.instance
                and self.instance.pk
                and self.instance.original_filename
            ):
                title = Path(
                    self.instance.original_filename
                ).stem

            if title:
                cleaned_data["title"] = title
            else:
                self.add_error(
                    "title",
                    "Zadejte název nebo nahrajte MP3.",
                )

        return cleaned_data

    def save(self, commit=True):
        track = super().save(commit=False)

        uploaded_audio = self.cleaned_data.get(
            "full_audio"
        )

        if (
            uploaded_audio
            and "full_audio" in self.changed_data
        ):
            track.original_filename = (
                uploaded_audio.name
            )

        if commit:
            track.save()

        return track



class AddToCartForm(forms.Form):
    variant = forms.ModelChoiceField(
        queryset=ProductVariant.objects.none(),
        widget=forms.HiddenInput,
    )
    quantity = forms.IntegerField(
        min_value=1,
        max_value=SessionCart.MAX_QUANTITY_PER_ITEM,
        initial=1,
    )

    def __init__(self, *args, product, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["variant"].queryset = (
            product.variants
            .filter(is_active=True)
            .order_by("sort_order", "name")
        )


class CartQuantityForm(forms.Form):
    quantity = forms.IntegerField(
        min_value=1,
        max_value=SessionCart.MAX_QUANTITY_PER_ITEM,
    )



class CheckoutForm(forms.Form):
    first_name = forms.CharField(
        label="Jméno",
        max_length=100,
    )

    last_name = forms.CharField(
        label="Příjmení",
        max_length=100,
    )

    email = forms.EmailField(
        label="E-mail",
    )

    phone = forms.CharField(
        label="Telefon",
        max_length=40,
        required=False,
    )

    address_line1 = forms.CharField(
        label="Ulice a číslo",
        max_length=200,
    )

    address_line2 = forms.CharField(
        label="Doplnění adresy",
        max_length=200,
        required=False,
    )

    city = forms.CharField(
        label="Město",
        max_length=120,
    )

    postal_code = forms.CharField(
        label="PSČ",
        max_length=20,
    )

    customer_note = forms.CharField(
        label="Poznámka k objednávce",
        required=False,
        widget=forms.Textarea(
            attrs={
                "rows": 4,
                "placeholder": (
                    "Nepovinná poznámka k objednávce."
                ),
            }
        ),
    )

    newsletter_consent = forms.BooleanField(
        label=(
            "Chci dostávat novinky o koncertech, "
            "nahrávkách a aktivitách Lieder Society."
        ),
        required=False,
    )

    terms_accepted = forms.BooleanField(
        label=(
            "Souhlasím s obchodními podmínkami "
            "a potvrzuji správnost objednávky."
        ),
        required=True,
    )

    shipping_method = forms.ModelChoiceField(
        label="Způsob dopravy",
        queryset=ShippingMethod.objects.none(),
        required=False,
        empty_label=None,
        widget=forms.RadioSelect,
    )

    def __init__(
        self,
        *args,
        requires_shipping,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)

        self.requires_shipping = requires_shipping

        if not requires_shipping:
            self.fields.pop("address_line1")
            self.fields.pop("address_line2")
            self.fields.pop("city")
            self.fields.pop("postal_code")

        if requires_shipping:
            self.fields["shipping_method"].required = True
            self.fields["shipping_method"].queryset = (
                ShippingMethod.objects
                .filter(is_active=True)
                .order_by("sort_order", "name")
            )

            self.fields["shipping_method"].label_from_instance = (
                lambda method: (
                    f"{method.name} – "
                    f"{method.price:.2f} Kč"
                )
            )
        else:
            self.fields.pop("shipping_method")

    def clean_postal_code(self):
        postal_code = self.cleaned_data["postal_code"]

        return postal_code.strip().upper()



class StaffOrderStateForm(forms.Form):
    order_status = forms.ChoiceField(
        label="Stav objednávky",
    )

    payment_status = forms.ChoiceField(
        label="Stav platby",
    )

    fulfilment_status = forms.ChoiceField(
        label="Stav vyřízení",
    )

    note = forms.CharField(
        label="Interní poznámka ke změně",
        required=False,
        widget=forms.Textarea(
            attrs={
                "rows": 3,
                "placeholder": (
                    "Nepovinné vysvětlení změny stavů."
                ),
            }
        ),
    )

    def __init__(self, *args, order, **kwargs):
        super().__init__(*args, **kwargs)

        self.order = order

        # Storno musí proběhnout přes samostatnou akci,
        # protože při něm vracíme zboží na sklad.
        self.fields["order_status"].choices = [
            choice
            for choice in Order.Status.choices
            if choice[0] != Order.Status.CANCELLED
        ]

        # Refundaci zatím neumožníme, dokud nemáme
        # implementované skutečné vracení plateb.
        self.fields["payment_status"].choices = [
            choice
            for choice in Order.PaymentStatus.choices
            if choice[0]
            not in {
                Order.PaymentStatus.REFUNDED,
                Order.PaymentStatus.CANCELLED,
            }
        ]

        self.fields["fulfilment_status"].choices = (
            Order.FulfilmentStatus.choices
        )

        self.initial.update(
            {
                "order_status": order.status,
                "payment_status": order.payment_status,
                "fulfilment_status": order.fulfilment_status,
            }
        )

    def clean(self):
        cleaned_data = super().clean()

        order_status = cleaned_data.get("order_status")
        payment_status = cleaned_data.get("payment_status")
        fulfilment_status = cleaned_data.get(
            "fulfilment_status"
        )

        if not all(
            [
                order_status,
                payment_status,
                fulfilment_status,
            ]
        ):
            return cleaned_data

        if self.order.status == Order.Status.CANCELLED:
            raise forms.ValidationError(
                "Stornovanou objednávku už nelze upravovat."
            )

        if (
            fulfilment_status
            != Order.FulfilmentStatus.UNFULFILLED
            and payment_status != Order.PaymentStatus.PAID
        ):
            self.add_error(
                "fulfilment_status",
                "Nezaplacenou objednávku nelze začít vyřizovat.",
            )

        if (
            fulfilment_status
            == Order.FulfilmentStatus.SHIPPED
            and not self.order.requires_shipping
        ):
            self.add_error(
                "fulfilment_status",
                "Objednávka bez fyzické dopravy nemůže být odeslána.",
            )

        if (
            order_status == Order.Status.COMPLETED
            and fulfilment_status
            != Order.FulfilmentStatus.COMPLETED
        ):
            self.add_error(
                "order_status",
                "Dokončená objednávka musí být také označená jako vyřízená.",
            )

        return cleaned_data


class CancelOrderForm(forms.Form):
    reason = forms.CharField(
        label="Důvod storna",
        max_length=500,
        widget=forms.Textarea(
            attrs={
                "rows": 3,
                "placeholder": (
                    "Například: zákazník požádal o zrušení."
                ),
            }
        ),
    )



class ShippingMethodForm(forms.ModelForm):
    class Meta:
        model = ShippingMethod
        fields = (
            "name",
            "code",
            "method_type",
            "price",
            "is_active",
            "sort_order",
        )
        widgets = {
            "price": forms.NumberInput(
                attrs={
                    "step": "0.01",
                    "min": "0",
                }
            ),
            "sort_order": forms.NumberInput(
                attrs={"min": "0"}
            ),
        }