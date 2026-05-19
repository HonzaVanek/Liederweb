from django import template
from django.utils.html import escape
from django.utils.safestring import mark_safe

register = template.Library()


@register.filter
def facebook_message_html(post):
    if not post:
        return ""

    text = (getattr(post, "message", "") or "")
    tags = getattr(post, "message_tags", []) or []

    if not text:
        return ""

    valid_tags = []
    for tag in tags:
        if not isinstance(tag, dict):
            continue

        tag_id = str(tag.get("id") or "").strip()
        tag_type = str(tag.get("type") or "").strip().lower()

        try:
            offset = int(tag.get("offset"))
            length = int(tag.get("length"))
        except (TypeError, ValueError):
            continue

        if not tag_id or offset < 0 or length <= 0:
            continue

        valid_tags.append(
            {
                "id": tag_id,
                "type": tag_type,
                "offset": offset,
                "length": length,
            }
        )

    valid_tags.sort(key=lambda item: item["offset"])

    parts = []
    cursor = 0

    for tag in valid_tags:
        start = tag["offset"]
        end = min(start + tag["length"], len(text))

        if start < cursor or start >= len(text):
            continue

        parts.append(escape(text[cursor:start]))

        visible_text = text[start:end]

        if tag["type"] == "page":
            url = f"https://www.facebook.com/{tag['id']}"
            parts.append(
                f'<a href="{escape(url)}" target="_blank" rel="noopener">{escape(visible_text)}</a>'
            )
        else:
            parts.append(escape(visible_text))

        cursor = end

    parts.append(escape(text[cursor:]))

    html = "".join(parts).replace("\n", "<br>")
    return mark_safe(html)