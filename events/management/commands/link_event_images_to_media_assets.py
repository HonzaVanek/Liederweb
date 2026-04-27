from django.core.management.base import BaseCommand

from events.models import Event, EventArtist, EventSponsor, EventTicketSettings
from media_assets.models import MediaAsset


def find_asset_for_email_image(email_image):
    if not email_image or not email_image.image:
        return None
    return MediaAsset.objects.filter(file=email_image.image.name).first()


class Command(BaseCommand):
    help = "Napojí eventové obrázky z EmailImage na nové MediaAsset FK."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Jen vypíše, co by se udělalo, bez uložení změn.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        updated = 0

        for event in Event.objects.all():
            changed = False

            if event.poster_image and not event.poster_asset:
                asset = find_asset_for_email_image(event.poster_image)
                if asset:
                    event.poster_asset = asset
                    changed = True

            if event.hero_image and not event.hero_asset:
                asset = find_asset_for_email_image(event.hero_image)
                if asset:
                    event.hero_asset = asset
                    changed = True

            if event.secondary_image and not event.secondary_asset:
                asset = find_asset_for_email_image(event.secondary_image)
                if asset:
                    event.secondary_asset = asset
                    changed = True

            if changed:
                updated += 1
                self.stdout.write(f"{'[DRY RUN] ' if dry_run else ''}Event: {event.title}")
                if not dry_run:
                    event.save(update_fields=["poster_asset", "hero_asset", "secondary_asset"])

        for artist in EventArtist.objects.all():
            if artist.photo_image and not artist.photo_asset:
                asset = find_asset_for_email_image(artist.photo_image)
                if asset:
                    updated += 1
                    self.stdout.write(f"{'[DRY RUN] ' if dry_run else ''}Artist: {artist.name}")
                    if not dry_run:
                        artist.photo_asset = asset
                        artist.save(update_fields=["photo_asset"])

        for sponsor in EventSponsor.objects.all():
            if sponsor.logo_image and not sponsor.logo_asset:
                asset = find_asset_for_email_image(sponsor.logo_image)
                if asset:
                    updated += 1
                    self.stdout.write(f"{'[DRY RUN] ' if dry_run else ''}Sponsor: {sponsor.name}")
                    if not dry_run:
                        sponsor.logo_asset = asset
                        sponsor.save(update_fields=["logo_asset"])

        for settings_obj in EventTicketSettings.objects.all():
            if settings_obj.logo_image and not settings_obj.logo_asset:
                asset = find_asset_for_email_image(settings_obj.logo_image)
                if asset:
                    updated += 1
                    self.stdout.write(f"{'[DRY RUN] ' if dry_run else ''}TicketSettings: {settings_obj.event.title}")
                    if not dry_run:
                        settings_obj.logo_asset = asset
                        settings_obj.save(update_fields=["logo_asset"])

        self.stdout.write(self.style.SUCCESS(f"Hotovo. Aktualizovaných záznamů: {updated}"))