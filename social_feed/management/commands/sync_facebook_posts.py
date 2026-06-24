import json
import re
import subprocess
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
        url = f"https://graph.facebook.com/v25.0/me/posts?{urlencode(params)}"

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
        items = self.drop_duplicate_video_shadow_posts(items)
        created_count = 0
        updated_count = 0

        for item in items:
            published_at = parse_datetime(item.get("created_time") or "")
            fallback_image_url = (item.get("full_picture") or "")[:1500]
            message = self.get_post_message(
                item=item,
                token=token,
                source_name=source.name,
            )
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
                    first_item.get("thumbnail_url")
                    or first_item.get("media_url")
                    or fallback_image_url
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

            prepared_media_items = []

            for index, media_item in enumerate(post_media_items[:12], start=1):
                media_type = media_item.get("media_type") or SocialPostMedia.MediaType.OTHER
                media_url = (media_item.get("media_url") or "")[:1500]
                thumbnail_url = (media_item.get("thumbnail_url") or "")[:1500]

                has_audio = None
                width = media_item.get("width")
                height = media_item.get("height")

                if media_type == SocialPostMedia.MediaType.VIDEO:
                    probe = self.probe_video_media(media_url)

                    has_audio = probe["has_audio"]

                    if probe["width"]:
                        width = probe["width"]

                    if probe["height"]:
                        height = probe["height"]

                    self.stdout.write(
                        f"[{source.name}] video {media_item.get('external_media_id') or ''} | "
                        f"has_audio={has_audio} | width={width} | height={height}"
                    )

                prepared_media_items.append(
                    {
                        "external_media_id": media_item.get("external_media_id"),
                        "media_type": media_type,
                        "media_url": media_url,
                        "thumbnail_url": thumbnail_url,
                        "sort_order": index,
                        "has_audio": has_audio,
                        "width": width,
                        "height": height,
                        "facebook_url": (media_item.get("facebook_url") or "")[:1000],
                    }
                )

            with transaction.atomic():
                obj, created = SocialPost.objects.update_or_create(
                    source=source,
                    external_post_id=item["id"],
                    defaults=defaults,
                )

                obj.media_items.all().delete()

                media_objects = []

                for media_item in prepared_media_items:
                    media_objects.append(
                        SocialPostMedia(
                            post=obj,
                            external_media_id=media_item["external_media_id"],
                            media_type=media_item["media_type"],
                            media_url=media_item["media_url"],
                            thumbnail_url=media_item["thumbnail_url"],
                            sort_order=media_item["sort_order"],
                            has_audio=media_item["has_audio"],
                            width=media_item["width"],
                            height=media_item["height"],
                            facebook_url=media_item.get("facebook_url", "")[:1000],
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
                            has_audio=None,
                            width=None,
                            height=None,
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
    
    def drop_duplicate_video_shadow_posts(self, items):
        """
        Facebook někdy vrátí dvě položky k jednomu reálnému wall postu:
        - skutečný post stránky s textem a médií,
        - prázdný video-only objekt o pár sekund později.

        Ten video-only objekt nechceme ukládat jako samostatný SocialPost,
        protože pak na homepage přebije skutečný post.
        Video samotné nezahazujeme — zůstane jako media item u skutečného postu.
        """
        real_post_times = []

        for item in items:
            message = (item.get("message") or "").strip()
            permalink_url = item.get("permalink_url") or ""

            if not message:
                continue

            if "/posts/" not in permalink_url:
                continue

            published_at = parse_datetime(item.get("created_time") or "")
            if published_at:
                real_post_times.append(published_at)

        if not real_post_times:
            return items

        filtered_items = []

        for item in items:
            message = (item.get("message") or "").strip()
            permalink_url = item.get("permalink_url") or ""
            published_at = parse_datetime(item.get("created_time") or "")

            is_empty_video_shadow = (
                not message
                and "/videos/" in permalink_url
                and published_at is not None
            )

            has_near_real_post = False

            if is_empty_video_shadow:
                for real_post_time in real_post_times:
                    diff_seconds = abs((published_at - real_post_time).total_seconds())

                    if diff_seconds <= 120:
                        has_near_real_post = True
                        break

            if is_empty_video_shadow and has_near_real_post:
                self.stdout.write(
                    self.style.WARNING(
                        f"Přeskakuji duplicitní video-only objekt: {item.get('id')}"
                    )
                )
                continue

            filtered_items.append(item)

        return filtered_items

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
        target_data = attachment.get("target") or {}
        facebook_url = (target_data.get("url") or attachment.get("url") or "").strip()

        if raw_media_type in {"photo", "album"}:
            media_type = SocialPostMedia.MediaType.IMAGE
        elif raw_media_type == "video":
            media_type = SocialPostMedia.MediaType.VIDEO
        else:
            media_type = SocialPostMedia.MediaType.OTHER

        media_data = attachment.get("media") or {}
        image_data = media_data.get("image") or {}

        media_url = self.extract_media_url(media_data, attachment)
        thumbnail_url = self.extract_thumbnail_url(media_data, attachment, media_url)

        if not media_url and not thumbnail_url:
            return None

        width = None
        height = None

        try:
            width_value = int(image_data.get("width") or 0)
            height_value = int(image_data.get("height") or 0)
        except (TypeError, ValueError):
            width_value = 0
            height_value = 0

        if width_value > 0:
            width = width_value

        if height_value > 0:
            height = height_value

        return {
            "external_media_id": attachment.get("id"),
            "media_type": media_type,
            "media_url": media_url,
            "thumbnail_url": thumbnail_url,
            "width": width,
            "height": height,
            "facebook_url": facebook_url[:1000],
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
        

    def probe_video_media(self, media_url):
        """
        Vrací:
        {
            "has_audio": True/False/None,
            "width": int/None,
            "height": int/None,
        }

        None znamená, že se daná věc nepodařila ověřit.
        """
        result_data = {
            "has_audio": None,
            "width": None,
            "height": None,
        }

        if not media_url:
            return result_data

        ffprobe_path = getattr(settings, "FFPROBE_PATH", "ffprobe")

        try:
            result = subprocess.run(
                [
                    ffprobe_path,
                    "-v", "error",
                    "-show_streams",
                    "-of", "json",
                    media_url,
                ],
                capture_output=True,
                text=True,
                timeout=20,
            )
        except FileNotFoundError:
            self.stderr.write(
                self.style.WARNING(
                    "ffprobe není dostupný. Audio stopu ani rozměry videa nelze ověřit."
                )
            )
            return result_data
        except subprocess.TimeoutExpired:
            self.stderr.write(
                self.style.WARNING("ffprobe timeout při kontrole Facebook videa.")
            )
            return result_data
        except Exception as exc:
            self.stderr.write(
                self.style.WARNING(f"Nepodařilo se ověřit Facebook video: {exc}")
            )
            return result_data

        if result.returncode != 0:
            self.stderr.write(
                self.style.WARNING(
                    f"ffprobe neověřil Facebook video: {result.stderr.strip()[:300]}"
                )
            )
            return result_data

        try:
            payload = json.loads(result.stdout or "{}")
        except json.JSONDecodeError:
            self.stderr.write(
                self.style.WARNING("ffprobe vrátil nečitelný JSON.")
            )
            return result_data

        streams = payload.get("streams") or []

        audio_streams = [
            stream for stream in streams
            if stream.get("codec_type") == "audio"
        ]

        video_streams = [
            stream for stream in streams
            if stream.get("codec_type") == "video"
        ]

        result_data["has_audio"] = bool(audio_streams)

        if video_streams:
            video_stream = video_streams[0]

            try:
                width = int(video_stream.get("width") or 0)
                height = int(video_stream.get("height") or 0)
            except (TypeError, ValueError):
                width = 0
                height = 0

            if width > 0:
                result_data["width"] = width

            if height > 0:
                result_data["height"] = height

        return result_data
    
    def extract_video_id(self, item):
        """
        U video postů bývá ID videa buď za podtržítkem v post ID,
        nebo přímo v permalinku /videos/<id>.
        """
        item_id = item.get("id") or ""
        permalink_url = item.get("permalink_url") or ""

        match = re.search(r"/videos/(\d+)", permalink_url)
        if match:
            return match.group(1)

        if "_" in item_id:
            possible_id = item_id.rsplit("_", 1)[-1]
            if possible_id.isdigit():
                return possible_id

        return ""
    
    def fetch_video_text(self, video_id, token, source_name):
        """
        Některé Facebook video posty nemají text v poli message u /posts.
        Zkusíme ho proto dotáhnout přímo z video objektu přes description.
        """
        if not video_id:
            return ""

        params = {
            "fields": "description",
            "access_token": token,
        }
        url = f"https://graph.facebook.com/v25.0/{video_id}?{urlencode(params)}"

        payload = self.fetch_json(url, f"{source_name} video {video_id}")
        if payload is None:
            return ""

        if "error" in payload:
            return ""

        return (payload.get("description") or "").strip()
    
    def fetch_post_attachment_text(self, post_id, token, source_name):
        """
        Některé Facebook posty bez message mají text schovaný v attachments,
        případně attachment ukazuje na event permalink, kde může být skutečný text.
        """
        if not post_id:
            return ""

        params = {
            "fields": (
                "id,"
                "media_type,"
                "title,"
                "description,"
                "url,"
                "subattachments.limit(12){id,media_type,title,description,url}"
            ),
            "access_token": token,
        }
        url = f"https://graph.facebook.com/v25.0/{post_id}/attachments?{urlencode(params)}"

        payload = self.fetch_json(url, f"{source_name} / post {post_id} attachments text")
        if payload is None or "error" in payload:
            return ""

        candidates = []
        event_permalink_object_ids = []

        for attachment in payload.get("data", []):
            candidates.append(attachment.get("description") or "")
            candidates.append(attachment.get("title") or "")

            attachment_url = attachment.get("url") or ""
            event_object_id = self.extract_event_permalink_post_id_from_url(attachment_url)
            if event_object_id:
                event_permalink_object_ids.append(event_object_id)

            subattachments = (
                attachment.get("subattachments", {}) or {}
            ).get("data", [])

            for sub in subattachments:
                candidates.append(sub.get("description") or "")
                candidates.append(sub.get("title") or "")

                sub_url = sub.get("url") or ""
                sub_event_object_id = self.extract_event_permalink_post_id_from_url(sub_url)
                if sub_event_object_id:
                    event_permalink_object_ids.append(sub_event_object_id)

        for candidate in candidates:
            text = (candidate or "").strip()

            if not text:
                continue

            lowered = text.lower()
            if lowered.startswith("may be an image"):
                continue
            if lowered.startswith("may be a video"):
                continue

            return text

        #for event_object_id in event_permalink_object_ids:
         #   text = self.fetch_graph_object_text(event_object_id, token, source_name)
          #  if text:
           #     return text

        return ""
    
    def get_post_message(self, item, token, source_name):
        """
        Primárně bereme message z /posts.
        Když chybí, zkusíme video description.
        Když chybí i to, zkusíme text z attachments.
        """
        message = (item.get("message") or "").strip()

        if message:
            return message

        permalink_url = item.get("permalink_url") or ""

        if "/videos/" in permalink_url:
            video_id = self.extract_video_id(item)
            video_text = self.fetch_video_text(video_id, token, source_name)

            if video_text:
                return video_text

        return self.fetch_post_attachment_text(
            post_id=item.get("id") or "",
            token=token,
            source_name=source_name,
        )
    
    def extract_event_permalink_post_id_from_url(self, url):
        """
        Z URL typu:
        https://www.facebook.com/events/2457722498032606/permalink/2473588786445977/
        vytáhne ID event postu:
        2473588786445977
        """
        if not url:
            return ""

        match = re.search(r"/events/\d+/permalink/(\d+)", url)
        if match:
            return match.group(1)

        return ""


    def fetch_graph_object_text(self, object_id, token, source_name):
        """
        Zkusí vytáhnout text přímo z Graph objektu.
        U event permalinků může být text uložený v message.
        """
        if not object_id:
            return ""

        params = {
            "fields": "message,story,description",
            "access_token": token,
        }
        url = f"https://graph.facebook.com/v25.0/{object_id}?{urlencode(params)}"

        payload = self.fetch_json(url, f"{source_name} object {object_id}")
        if payload is None or "error" in payload:
            return ""

        for field in ["message", "description", "story"]:
            value = (payload.get(field) or "").strip()
            if value:
                return value

        return ""