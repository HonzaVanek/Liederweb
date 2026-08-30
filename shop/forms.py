from django import forms
from django.forms import inlineformset_factory

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
        }

    def clean(self):
        cleaned_data = super().clean()

        fulfilment_type = cleaned_data.get("fulfilment_type")
        track_stock = cleaned_data.get("track_stock")
        stock_quantity = cleaned_data.get("stock_quantity")

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


ProductVariantFormSet = inlineformset_factory(
    parent_model=Product,
    model=ProductVariant,
    form=ProductVariantForm,
    fields=[
        "name",
        "sku",
        "fulfilment_type",
        "price",
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
    class Meta:
        model = AlbumTrack
        fields = [
            "track_number",
            "title",
            "full_audio",
            "preview_start_seconds",
            "purchase_variant",
            "is_active",
        ]

        widgets = {
            "track_number": forms.NumberInput(
                attrs={
                    "min": 1,
                }
            ),
            "title": forms.TextInput(
                attrs={
                    "placeholder": "Např. Die Nacht",
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
            "track_number": (
                "Pořadové číslo skladby na albu."
            ),
            "full_audio": (
                "Nahrajte celou skladbu ve formátu MP3. "
                "30sekundová ukázka se později vytvoří automaticky."
            ),
            "preview_start_seconds": (
                "Sekunda, od které má začínat veřejná "
                "30sekundová ukázka. Například 45 znamená, "
                "že ukázka bude přibližně 0:45–1:15."
            ),
            "purchase_variant": (
                "Digitální varianta používaná při samostatném "
                "nákupu této stopy. Pokud stopu samostatně "
                "prodávat nechcete, nechte prázdné."
            ),
            "is_active": (
                "Určuje, zda se stopa zobrazí ve veřejném tracklistu."
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

        self.fields["purchase_variant"].queryset = (
            ProductVariant.objects
            .filter(
                product=product,
                fulfilment_type=ProductVariant.FulfilmentType.DIGITAL,
            )
            .order_by("sort_order", "name")
        )

        self.fields["purchase_variant"].required = False

        self.fields["purchase_variant"].label_from_instance = (
            lambda variant: (
                f"{variant.name} – "
                f"{variant.price:.2f} Kč"
            )
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

        purchase_variant = cleaned_data.get(
            "purchase_variant"
        )

        if purchase_variant:
            if purchase_variant.product_id != self.product.id:
                self.add_error(
                    "purchase_variant",
                    "Vybraná varianta patří k jinému produktu.",
                )

            if not purchase_variant.is_digital:
                self.add_error(
                    "purchase_variant",
                    "Pro stopu lze použít pouze digitální variantu.",
                )

        return cleaned_data



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