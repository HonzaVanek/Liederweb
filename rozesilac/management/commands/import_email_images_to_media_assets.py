from pathlib import Path

from django.core.management.base import BaseCommand

from media_assets.models import MediaAsset
from rozesilac.models import EmailImage


class Command(BaseCommand):
    help = "Převede existující EmailImage do MediaAsset."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Jen vypíše, co by se udělalo, bez uložení změn.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]

        images = EmailImage.objects.all().order_by("id")

        if not images.exists():
            self.stdout.write(self.style.WARNING("Nebyly nalezeny žádné EmailImage záznamy."))
            return

        created_count = 0
        reused_count = 0

        for email_image in images:
            file_name = email_image.image.name

            asset = MediaAsset.objects.filter(file=file_name).first()

            if asset:
                reused_count += 1
                self.stdout.write(
                    f"{'[DRY RUN] ' if dry_run else ''}EXISTS: {email_image.title or Path(file_name).name}"
                )
                continue

            asset = MediaAsset(
                title=email_image.title or Path(file_name).stem,
                file=file_name,
                alt_text=email_image.title or "",
                uploaded_by=email_image.uploaded_by,
                is_active=True,
            )

            if not dry_run:
                asset.save()

                # zachováme původní čas nahrání
                MediaAsset.objects.filter(pk=asset.pk).update(
                    uploaded_at=email_image.uploaded_at
                )

            created_count += 1
            self.stdout.write(
                f"{'[DRY RUN] ' if dry_run else ''}CREATE: {email_image.title or Path(file_name).name}"
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Hotovo. Vytvořeno assetů: {created_count}, už existovalo: {reused_count}"
            )
        )