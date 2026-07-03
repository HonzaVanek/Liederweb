import re

from django import template
from django.utils.html import conditional_escape
from django.utils.safestring import mark_safe

from core.templatetags.czech_typography import cz_nbsp


register = template.Library()

BOLD_RE = re.compile(r"\*\*(?!\s)(.+?)(?<!\s)\*\*")
ITALIC_RE = re.compile(r"(?<!\*)\*(?![\s*])(.+?)(?<![\s*])\*(?!\*)")
LIST_ITEM_RE = re.compile(r"^\s*[-*]\s+(.+?)\s*$")


def _format_inline(text):
    text = BOLD_RE.sub(r"<strong>\1</strong>", text)
    text = ITALIC_RE.sub(r"<em>\1</em>", text)
    return text


@register.filter(needs_autoescape=True)
def content_richtext(value, autoescape=True):
    """
    Bezpečný jednoduchý formátovač pro blogposty.

    Podporuje:
    - odstavce
    - jedno odřádkování jako <br>
    - prázdný řádek jako nový odstavec
    - tučně přes **text**
    - kurzívu přes *text*
    - odrážky přes řádky začínající "- "
    - automatické české nezlomitelné mezery
    - ruční &nbsp;, &#160;, &#xA0;

    Ostatní HTML se escapuje.
    """
    if not value:
        return ""

    text = cz_nbsp(str(value))

    if autoescape:
        text = conditional_escape(text)

    lines = str(text).splitlines()

    html_blocks = []
    paragraph_lines = []
    list_items = []

    def flush_paragraph():
        nonlocal paragraph_lines

        if not paragraph_lines:
            return

        paragraph = "\n".join(paragraph_lines).strip()

        if paragraph:
            paragraph = _format_inline(paragraph)
            paragraph = paragraph.replace("\n", "<br>")
            html_blocks.append(f"<p>{paragraph}</p>")

        paragraph_lines = []

    def flush_list():
        nonlocal list_items

        if not list_items:
            return

        items_html = "".join(
            f"<li>{_format_inline(item)}</li>"
            for item in list_items
        )
        html_blocks.append(f"<ul>{items_html}</ul>")

        list_items = []

    for line in lines:
        stripped = line.strip()

        if not stripped:
            flush_paragraph()
            flush_list()
            continue

        list_match = LIST_ITEM_RE.match(line)

        if list_match:
            flush_paragraph()
            list_items.append(list_match.group(1))
        else:
            flush_list()
            paragraph_lines.append(line)

    flush_paragraph()
    flush_list()

    return mark_safe("\n".join(html_blocks))