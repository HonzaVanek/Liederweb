import json
from urllib.parse import urlencode
from urllib.request import urlopen
from urllib.error import HTTPError, URLError

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils.dateparse import parse_datetime

from social_feed.models import SocialPost, SocialPostMedia, SocialSource




class Command(BaseCommand):
    help = "Stáhne poslední Facebook posty a uloží je do databáze."


    def normalize_message_tags(self, raw_tags):
        normalized = []

        if isinstance(raw_tags, dict):
            items = []
            for value in raw_tags.values():
                if isinstance(value, list):
                    items.extend(value)
                elif isinstance(value, dict):
                    items.append(value)
        elif isinstance(raw_tags, list):
            items = raw_tags
        else:
            items = []

        for item in items:
            if not isinstance(item, dict):
                continue

            tag_id = str(item.get("id") or "").strip()
            name = (item.get("name") or "").strip()

            try:
                offset = int(item.get("offset"))
                length = int(item.get("length"))
            except (TypeError, ValueError):
                continue

            if not tag_id or not name or offset < 0 or length <= 0:
                continue

            normalized.append(
                {
                    "id": tag_id,
                    "name": name,
                    "offset": offset,
                    "length": length,
                    "type": (item.get("type") or "").strip(),
                }
            )

        normalized.sort(key=lambda x: (x["offset"], -x["length"]))
        return normalized

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
            "fields": "id,message,message_tags,created_time,permalink_url,full_picture",
            "limit": limit,
            "access_token": token,
        }
        url = f"https://graph.facebook.com/v25.0/{source.external_account_id}/posts?{urlencode(params)}"

        payload = self.fetch_json(url, source.name)
        if payload is None:
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
            fallback_image_url = (item.get("full_picture") or "")[:1500]
            message = (item.get("message") or "").strip()
            message_tags = self.normalize_message_tags(item.get("message_tags"))
            post_media_items = self.fetch_post_media_items(
                post_id=item["id"],
                token=token,
                source_name=source.name,
            )

            primary_media_url = fallback_image_url
            primary_thumbnail_url = fallback_image_url
            post_media_type = SocialPost.MediaType.TEXT if message else SocialPost.MediaType.OTHER

            if post_media_items:
                first_item = post_media_items[0]
                primary_media_url = (first_item.get("media_url") or fallback_image_url)[:1500]
                primary_thumbnail_url = (
                    first_item.get("thumbnail_url") or first_item.get("media_url") or fallback_image_url
                )[:1500]

                if len(post_media_items) > 1:
                    post_media_type = SocialPost.MediaType.CAROUSEL
                else:
                    first_type = first_item.get("media_type")
                    if first_type == SocialPostMedia.MediaType.VIDEO:
                        post_media_type = SocialPost.MediaType.VIDEO
                    elif first_type == SocialPostMedia.MediaType.IMAGE:
                        post_media_type = SocialPost.MediaType.IMAGE
                    else:
                        post_media_type = SocialPost.MediaType.OTHER
            elif fallback_image_url:
                post_media_type = SocialPost.MediaType.IMAGE

            defaults = {
                "message": message,
                "message_tags": message_tags,
                "permalink_url": (item.get("permalink_url") or "")[:1000],
                "media_type": post_media_type,
                "image_url": primary_media_url,
                "thumbnail_url": primary_thumbnail_url,
                "published_at": published_at,
                "is_visible": True,
                "raw_payload": item,               
            }

            with transaction.atomic():
                obj, created = SocialPost.objects.update_or_create(
                    source=source,
                    external_post_id=item["id"],
                    defaults=defaults,
                )

                obj.media_items.all().delete()

                media_objects = []
                for index, media_item in enumerate(post_media_items[:12], start=1):
                    media_objects.append(
                        SocialPostMedia(
                            post=obj,
                            external_media_id=media_item.get("external_media_id"),
                            media_type=media_item.get("media_type") or SocialPostMedia.MediaType.OTHER,
                            media_url=(media_item.get("media_url") or "")[:1500],
                            thumbnail_url=(media_item.get("thumbnail_url") or "")[:1500],
                            sort_order=index,
                        )
                    )

                if not media_objects and fallback_image_url:
                    media_objects.append(
                        SocialPostMedia(
                            post=obj,
                            external_media_id=None,
                            media_type=SocialPostMedia.MediaType.IMAGE,
                            media_url=fallback_image_url,
                            thumbnail_url=fallback_image_url,
                            sort_order=1,
                        )
                    )

                if media_objects:
                    SocialPostMedia.objects.bulk_create(media_objects)

            if created:
                created_count += 1
            else:
                updated_count += 1

        self.stdout.write(
            f"[{source.name}] načteno {len(items)} postů | vytvořeno {created_count} | aktualizováno {updated_count}"
        )

        return created_count, updated_count

    def fetch_post_media_items(self, post_id, token, source_name):
        params = {
            "fields": (
                "id,"
                "media_type,"
                "media,"
                "source,"
                "url,"
                "subattachments.limit(12){id,media_type,media,source,url}"
            ),
            "limit": 12,
            "access_token": token,
        }
        url = f"https://graph.facebook.com/v25.0/{post_id}/attachments?{urlencode(params)}"

        payload = self.fetch_json(url, f"{source_name} / post {post_id}")
        if payload is None or "error" in payload:
            return []

        attachments = payload.get("data", [])
        collected = []

        for attachment in attachments:
            subattachments = (
                attachment.get("subattachments", {}) or {}
            ).get("data", [])

            if subattachments:
                for sub in subattachments:
                    normalized = self.normalize_attachment(sub)
                    if normalized:
                        collected.append(normalized)
            else:
                normalized = self.normalize_attachment(attachment)
                if normalized:
                    collected.append(normalized)

        unique = []
        seen = set()

        for item in collected:
            key = (
                item.get("external_media_id") or "",
                item.get("media_url") or "",
            )
            if key in seen:
                continue
            seen.add(key)
            unique.append(item)

        return unique[:12]

    def normalize_attachment(self, attachment):
        raw_media_type = (attachment.get("media_type") or "").lower()

        if raw_media_type in {"photo", "album"}:
            media_type = SocialPostMedia.MediaType.IMAGE
        elif raw_media_type == "video":
            media_type = SocialPostMedia.MediaType.VIDEO
        else:
            media_type = SocialPostMedia.MediaType.OTHER

        media_data = attachment.get("media") or {}
        media_url = self.extract_media_url(media_data, attachment)
        thumbnail_url = self.extract_thumbnail_url(media_data, attachment, media_url)

        if not media_url and not thumbnail_url:
            return None

        return {
            "external_media_id": attachment.get("id"),
            "media_type": media_type,
            "media_url": media_url,
            "thumbnail_url": thumbnail_url,
        }

    def extract_media_url(self, media_data, attachment):
        raw_media_type = (attachment.get("media_type") or "").lower()

        if raw_media_type == "video":
            return attachment.get("source") or media_data.get("source") or ""

        image = media_data.get("image") or {}
        return image.get("src") or attachment.get("url") or ""

    def extract_thumbnail_url(self, media_data, attachment, fallback=""):
        image = media_data.get("image") or {}
        return image.get("src") or attachment.get("url") or fallback or ""

    def fetch_json(self, url, source_name):
        try:
            with urlopen(url, timeout=60) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            try:
                error_body = exc.read().decode("utf-8", errors="replace")
            except Exception:
                error_body = "<nepodařilo se přečíst tělo chyby>"

            self.stderr.write(
                self.style.ERROR(
                    f"[{source_name}] HTTP chyba {exc.code}: {exc.reason} | {error_body}"
                )
            )
            return None
        except URLError as exc:
            self.stderr.write(
                self.style.ERROR(
                    f"[{source_name}] Síťová chyba: {exc.reason}"
                )
            )
            return None
        except Exception as exc:
            self.stderr.write(
                self.style.ERROR(
                    f"[{source_name}] Neočekávaná chyba: {exc}"
                )
            )
            return None