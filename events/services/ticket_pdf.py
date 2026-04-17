# events/services/ticket_pdf.py

from __future__ import annotations

import logging
from io import BytesIO
from pathlib import Path

from django.contrib.staticfiles import finders
from django.utils.text import slugify

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas


logger = logging.getLogger("liederweb.events.ticket_pdf")

DEFAULT_TICKET_LOGO_STATIC_PATH = "events/default_ticket_logo.png"
DOMINE_REGULAR_STATIC_PATH = "events/fonts/Domine-Regular.ttf"
DOMINE_BOLD_STATIC_PATH = "events/fonts/Domine-Bold.ttf"
SHOW_DEBUG_SEPARATOR_LINES = False

_FONT_REGISTRY_READY = False
_FONT_NAMES = {
    "regular": "Times-Roman",
    "bold": "Times-Bold",
}


CZECH_MONTHS_GENITIVE = {
    1: "ledna",
    2: "února",
    3: "března",
    4: "dubna",
    5: "května",
    6: "června",
    7: "července",
    8: "srpna",
    9: "září",
    10: "října",
    11: "listopadu",
    12: "prosince",
}


def build_ticket_pdf_filename(event, variant) -> str:
    event_slug = slugify(getattr(event, "slug", "") or getattr(event, "title", "") or "event")
    variant_code = getattr(variant, "code", "ticket")
    return f"vstupenky_{event_slug}_{variant_code}.pdf"


def build_event_ticket_pdf(event, variant, tickets_per_page: int | None = None) -> bytes:
    """
    Vygeneruje jednostránkové A4 PDF s jednou variantou vstupenek.
    Na stránce zopakuje stejnou vstupenku 4x nebo 5x.
    """
    _register_fonts()

    ticket_settings = getattr(event, "ticket_settings", None)
    page_count = tickets_per_page or getattr(ticket_settings, "default_tickets_per_page", None) or 5
    page_count = int(page_count)

    if page_count not in (4, 5):
        raise ValueError("Počet vstupenek na stránku musí být 4 nebo 5.")

    render_data = _build_ticket_render_data(event, variant, ticket_settings=ticket_settings)
    logo_path = _resolve_logo_path(ticket_settings)
    logo_reader = ImageReader(logo_path) if logo_path else None

    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    pdf.setTitle(build_ticket_pdf_filename(event, variant))

    page_width, page_height = A4
    layout = _get_page_layout(page_count, page_width, page_height)

    for index in range(page_count):
        x = layout["page_margin_x"]
        y = (
            page_height
            - layout["page_margin_top"]
            - ((index + 1) * layout["ticket_height"])
            - (index * layout["ticket_gap"])
        )

        _draw_ticket(
            pdf=pdf,
            x=x,
            y=y,
            width=layout["ticket_width"],
            height=layout["ticket_height"],
            data=render_data,
            logo_reader=logo_reader,
            layout=layout,
        )

    pdf.showPage()
    pdf.save()

    return buffer.getvalue()


def _build_ticket_render_data(event, variant, ticket_settings=None) -> dict:
    return {
        "header_text": _clean_text(getattr(ticket_settings, "header_text", None) or "VSTUPENKA"),
        "title": _clean_text(getattr(ticket_settings, "ticket_title", None) or getattr(event, "title", "")),
        "artists_text": _clean_text(
            getattr(ticket_settings, "ticket_artists_text", None) or _build_artists_text_from_event(event)
        ),
        "venue_text": _clean_text(
            getattr(ticket_settings, "ticket_venue_text", None) or getattr(event, "venue", "")
        ),
        "datetime_text": _clean_text(
            getattr(ticket_settings, "ticket_datetime_text", None) or _build_datetime_text_from_event(event)
        ),
        "price_text": _clean_text(
            getattr(variant, "ticket_price_text", None) or _build_price_text_from_variant(variant)
        ),
    }


def _build_artists_text_from_event(event) -> str:
    artists_manager = getattr(event, "artists", None)
    if not artists_manager:
        return ""

    names = []
    for artist in artists_manager.all().order_by("sort_order", "id"):
        name = _clean_text(getattr(artist, "name", ""))
        if name:
            names.append(name)

    return " | ".join(names)


def _build_datetime_text_from_event(event) -> str:
    starts_at = getattr(event, "starts_at", None)
    if not starts_at:
        return ""

    month = CZECH_MONTHS_GENITIVE.get(starts_at.month, str(starts_at.month))
    return f"{starts_at.day}. {month} {starts_at.year} od {starts_at:%H:%M} hod"


