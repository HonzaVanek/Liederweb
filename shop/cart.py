from dataclasses import dataclass
from decimal import Decimal

from .models import ProductVariant


class CartQuantityError(ValueError):
    pass


@dataclass(frozen=True)
class CartItem:
    variant: ProductVariant
    quantity: int

    @property
    def unit_price(self):
        return self.variant.price

    @property
    def subtotal(self):
        return self.variant.price * self.quantity

    @property
    def is_available(self):
        if not self.variant.track_stock:
            return True

        return self.quantity <= self.variant.stock_quantity


class SessionCart:
    SESSION_KEY = "shop_cart"
    MAX_QUANTITY_PER_ITEM = 99

    def __init__(self, request):
        self.request = request
        self.session = request.session
        self._data = self._normalise(
            self.session.get(self.SESSION_KEY, {})
        )
        self._items_cache = None

    def _normalise(self, raw_data):
        normalised = {}

        if not isinstance(raw_data, dict):
            return normalised

        for variant_id, quantity in raw_data.items():
            try:
                variant_id = int(variant_id)
                quantity = int(quantity)
            except (TypeError, ValueError):
                continue

            if variant_id <= 0 or quantity <= 0:
                continue

            normalised[str(variant_id)] = min(
                quantity,
                self.MAX_QUANTITY_PER_ITEM,
            )

        return normalised

    def _save(self):
        self.session[self.SESSION_KEY] = self._data
        self.session.modified = True
        self._items_cache = None

    def _validate_quantity(self, variant, quantity):
        if quantity < 1:
            raise CartQuantityError(
                "Množství musí být alespoň 1."
            )

        if quantity > self.MAX_QUANTITY_PER_ITEM:
            raise CartQuantityError(
                f"Maximální množství jedné varianty je "
                f"{self.MAX_QUANTITY_PER_ITEM} kusů."
            )

        if (
            variant.track_stock
            and quantity > variant.stock_quantity
        ):
            raise CartQuantityError(
                f"Požadované množství není skladem. "
                f"K dispozici je {variant.stock_quantity} ks."
            )

    def get_quantity(self, variant_id):
        return self._data.get(str(variant_id), 0)

    def add(self, variant, quantity=1):
        current_quantity = self.get_quantity(variant.id)
        new_quantity = current_quantity + quantity

        self._validate_quantity(variant, new_quantity)

        self._data[str(variant.id)] = new_quantity
        self._save()

    def set_quantity(self, variant, quantity):
        self._validate_quantity(variant, quantity)

        self._data[str(variant.id)] = quantity
        self._save()

    def remove(self, variant_id):
        variant_id = str(variant_id)

        if variant_id in self._data:
            del self._data[variant_id]
            self._save()

    def clear(self):
        self._data = {}
        self._save()

    @property
    def items(self):
        if self._items_cache is not None:
            return self._items_cache

        variant_ids = [
            int(variant_id)
            for variant_id in self._data
        ]

        variants = (
            ProductVariant.objects
            .filter(
                id__in=variant_ids,
                is_active=True,
            )
            .select_related(
                "product",
                "product__main_image",
            )
        )

        if not self.request.user.is_staff:
            variants = variants.filter(
                product__is_published=True
            )

        variant_map = {
            str(variant.id): variant
            for variant in variants
        }

        cart_items = []
        invalid_variant_ids = []

        for variant_id, quantity in self._data.items():
            variant = variant_map.get(variant_id)

            if variant is None:
                invalid_variant_ids.append(variant_id)
                continue

            cart_items.append(
                CartItem(
                    variant=variant,
                    quantity=quantity,
                )
            )

        if invalid_variant_ids:
            for variant_id in invalid_variant_ids:
                self._data.pop(variant_id, None)

            self._save()

        self._items_cache = cart_items
        return cart_items

    @property
    def total(self):
        return sum(
            (item.subtotal for item in self.items),
            start=Decimal("0.00"),
        )

    @property
    def requires_shipping(self):
        return any(
            item.variant.requires_shipping
            for item in self.items
        )

    @property
    def contains_digital_content(self):
        return any(
            item.variant.is_digital
            for item in self.items
        )

    def __len__(self):
        return sum(self._data.values())

    def __bool__(self):
        return bool(self._data)