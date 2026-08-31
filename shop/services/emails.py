import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives, get_connection
from django.template.loader import render_to_string
from django.utils import timezone
from django.urls import reverse

from shop.models import Order
from shop.services.invoice_pdf import (
    build_invoice_pdf,
    build_invoice_pdf_filename,
)


logger = logging.getLogger("liederweb.shop.emails")



def get_shop_email_connection():
    missing_settings = []

    if not settings.SHOP_EMAIL_HOST_USER:
        missing_settings.append("SHOP_EMAIL_HOST_USER")

    if not settings.SHOP_EMAIL_HOST_PASSWORD:
        missing_settings.append("SHOP_EMAIL_HOST_PASSWORD")

    if missing_settings:
        raise RuntimeError(
            "Chybí nastavení e-shopového SMTP: "
            + ", ".join(missing_settings)
        )

    if (
        settings.SHOP_EMAIL_USE_TLS
        and settings.SHOP_EMAIL_USE_SSL
    ):
        raise RuntimeError(
            "SHOP_EMAIL_USE_TLS a SHOP_EMAIL_USE_SSL "
            "nemohou být současně zapnuté."
        )

    return get_connection(
        backend=settings.SHOP_EMAIL_BACKEND,
        fail_silently=False,
        host=settings.SHOP_EMAIL_HOST,
        port=settings.SHOP_EMAIL_PORT,
        username=settings.SHOP_EMAIL_HOST_USER,
        password=settings.SHOP_EMAIL_HOST_PASSWORD,
        use_tls=settings.SHOP_EMAIL_USE_TLS,
        use_ssl=settings.SHOP_EMAIL_USE_SSL,
        timeout=settings.SHOP_EMAIL_TIMEOUT,
    )


def send_order_confirmation_email(order_id):
    order = (
        Order.objects
        .select_related("invoice")
        .prefetch_related("items")
        .get(pk=order_id)
    )

    try:
        invoice_pdf = build_invoice_pdf(order.invoice)

        download_url = None

        if order.contains_digital_content:
            download_url = (
                settings.SHOP_BASE_URL.rstrip("/")
                + reverse(
                    "shop:digital_downloads",
                    kwargs={
                        "token": order.download_token,
                    },
                )
            )

        context = {
            "order": order,
            "invoice": order.invoice,
            "download_url": download_url,
        }

        text_body = render_to_string(
            "shop/emails/order_confirmation.txt",
            context,
        )

        html_body = render_to_string(
            "shop/emails/order_confirmation.html",
            context,
        )

        reply_to = []

        if settings.SHOP_EMAIL_REPLY_TO:
            reply_to.append(
                settings.SHOP_EMAIL_REPLY_TO
            )

        with get_shop_email_connection() as connection:
            message = EmailMultiAlternatives(
                subject=(
                    f"Potvrzení objednávky "
                    f"{order.number}"
                ),
                body=text_body,
                from_email=settings.SHOP_EMAIL_FROM,
                to=[order.email],
                reply_to=reply_to,
                connection=connection,
            )

            message.attach_alternative(
                html_body,
                "text/html",
            )

            message.attach(
                build_invoice_pdf_filename(
                    order.invoice
                ),
                invoice_pdf,
                "application/pdf",
            )

            sent_count = message.send(
                fail_silently=False
            )

            if sent_count != 1:
                raise RuntimeError(
                    "SMTP server nepotvrdil "
                    "odeslání e-mailu."
                )

    except Exception as exc:
        logger.exception(
            "Nepodařilo se odeslat potvrzení "
            "objednávky %s.",
            order.number,
        )

        Order.objects.filter(pk=order.pk).update(
            confirmation_email_error=str(exc)[:2000],
        )

        return False

    Order.objects.filter(pk=order.pk).update(
        confirmation_email_sent_at=timezone.now(),
        confirmation_email_error="",
    )

    return True


def send_staff_new_order_email(order_id):
    order = (
        Order.objects
        .select_related("invoice")
        .prefetch_related("items")
        .get(pk=order_id)
    )

    try:
        recipients = list(
            settings.SHOP_STAFF_NOTIFICATION_EMAILS
        )

        if not recipients:
            raise RuntimeError(
                "SHOP_STAFF_NOTIFICATION_EMAILS "
                "neobsahuje žádnou adresu."
            )

        order_detail_url = (
            settings.SHOP_BASE_URL
            + reverse(
                "shop_staff:order_detail",
                args=[order.id],
            )
        )

        context = {
            "order": order,
            "invoice": order.invoice,
            "order_detail_url": order_detail_url,
        }

        text_body = render_to_string(
            "shop/emails/staff_new_order.txt",
            context,
        )

        html_body = render_to_string(
            "shop/emails/staff_new_order.html",
            context,
        )

        reply_to = []

        if settings.SHOP_EMAIL_REPLY_TO:
            reply_to.append(
                settings.SHOP_EMAIL_REPLY_TO
            )

        with get_shop_email_connection() as connection:
            message = EmailMultiAlternatives(
                subject=(
                    f"[E-shop] Nová objednávka "
                    f"{order.number} – "
                    f"{order.total} Kč"
                ),
                body=text_body,
                from_email=settings.SHOP_EMAIL_FROM,
                to=recipients,
                reply_to=reply_to,
                connection=connection,
            )

            message.attach_alternative(
                html_body,
                "text/html",
            )

            sent_count = message.send(
                fail_silently=False
            )

            if sent_count != 1:
                raise RuntimeError(
                    "SMTP server nepotvrdil odeslání "
                    "upozornění staffu."
                )

    except Exception as exc:
        logger.exception(
            "Nepodařilo se odeslat upozornění staffu "
            "na objednávku %s.",
            order.number,
        )

        Order.objects.filter(pk=order.pk).update(
            staff_notification_error=str(exc)[:2000],
        )

        return False

    Order.objects.filter(pk=order.pk).update(
        staff_notification_sent_at=timezone.now(),
        staff_notification_error="",
    )

    return True