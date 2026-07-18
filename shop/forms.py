from django import forms
from django.forms import inlineformset_factory

from .models import Product, ProductVariant
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