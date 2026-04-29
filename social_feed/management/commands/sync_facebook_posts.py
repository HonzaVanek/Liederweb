import json
from urllib.parse import urlencode
from urllib.request import urlopen
from urllib.error import HTTPError, URLError

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils.dateparse import parse_datetime

from social_feed.models import SocialPost, SocialSource


class Command(BaseCommand):
    help = "Stáhne poslední Facebook posty a uloží je do databáze."

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=5,
            help="Kolik posledních postů stáhnout pro každý aktivní Facebook source.",
        )

    def handle(self, *args, **options):
        token = getattr(settings, "FACEBOOK_PAGE_ACCESS_TOKEN", "").strip()
        limit = options["limit"]

        if not token:
            self.stderr.write("Chybí FACEBOOK_PAGE_ACCESS_TOKEN v settings.")
            return

        sources = SocialSource.objects.filter(
            platform=SocialSource.Platform.FACEBOOK,
            is_active=True,
        )

        if not sources.exists():
            self.stdout.write("Není žádný aktivní Facebook source.")
            return

        total_created = 0
        total_updated = 0

        for source in sources:
            created_count, updated_count = self.sync_source(source, token, limit)
            total_created += created_count
            total_updated += updated_count

        self.stdout.write(
            self.style.SUCCESS(
                f"Hotovo. Vytvořeno: {total_created}, aktualizováno: {total_updated}"
            )
        )

    def sync_source(self, source, token, limit):
        params = {
            "fields": "id,message,created_time,permalink_url,full_picture",
            "limit": limit,
            "access_token": token,
        }
        url = f"https://graph.facebook.com/v25.0/{source.external_account_id}/posts?{urlencode(params)}"

        try:
            with urlopen(url, timeout=30) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            try:
                error_body = exc.read().decode("utf-8", errors="replace")
            except Exception:
                error_body = "<nepodařilo se přečíst tělo chyby>"

            self.stderr.write(
                self.style.ERROR(
                    f"[{source.name}] HTTP chyba {exc.code}: {exc.reason} | {error_body}"
                )
            )
            return 0, 0
        except URLError as exc:
            self.stderr.write(
                self.style.ERROR(
                    f"[{source.name}] Síťová chyba: {exc.reason}"
                )
            )
            return 0, 0
        except Exception as exc:
            self.stderr.write(
                self.style.ERROR(
                    f"[{source.name}] Neočekávaná chyba: {exc}"
                )
            )
            return 0, 0

        if "error" in payload:
            self.stderr.write(
                self.style.ERROR(
                    f"[{source.name}] Facebook API error: {payload['error']}"
                )
            )
            return 0, 0

        items = payload.get("data", [])
        created_count = 0
        updated_count = 0

        for item in items:
            published_at = parse_datetime(item.get("created_time") or "")
            image_url = item.get("full_picture") or ""
            message = (item.get("message") or "").strip()

            defaults = {
                "message": message,
                "permalink_url": item.get("permalink_url") or "",
                "media_type": (
                    SocialPost.MediaType.IMAGE if image_url else SocialPost.MediaType.TEXT
                ),
                "image_url": image_url,
                "thumbnail_url": image_url,
                "published_at": published_at,
                "is_visible": True,
                "raw_payload": item,
            }

            obj, created = SocialPost.objects.update_or_create(
                source=source,
                external_post_id=item["id"],
                defaults=defaults,
            )

            if created:
                created_count += 1
            else:
                updated_count += 1

        self.stdout.write(
            f"[{source.name}] načteno {len(items)} postů | vytvořeno {created_count} | aktualizováno {updated_count}"
        )

        return created_count, updated_count