def _build_price_text_from_variant(variant) -> str:
    explicit = _clean_text(getattr(variant, "ticket_price_text", ""))
    if explicit:
        return explicit

    price = getattr(variant, "price", None)
    if price is not None:
        price_value = int(price) if float(price).is_integer() else price
        return f"Cena: {price_value} Kč"

    return _clean_text(getattr(variant, "name", ""))


def _resolve_logo_path(ticket_settings) -> str | None:
    # pokud je u settings zvolené vlastní logo, použijeme ho
    if ticket_settings:
        logo_image = getattr(ticket_settings, "logo_image", None)
        if logo_image and getattr(logo_image, "image", None):
            try:
                logo_path = logo_image.image.path
                if logo_path and Path(logo_path).exists():
                    return logo_path
            except Exception:
                logger.warning("Nepodařilo se použít vlastní logo vstupenky.", exc_info=True)

    # jinak fallback na static/events/default_ticket_logo.png
    static_path = finders.find(DEFAULT_TICKET_LOGO_STATIC_PATH)
    if static_path and Path(static_path).exists():
        return static_path

    logger.warning("Výchozí logo vstupenky nebylo nalezeno: %s", DEFAULT_TICKET_LOGO_STATIC_PATH)
    return None


def _get_page_layout(tickets_per_page: int, page_width: float, page_height: float) -> dict:
    compact = tickets_per_page == 5

    page_margin_x = 12 * mm
    page_margin_top = 10 * mm
    page_margin_bottom = 10 * mm
    ticket_gap = 3.5 * mm if compact else 5 * mm

    ticket_width = page_width - (2 * page_margin_x)
    usable_height = page_height - page_margin_top - page_margin_bottom - ((tickets_per_page - 1) * ticket_gap)
    ticket_height = usable_height / tickets_per_page

    return {
        "compact": compact,
        "page_margin_x": page_margin_x,
        "page_margin_top": page_margin_top,
        "ticket_width": ticket_width,
        "ticket_height": ticket_height,
        "ticket_gap": ticket_gap,
        "inner_padding_x": 6 * mm,
        "inner_padding_top": 4.5 * mm if compact else 6 * mm,
        "inner_padding_bottom": 4.0 * mm if compact else 5 * mm,
        "left_ratio": 0.53,
        "logo_width": 48 * mm,
        "logo_offset_x": 2.2 * mm,              # nové: logo lehce doprava
        "title_gap_below_logo": 5.2 * mm,       # nové: větší mezera mezi logem a názvem
        "separator_line_width": 0.35,
        "header_font_size": 20,
        "detail_font_size": 12,
        "title_font_size": 20,
        "artists_font_size": 11,
        "right_header_top_offset": 8.5 * mm,    # bylo 4.5 mm, celý pravý blok níž
        "right_details_gap_below_header": 8.0 * mm,
        "right_line_gap": 4.8 * mm,             # bylo 4.2 mm, nepatrně větší
        "title_to_artists_baseline_gap": 6.5 * mm,  # bylo 7.2 mm, tedy menší mezera
        "artists_line_gap": 4.2 * mm,
    }


def _draw_ticket(pdf, x: float, y: float, width: float, height: float, data: dict, logo_reader, layout: dict) -> None:
    pdf.saveState()

    top_y = y + height
    bottom_y = y

    if SHOW_DEBUG_SEPARATOR_LINES:
        pdf.setLineWidth(layout["separator_line_width"])
        pdf.line(x, top_y, x + width, top_y)

    inner_left = x + layout["inner_padding_x"]
    inner_right = x + width - layout["inner_padding_x"]
    content_top = top_y - layout["inner_padding_top"]
    content_bottom = bottom_y + layout["inner_padding_bottom"]

    left_width = width * layout["left_ratio"]
    right_x = x + left_width
    right_width = inner_right - right_x

    _draw_left_block(
        pdf=pdf,
        x=inner_left,
        content_top=content_top,
        content_bottom=content_bottom,
        max_width=(right_x - inner_left - 4 * mm),
        data=data,
        logo_reader=logo_reader,
        layout=layout,
    )

    _draw_right_block(
        pdf=pdf,
        x=right_x,
        width=right_width,
        content_top=content_top,
        data=data,
        layout=layout,
    )

    pdf.restoreState()


