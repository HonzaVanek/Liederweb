from dataclasses import dataclass

from shop.models import DigitalDownloadGrant, Order
from shop.services.downloads import (
    DigitalDownloadGrantError,
    grant_digital_downloads,
)
from shop.services.emails import send_digital_ready_email
from shop.services.orders import update_order_states


@dataclass(frozen=True)
class PaymentCompletionResult:
    created_downloads: int = 0
    download_error: str = ""
    email_attempted: bool = False
    email_sent: bool = False
    email_error: str = ""


def _finalize_paid_order(order):
    """
    Provede vše, co má následovat po úspěšně
    zaznamenané platbě.

    Samotný stav platby už v tuto chvíli musí být PAID.
    """
    if order.payment_status != Order.PaymentStatus.PAID:
        raise ValueError(
            "Dokončení platby lze provést pouze "
            "pro zaplacenou objednávku."
        )

    # U čistě fyzické objednávky zatím není
    # po zaplacení potřeba nic dalšího dělat.
    if not order.contains_digital_content:
        return PaymentCompletionResult()

    try:
        created_downloads = grant_digital_downloads(
            order
        )

    except DigitalDownloadGrantError as exc:
        return PaymentCompletionResult(
            download_error=str(exc),
        )

    # Dotazujeme DB přímo, aby nás případně
    # neovlivnil starší prefetched related cache.
    has_downloads = (
        DigitalDownloadGrant.objects
        .filter(order_id=order.id)
        .exists()
    )

    if not has_downloads:
        return PaymentCompletionResult(
            created_downloads=created_downloads,
            download_error=(
                "Objednávka je zaplacená a obsahuje "
                "digitální obsah, ale nevznikly žádné "
                "soubory ke stažení."
            ),
        )

    # Mail už byl úspěšně odeslán.
    if order.digital_ready_email_sent_at:
        return PaymentCompletionResult(
            created_downloads=created_downloads,
        )

    email_sent = send_digital_ready_email(
        order.id
    )

    order.refresh_from_db(
        fields=[
            "digital_ready_email_sent_at",
            "digital_ready_email_error",
        ]
    )

    return PaymentCompletionResult(
        created_downloads=created_downloads,
        email_attempted=True,
        email_sent=email_sent,
        email_error=(
            order.digital_ready_email_error
            if not email_sent
            else ""
        ),
    )


def mark_order_paid(
    *,
    order_id,
    order_status=None,
    fulfilment_status=None,
    note="",
    performed_by=None,
):
    """
    Jednotné místo pro označení objednávky jako zaplacené.

    Uloží PAID přes existující správu stavů a následně
    provede všechny navazující akce.
    """
    order = Order.objects.get(pk=order_id)

    if order_status is None:
        order_status = order.status

    if fulfilment_status is None:
        fulfilment_status = order.fulfilment_status

    order, changed = update_order_states(
        order_id=order.id,
        order_status=order_status,
        payment_status=Order.PaymentStatus.PAID,
        fulfilment_status=fulfilment_status,
        note=note,
        performed_by=performed_by,
    )

    completion = _finalize_paid_order(order)

    return order, changed, completion