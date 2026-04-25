from django.core.management.base import BaseCommand
from core.models import Person
from media_assets.models import MediaAsset


class Command(BaseCommand):
    help = "Převede existující Person.photo do MediaAsset a napojí photo_asset."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Jen vypíše, co by se udělalo, bez uložení změn.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]

        people = Person.objects.exclude(photo="").exclude(photo__isnull=True).filter(photo_asset__isnull=True)

        if not people.exists():
            self.stdout.write(self.style.WARNING("Nebyly nalezeny žádné profily k převodu."))
            return

        created_count = 0
        linked_count = 0

        for person in people:
            file_name = person.photo.name

            asset = MediaAsset.objects.filter(file=file_name).first()

            if not asset:
                asset = MediaAsset(
                    title=person.name,
                    file=file_name,
                    alt_text=person.name,
                    is_active=True,
                )
                if not dry_run:
                    asset.save()
                created_count += 1

            if not dry_run:
                person.photo_asset = asset
                person.save(update_fields=["photo_asset"])

            linked_count += 1
            self.stdout.write(f"{'[DRY RUN] ' if dry_run else ''}{person.name} -> {file_name}")

        self.stdout.write(self.style.SUCCESS(
            f"Hotovo. Vytvořeno assetů: {created_count}, napojeno profilů: {linked_count}"
        ))