from django.conf import settings

from core.utils.payments import (
    build_spd_payload,
    make_qr_svg,
)


def get_bank_transfer_payment_data(order):
    payload = build_spd_payload(
        iban=settings.LIEDER_SHOP_IBAN,
        amount=order.total,
        message=f"Objednavka {order.number}",
        variable_symbol=order.variable_symbol,
        currency=order.currency,
    )

    return {
        "recipient": settings.LIEDER_SHOP_RECIPIENT,
        "account_display": settings.LIEDER_SHOP_ACCOUNT_DISPLAY,
        "iban": settings.LIEDER_SHOP_IBAN,
        "amount": order.total,
        "currency": order.currency,
        "variable_symbol": order.variable_symbol,
        "message": f"Objednávka {order.number}",
        "payload": payload,
        "qr_svg": make_qr_svg(payload),
    }