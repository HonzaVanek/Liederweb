from django import template


import re

from django.template.defaultfilters import linebreaks
from django.utils.html import conditional_escape
from django.utils.safestring import mark_safe

from core.models import Partner

register = template.Library()


@register.inclusion_tag("core/includes/partners_section.html", takes_context=True)
def render_partners_section(context):
    request = context.get("request")

    partners = (
        Partner.objects
        .filter(is_active=True)
        .select_related("logo")
        .order_by("sort_order", "name", "id")
    )

    return {
        "request": request,
        "partners": partners,
    }

ITALIC_RE = re.compile(r"\*(?!\s)(.+?)(?<!\s)\*")


@register.filter(needs_autoescape=True)
def event_richtext(value, autoescape=True):
    """
    Bezpečný jednoduchý formátovač pro veřejné texty koncertu.

    Povolí:
    - odstavce a odřádkování
    - kurzívu přes <em>...</em>
    - kurzívu přes *...*

    Ostatní HTML zůstane escapované.
    """
    if not value:
        return ""

    text = str(conditional_escape(value)) if autoescape else str(value)

    text = (
        text
        .replace("&lt;em&gt;", "<em>")
        .replace("&lt;/em&gt;", "</em>")
        .replace("&lt;i&gt;", "<em>")
        .replace("&lt;/i&gt;", "</em>")
    )

    text = ITALIC_RE.sub(r"<em>\1</em>", text)

    return mark_safe(linebreaks(text, autoescape=False))