def _draw_left_block(pdf, x: float, content_top: float, content_bottom: float, max_width: float, data: dict, logo_reader, layout: dict) -> None:
    logo_bottom = content_top

    if logo_reader:
        img_w, img_h = logo_reader.getSize()
        logo_ratio = (img_h / img_w) if img_w else 0.54

        logo_width = min(layout["logo_width"], max_width)
        logo_height = logo_width * logo_ratio
        logo_x = x + layout.get("logo_offset_x", 0)
        logo_y = content_top - logo_height

        pdf.drawImage(
            logo_reader,
            logo_x,
            logo_y,
            width=logo_width,
            height=logo_height,
            preserveAspectRatio=True,
            mask="auto",
        )
        logo_bottom = logo_y

    title_text = _truncate_to_width(
        data["title"],
        _font("bold"),
        layout["title_font_size"],
        max_width,
    )

    artists_lines = _wrap_text(
        data["artists_text"],
        font_name=_font("regular"),
        font_size=layout["artists_font_size"],
        max_width=max_width,
        max_lines=2,
    )

    artists_last_baseline = content_bottom + 1.0 * mm
    artists_first_baseline = artists_last_baseline + (
        layout["artists_line_gap"] * max(len(artists_lines) - 1, 0)
    )

    title_baseline = artists_first_baseline + layout["title_to_artists_baseline_gap"]

    max_title_baseline = logo_bottom - layout.get("title_gap_below_logo", 4 * mm)
    if title_baseline > max_title_baseline:
        shift = title_baseline - max_title_baseline
        title_baseline -= shift
        artists_first_baseline -= shift

    pdf.setFont(_font("bold"), layout["title_font_size"])
    pdf.drawString(x, title_baseline, title_text)

    if artists_lines:
        pdf.setFont(_font("regular"), layout["artists_font_size"])
        line_y = artists_first_baseline
        for line in artists_lines:
            pdf.drawString(x, line_y, line)
            line_y -= layout["artists_line_gap"]


def _draw_right_block(pdf, x: float, width: float, content_top: float, data: dict, layout: dict) -> None:
    right_edge = x + width - 1.5 * mm

    header_y = content_top - layout["right_header_top_offset"]

    pdf.setFont(_font("bold"), layout["header_font_size"])
    pdf.drawRightString(right_edge, header_y, data["header_text"])

    current_y = header_y - layout["right_details_gap_below_header"]

    current_y = _draw_right_aligned_labeled_line(
        pdf=pdf,
        right_edge=right_edge,
        baseline_y=current_y,
        label="Místo:",
        value=data["venue_text"],
        label_font=_font("regular"),
        value_font=_font("bold"),
        font_size=layout["detail_font_size"],
        max_width=width - 2 * mm,
    )
    current_y -= layout["right_line_gap"]

    current_y = _draw_right_aligned_labeled_line(
        pdf=pdf,
        right_edge=right_edge,
        baseline_y=current_y,
        label="Datum a čas:",
        value=data["datetime_text"],
        label_font=_font("regular"),
        value_font=_font("bold"),
        font_size=layout["detail_font_size"],
        max_width=width - 2 * mm,
    )
    current_y -= layout["right_line_gap"]

    price_text = data["price_text"]
    if ":" in price_text:
        label, value = price_text.split(":", 1)
        _draw_right_aligned_labeled_line(
            pdf=pdf,
            right_edge=right_edge,
            baseline_y=current_y,
            label=f"{label.strip()}:",
            value=value.strip(),
            label_font=_font("bold"),
            value_font=_font("bold"),
            font_size=layout["detail_font_size"],
            max_width=width - 2 * mm,
        )
    else:
        text = _truncate_to_width(price_text, _font("bold"), layout["detail_font_size"], width - 2 * mm)
        pdf.setFont(_font("bold"), layout["detail_font_size"])
        pdf.drawRightString(right_edge, current_y, text)


def _draw_right_aligned_labeled_line(
    pdf,
    right_edge: float,
    baseline_y: float,
    label: str,
    value: str,
    label_font: str,
    value_font: str,
    font_size: float,
    max_width: float,
) -> float:
    label = _clean_text(label)
    value = _clean_text(value)

    if not value:
        text = _truncate_to_width(label, label_font, font_size, max_width)
        pdf.setFont(label_font, font_size)
        pdf.drawRightString(right_edge, baseline_y, text)
        return baseline_y

    combined = f"{label} {value}"

    if pdfmetrics.stringWidth(combined, value_font, font_size) <= max_width:
        # rychlá cesta, když se to vejde i jako celek
        pass

    label_width = pdfmetrics.stringWidth(label, label_font, font_size)
    space_width = pdfmetrics.stringWidth(" ", label_font, font_size)

    available_for_value = max_width - label_width - space_width
    value = _truncate_to_width(value, value_font, font_size, available_for_value)

    value_width = pdfmetrics.stringWidth(value, value_font, font_size)
    total_width = label_width + space_width + value_width

    start_x = right_edge - total_width

    pdf.setFont(label_font, font_size)
    pdf.drawString(start_x, baseline_y, label)

    pdf.setFont(value_font, font_size)
    pdf.drawString(start_x + label_width + space_width, baseline_y, value)

    return baseline_y

