from django.db import transaction
from django.utils import timezone

from shop.models import Order, OrderStatusHistory, ProductVariant, Invoice


class OrderManagementError(Exception):
    pass


def _choice_label(choices, value):
    return dict(choices).get(value, value)


def _validate_state_combination(
    *,
    order,
    order_status,
    payment_status,
    fulfilment_status,
):
    if order.status == Order.Status.CANCELLED:
        raise OrderManagementError(
            "Stornovanou objednávku už nelze upravovat."
        )

    if (
        fulfilment_status
        != Order.FulfilmentStatus.UNFULFILLED
        and payment_status != Order.PaymentStatus.PAID
    ):
        raise OrderManagementError(
            "Nezaplacenou objednávku nelze začít vyřizovat."
        )

    if (
        fulfilment_status
        == Order.FulfilmentStatus.SHIPPED
        and not order.requires_shipping
    ):
        raise OrderManagementError(
            "Objednávka bez fyzické dopravy nemůže být odeslána."
        )

    if (
        order_status == Order.Status.COMPLETED
        and fulfilment_status
        != Order.FulfilmentStatus.COMPLETED
    ):
        raise OrderManagementError(
            "Dokončená objednávka musí být také vyřízená."
        )


@transaction.atomic
def update_order_states(
    *,
    order_id,
    order_status,
    payment_status,
    fulfilment_status,
    note="",
    performed_by,
):
    order = (
        Order.objects
        .select_for_update()
        .get(pk=order_id)
    )

    _validate_state_combination(
        order=order,
        order_status=order_status,
        payment_status=payment_status,
        fulfilment_status=fulfilment_status,
    )

    changes = []

    if order.status != order_status:
        old_label = _choice_label(
            Order.Status.choices,
            order.status,
        )
        new_label = _choice_label(
            Order.Status.choices,
            order_status,
        )

        changes.append(
            f"Stav objednávky: {old_label} → {new_label}"
        )
        order.status = order_status

    if order.payment_status != payment_status:
        old_label = _choice_label(
            Order.PaymentStatus.choices,
            order.payment_status,
        )
        new_label = _choice_label(
            Order.PaymentStatus.choices,
            payment_status,
        )

        changes.append(
            f"Stav platby: {old_label} → {new_label}"
        )
        order.payment_status = payment_status

    if order.fulfilment_status != fulfilment_status:
        old_label = _choice_label(
            Order.FulfilmentStatus.choices,
            order.fulfilment_status,
        )
        new_label = _choice_label(
            Order.FulfilmentStatus.choices,
            fulfilment_status,
        )

        changes.append(
            f"Stav vyřízení: {old_label} → {new_label}"
        )
        order.fulfilment_status = fulfilment_status

    note = note.strip()

    if not changes and not note:
        return order, False

    if changes:
        order.save(
            update_fields=[
                "status",
                "payment_status",
                "fulfilment_status",
                "updated_at",
            ]
        )

    OrderStatusHistory.objects.create(
        order=order,
        action=OrderStatusHistory.Action.STATE_CHANGE,
        description=(
            "; ".join(changes)
            if changes
            else "Byla přidána interní poznámka."
        ),
        order_status=order.status,
        payment_status=order.payment_status,
        fulfilment_status=order.fulfilment_status,
        note=note,
        performed_by=performed_by,
    )

    return order, True


@transaction.atomic
def cancel_order(
    *,
    order_id,
    reason,
    performed_by,
):
    order = (
        Order.objects
        .select_for_update()
        .prefetch_related("items")
        .get(pk=order_id)
    )

    if order.status == Order.Status.CANCELLED:
        raise OrderManagementError(
            "Objednávka už je stornovaná."
        )

    if order.payment_status == Order.PaymentStatus.PAID:
        raise OrderManagementError(
            "Zaplacenou objednávku zatím nelze stornovat. "
            "Nejdřív musíme doplnit proces vrácení platby."
        )

    if order.fulfilment_status in {
        Order.FulfilmentStatus.SHIPPED,
        Order.FulfilmentStatus.COMPLETED,
    }:
        raise OrderManagementError(
            "Odeslanou nebo vyřízenou objednávku nelze "
            "tímto jednoduchým stornem zrušit."
        )

    items = list(
        order.items.select_related("variant")
    )

    tracked_variant_ids = {
        item.variant_id
        for item in items
        if (
            item.variant_id
            and item.variant
            and item.variant.track_stock
        )
    }

    variants = (
        ProductVariant.objects
        .select_for_update()
        .filter(id__in=tracked_variant_ids)
    )

    variants_by_id = {
        variant.id: variant
        for variant in variants
    }

    restored_items = []

    for item in items:
        variant = variants_by_id.get(item.variant_id)

        if variant is None:
            continue

        variant.stock_quantity += item.quantity
        variant.save(update_fields=["stock_quantity"])

        restored_items.append(
            f"{item.product_name} – "
            f"{item.variant_name}: {item.quantity} ks"
        )

    order.status = Order.Status.CANCELLED
    order.payment_status = Order.PaymentStatus.CANCELLED
    order.fulfilment_status = (
        Order.FulfilmentStatus.UNFULFILLED
    )

    try:
        invoice = order.invoice
    except Invoice.DoesNotExist:
        invoice = None

    if invoice and invoice.status != Invoice.Status.CANCELLED:
        invoice.status = Invoice.Status.CANCELLED
        invoice.cancelled_at = timezone.now()

        invoice.save(
            update_fields=[
                "status",
                "cancelled_at",
                "updated_at",
            ]
        )

    order.save(
        update_fields=[
            "status",
            "payment_status",
            "fulfilment_status",
            "updated_at",
        ]
    )

    description = "Objednávka byla stornována."

    if restored_items:
        description += (
            " Na sklad bylo vráceno: "
            + "; ".join(restored_items)
            + "."
        )

    OrderStatusHistory.objects.create(
        order=order,
        action=OrderStatusHistory.Action.CANCELLED,
        description=description,
        order_status=order.status,
        payment_status=order.payment_status,
        fulfilment_status=order.fulfilment_status,
        note=reason.strip(),
        performed_by=performed_by,
    )

    return order