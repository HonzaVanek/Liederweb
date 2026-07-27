from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from shop.models import Invoice


def _build_customer_address(order):
    lines = [
        order.address_line1,
        order.address_line2,
        " ".join(
            part
            for part in [
                order.postal_code,
                order.city,
            ]
            if part
        ),
        order.country,
    ]

    return "\n".join(
        line.strip()
        for line in lines
        if line and line.strip()
    )


def issue_invoice_for_order(order):
    issued_at = timezone.now()

    invoice, created = Invoice.objects.get_or_create(
        order=order,
        defaults={
            "issued_at": issued_at,
            "due_date": (
                timezone.localdate(issued_at)
                + timedelta(
                    days=settings.LIEDER_SHOP_INVOICE_DUE_DAYS
                )
            ),

            "seller_name": settings.LIEDER_SHOP_SELLER_NAME,
            "seller_address": settings.LIEDER_SHOP_SELLER_ADDRESS,
            "seller_company_id": (
                settings.LIEDER_SHOP_SELLER_COMPANY_ID
            ),
            "seller_vat_id": settings.LIEDER_SHOP_SELLER_VAT_ID,
            "seller_is_vat_payer": (
                settings.LIEDER_SHOP_SELLER_IS_VAT_PAYER
            ),

            "customer_name": order.customer_name,
            "customer_email": order.email,
            "customer_address": _build_customer_address(order),

            "subtotal": order.subtotal,
            "shipping_price": order.shipping_price,
            "total": order.total,
            "currency": order.currency,

            "payment_method": order.payment_method,
            "bank_account": (
                settings.LIEDER_SHOP_ACCOUNT_DISPLAY
            ),
            "iban": settings.LIEDER_SHOP_IBAN,
            "variable_symbol": order.variable_symbol,
        },
    )

    if created or not invoice.number:
        invoice.ensure_number()

    return invoice