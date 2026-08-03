from django.core.management.base import BaseCommand
from django.utils import timezone

from shop.models import Order
from shop.services.orders import (
    OrderManagementError,
    cancel_order,
)


class Command(BaseCommand):
    help = (
        "Stornuje expirované nezaplacené objednávky "
        "a vrátí jejich skladové položky."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help=(
                "Pouze vypíše objednávky, které by byly "
                "stornovány."
            ),
        )

    def handle(self, *args, **options):
        now = timezone.now()
        dry_run = options["dry_run"]

        orders = (
            Order.objects
            .filter(
                expires_at__isnull=False,
                expires_at__lte=now,
                payment_status=Order.PaymentStatus.AWAITING,
                fulfilment_status=(
                    Order.FulfilmentStatus.UNFULFILLED
                ),
                status__in=[
                    Order.Status.NEW,
                    Order.Status.CONFIRMED,
                ],
            )
            .order_by("id")
        )

        order_ids = list(
            orders.values_list("id", flat=True)
        )

        if not order_ids:
            self.stdout.write(
                self.style.SUCCESS(
                    "Žádné expirované nezaplacené "
                    "objednávky nebyly nalezeny."
                )
            )
            return

        if dry_run:
            self.stdout.write(
                f"Bylo nalezeno {len(order_ids)} "
                f"objednávek k expiraci:"
            )

            for order in orders:
                self.stdout.write(
                    f"- {order.number} | "
                    f"{order.email} | "
                    f"{order.total} Kč | "
                    f"expirace {order.expires_at}"
                )

            self.stdout.write(
                self.style.WARNING(
                    "Dry-run: nebyly provedeny žádné změny."
                )
            )
            return

        cancelled_count = 0
        skipped_count = 0

        for order_id in order_ids:
            try:
                order = cancel_order(
                    order_id=order_id,
                    reason=(
                        "Automaticky stornováno po uplynutí "
                        "lhůty k úhradě."
                    ),
                    performed_by=None,
                )

            except (
                OrderManagementError,
                Order.DoesNotExist,
            ) as exc:
                skipped_count += 1

                self.stderr.write(
                    self.style.WARNING(
                        f"Objednávka ID {order_id} "
                        f"nebyla stornována: {exc}"
                    )
                )

            else:
                cancelled_count += 1

                self.stdout.write(
                    self.style.SUCCESS(
                        f"Stornována objednávka "
                        f"{order.number}."
                    )
                )

        self.stdout.write(
            self.style.SUCCESS(
                f"Dokončeno. Stornováno: "
                f"{cancelled_count}, přeskočeno: "
                f"{skipped_count}."
            )
        )