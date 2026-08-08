from decimal import Decimal
from functools import partial
from datetime import timedelta
from django.conf import settings

from django.db import transaction
from django.utils import timezone

from shop.models import Order, OrderItem, OrderStatusHistory, ProductVariant, ShippingMethod
from shop.services.newsletter import add_order_contact_to_newsletter
from shop.services.emails import send_order_confirmation_email, send_staff_new_order_email
from shop.services.invoices import issue_invoice_for_order


class CheckoutError(Exception):
    pass


@transaction.atomic
def create_order_from_cart(
    *,
    cart,
    cleaned_data,
    user=None,
    allow_unpublished=False,
):
    cart_items = list(cart.items)

    if not cart_items:
        raise CheckoutError("Košík je prázdný.")

    quantities = {
        item.variant.id: item.quantity
        for item in cart_items
    }

    variants = (
        ProductVariant.objects
        .select_for_update()
        .select_related("product")
        .filter(id__in=quantities.keys())
    )

    variant_map = {
        variant.id: variant
        for variant in variants
    }

    if len(variant_map) != len(quantities):
        raise CheckoutError(
            "Některá položka už není dostupná."
        )

    # --------------------------------------------------
    # Doprava
    # --------------------------------------------------

    shipping_method = None
    shipping_price = Decimal("0.00")

    if cart.requires_shipping:
        submitted_shipping_method = cleaned_data.get(
            "shipping_method"
        )

        if not submitted_shipping_method:
            raise CheckoutError(
                "Vyberte způsob dopravy."
            )

        # Cenu ani dostupnost dopravy nebereme pouze
        # z hodnoty formuláře. Znovu ji ověříme v DB.
        shipping_method = (
            ShippingMethod.objects
            .select_for_update()
            .filter(
                pk=submitted_shipping_method.pk,
                is_active=True,
            )
            .first()
        )

        if shipping_method is None:
            raise CheckoutError(
                "Vybraný způsob dopravy už není dostupný."
            )

        shipping_price = shipping_method.price

    # --------------------------------------------------
    # Základní údaje objednávky
    # --------------------------------------------------

    newsletter_consent = cleaned_data.get(
        "newsletter_consent",
        False,
    )

    now = timezone.now()

    order = Order.objects.create(
        user=user,

        first_name=cleaned_data["first_name"],
        last_name=cleaned_data["last_name"],
        email=cleaned_data["email"].strip().lower(),
        phone=cleaned_data.get("phone", "").strip(),

        address_line1=cleaned_data.get(
            "address_line1",
            "",
        ).strip(),
        address_line2=cleaned_data.get(
            "address_line2",
            "",
        ).strip(),
        city=cleaned_data.get(
            "city",
            "",
        ).strip(),
        postal_code=cleaned_data.get(
            "postal_code",
            "",
        ).strip(),
        country="CZ",

        customer_note=cleaned_data.get(
            "customer_note",
            "",
        ).strip(),

        requires_shipping=cart.requires_shipping,
        contains_digital_content=(
            cart.contains_digital_content
        ),

        # Snapshot dopravy
        shipping_method=shipping_method,
        shipping_method_name=(
            shipping_method.name
            if shipping_method
            else ""
        ),
        shipping_method_code=(
            shipping_method.code
            if shipping_method
            else ""
        ),
        shipping_price=shipping_price,

        newsletter_consent=newsletter_consent,
        newsletter_consent_at=(
            now
            if newsletter_consent
            else None
        ),

        terms_accepted_at=now,

        expires_at=(
            now
            + timedelta(
                days=settings.SHOP_ORDER_EXPIRY_DAYS
            )
        ),
    )

    # --------------------------------------------------
    # Položky objednávky
    # --------------------------------------------------

    subtotal = Decimal("0.00")

    for variant_id, quantity in quantities.items():
        variant = variant_map[variant_id]

        if not variant.is_active:
            raise CheckoutError(
                f'Varianta „{variant.name}“ už není aktivní.'
            )

        if (
            not allow_unpublished
            and not variant.product.is_published
        ):
            raise CheckoutError(
                f'Produkt „{variant.product.name}“ '
                "už není dostupný."
            )

        if variant.is_digital and quantity != 1:
            raise CheckoutError(
                "Digitální obsah lze objednat pouze jednou."
            )

        if (
            variant.track_stock
            and variant.stock_quantity < quantity
        ):
            raise CheckoutError(
                f'Varianta „{variant.name}“ už není '
                "v požadovaném množství skladem. "
                f"K dispozici je "
                f"{variant.stock_quantity} ks."
            )

        line_total = variant.price * quantity
        subtotal += line_total

        OrderItem.objects.create(
            order=order,
            variant=variant,
            product_name=variant.product.name,
            variant_name=variant.name,
            sku=variant.sku,
            fulfilment_type=variant.fulfilment_type,
            unit_price=variant.price,
            quantity=quantity,
            line_total=line_total,
        )

        if variant.track_stock:
            variant.stock_quantity -= quantity

            variant.save(
                update_fields=["stock_quantity"]
            )

    # --------------------------------------------------
    # Celková cena
    # --------------------------------------------------

    order.subtotal = subtotal
    order.total = subtotal + shipping_price

    order.save(
        update_fields=[
            "subtotal",
            "total",
        ]
    )

    order.ensure_number()

    # --------------------------------------------------
    # Historie
    # --------------------------------------------------

    OrderStatusHistory.objects.create(
        order=order,
        action=OrderStatusHistory.Action.CREATED,
        description="Objednávka byla vytvořena.",
        order_status=order.status,
        payment_status=order.payment_status,
        fulfilment_status=order.fulfilment_status,
        performed_by=user,
    )

    # --------------------------------------------------
    # Faktura + newsletter
    # --------------------------------------------------

    issue_invoice_for_order(order)
    add_order_contact_to_newsletter(order)

    # --------------------------------------------------
    # E-maily až po úspěšném commitu transakce
    # --------------------------------------------------

    transaction.on_commit(
        partial(
            send_order_confirmation_email,
            order.pk,
        ),
        robust=True,
    )

    transaction.on_commit(
        partial(
            send_staff_new_order_email,
            order.pk,
        ),
        robust=True,
    )

    return order