def _draw_centered_labeled_line(
    pdf,
    center_x: float,
    baseline_y: float,
    label: str,
    value: str,
    label_font: str,
    value_font: str,
    font_size: float,
    max_width: float,
) -> float:
    label = _clean_text(label)
    value = _clean_text(value)

    if not value:
        text = _truncate_to_width(label, label_font, font_size, max_width)
        pdf.setFont(label_font, font_size)
        pdf.drawCentredString(center_x, baseline_y, text)
        return baseline_y

    available_value_width = max_width * 0.72
    value = _truncate_to_width(value, value_font, font_size, available_value_width)

    combined_width = (
        pdfmetrics.stringWidth(label, label_font, font_size)
        + pdfmetrics.stringWidth(" ", label_font, font_size)
        + pdfmetrics.stringWidth(value, value_font, font_size)
    )

    if combined_width > max_width:
        value = _truncate_to_width(
            value,
            value_font,
            font_size,
            max_width - pdfmetrics.stringWidth(label, label_font, font_size) - pdfmetrics.stringWidth(" ", label_font, font_size),
        )
        combined_width = (
            pdfmetrics.stringWidth(label, label_font, font_size)
            + pdfmetrics.stringWidth(" ", label_font, font_size)
            + pdfmetrics.stringWidth(value, value_font, font_size)
        )

    start_x = center_x - (combined_width / 2)

    pdf.setFont(label_font, font_size)
    pdf.drawString(start_x, baseline_y, label)

    label_width = pdfmetrics.stringWidth(label, label_font, font_size)
    space_width = pdfmetrics.stringWidth(" ", label_font, font_size)

    pdf.setFont(value_font, font_size)
    pdf.drawString(start_x + label_width + space_width, baseline_y, value)

    return baseline_y


def _wrap_text(text: str, font_name: str, font_size: float, max_width: float, max_lines: int = 2) -> list[str]:
    text = _clean_text(text)
    if not text:
        return []

    raw_lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not raw_lines:
        raw_lines = [text]

    result: list[str] = []

    for raw_line in raw_lines:
        words = raw_line.split()
        if not words:
            continue

        current = words[0]

        for word in words[1:]:
            candidate = f"{current} {word}"
            if pdfmetrics.stringWidth(candidate, font_name, font_size) <= max_width:
                current = candidate
            else:
                result.append(current)
                current = word
                if len(result) >= max_lines:
                    result[-1] = _truncate_to_width(result[-1], font_name, font_size, max_width)
                    return result

        result.append(current)
        if len(result) >= max_lines:
            result[-1] = _truncate_to_width(result[-1], font_name, font_size, max_width)
            return result

    return result[:max_lines]


def _truncate_to_width(text: str, font_name: str, font_size: float, max_width: float) -> str:
    text = _clean_text(text)
    if not text:
        return ""

    if max_width <= 0:
        return ""

    if pdfmetrics.stringWidth(text, font_name, font_size) <= max_width:
        return text

    ellipsis = "…"
    shortened = text

    while shortened:
        shortened = shortened[:-1].rstrip()
        candidate = f"{shortened}{ellipsis}"
        if pdfmetrics.stringWidth(candidate, font_name, font_size) <= max_width:
            return candidate

    return ellipsis


def _clean_text(value) -> str:
    return str(value or "").strip()


def _font(kind: str) -> str:
    return _FONT_NAMES[kind]


def _register_fonts() -> None:
    global _FONT_REGISTRY_READY

    if _FONT_REGISTRY_READY:
        return

    domine_regular_path = finders.find(DOMINE_REGULAR_STATIC_PATH)
    domine_bold_path = finders.find(DOMINE_BOLD_STATIC_PATH)

    if domine_regular_path and domine_bold_path:
        pdfmetrics.registerFont(TTFont("DomineRegular", domine_regular_path))
        pdfmetrics.registerFont(TTFont("DomineBold", domine_bold_path))
        _FONT_NAMES["regular"] = "DomineRegular"
        _FONT_NAMES["bold"] = "DomineBold"
    else:
        logger.warning(
            "Font Domine nebyl nalezen ve static files (%s, %s). Použije se fallback font.",
            DOMINE_REGULAR_STATIC_PATH,
            DOMINE_BOLD_STATIC_PATH,
        )

    _FONT_REGISTRY_READY = True