from __future__ import annotations

import logging
from io import BytesIO
from xml.sax.saxutils import escape

from django.contrib.staticfiles import finders
from django.utils import timezone

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Image,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from core.utils.payments import (
    build_spd_payload,
    make_qr_png,
)


logger = logging.getLogger("liederweb.shop.invoice_pdf")

DOMINE_REGULAR_STATIC_PATH = "events/fonts/Domine-Regular.ttf"
DOMINE_BOLD_STATIC_PATH = "events/fonts/Domine-Bold.ttf"

_FONT_READY = False
_FONT_REGULAR = "Times-Roman"
_FONT_BOLD = "Times-Bold"


def build_invoice_pdf_filename(invoice) -> str:
    number = (invoice.number or "faktura").replace("/", "-")
    return f"faktura_{number}.pdf"


def build_invoice_pdf(invoice) -> bytes:
    _register_fonts()

    order = invoice.order
    items = list(order.items.all())

    buffer = BytesIO()

    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=16 * mm,
        leftMargin=16 * mm,
        topMargin=15 * mm,
        bottomMargin=18 * mm,
        title=invoice.number or "Faktura",
        author=invoice.seller_name,
    )

    normal = ParagraphStyle(
        "InvoiceNormal",
        fontName=_FONT_REGULAR,
        fontSize=9.5,
        leading=13,
        textColor=colors.HexColor("#202020"),
    )

    small = ParagraphStyle(
        "InvoiceSmall",
        parent=normal,
        fontSize=8,
        leading=10,
        textColor=colors.HexColor("#555555"),
    )

    heading = ParagraphStyle(
        "InvoiceHeading",
        parent=normal,
        fontName=_FONT_BOLD,
        fontSize=20,
        leading=24,
    )

    section_heading = ParagraphStyle(
        "InvoiceSectionHeading",
        parent=normal,
        fontName=_FONT_BOLD,
        fontSize=11,
        leading=14,
        spaceAfter=5,
    )

    right = ParagraphStyle(
        "InvoiceRight",
        parent=normal,
        alignment=TA_RIGHT,
    )

    story = []

    title_text = "FAKTURA"

    if invoice.status == invoice.Status.CANCELLED:
        title_text += " - STORNOVÁNO"

    header = Table(
        [
            [
                Paragraph(title_text, heading),
                Paragraph(
                    (
                        f"<b>{escape(invoice.number or '')}</b><br/>"
                        f"Objednávka: {escape(order.number or '')}"
                    ),
                    right,
                ),
            ]
        ],
        colWidths=[105 * mm, 72 * mm],
    )

    header.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )

    story.append(header)
    story.append(Spacer(1, 9 * mm))

    seller_text = (
        f"<b>{escape(invoice.seller_name)}</b><br/>"
        f"{_multiline(invoice.seller_address)}<br/>"
        f"IČO: {escape(invoice.seller_company_id)}"
    )

    if invoice.seller_vat_id:
        seller_text += (
            f"<br/>DIČ: {escape(invoice.seller_vat_id)}"
        )

    customer_text = (
        f"<b>{escape(invoice.customer_name)}</b><br/>"
        f"{_multiline(invoice.customer_address)}"
    )

    if invoice.customer_email:
        customer_text += (
            f"<br/>{escape(invoice.customer_email)}"
        )

    parties = Table(
        [
            [
                Paragraph(
                    "<b>Dodavatel</b><br/><br/>" + seller_text,
                    normal,
                ),
                Paragraph(
                    "<b>Odběratel</b><br/><br/>" + customer_text,
                    normal,
                ),
            ]
        ],
        colWidths=[88 * mm, 89 * mm],
    )

    parties.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.grey),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.lightgrey),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )

    story.append(parties)
    story.append(Spacer(1, 7 * mm))

    issued_date = timezone.localtime(
        invoice.issued_at
    ).date()

    metadata = Table(
        [
            [
                Paragraph("<b>Datum vystavení</b>", normal),
                Paragraph(issued_date.strftime("%d.%m.%Y"), normal),
                Paragraph("<b>Datum splatnosti</b>", normal),
                Paragraph(
                    invoice.due_date.strftime("%d.%m.%Y"),
                    normal,
                ),
            ],
            [
                Paragraph("<b>Způsob platby</b>", normal),
                Paragraph("Bankovní převod", normal),
                Paragraph("<b>Variabilní symbol</b>", normal),
                Paragraph(
                    escape(invoice.variable_symbol),
                    normal,
                ),
            ],
        ],
        colWidths=[
            38 * mm,
            48 * mm,
            42 * mm,
            49 * mm,
        ],
    )

    metadata.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.lightgrey),
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f1f1f1")),
                ("BACKGROUND", (2, 0), (2, -1), colors.HexColor("#f1f1f1")),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )

    story.append(metadata)
    story.append(Spacer(1, 8 * mm))
    story.append(Paragraph("Položky faktury", section_heading))

    item_rows = [
        [
            Paragraph("<b>Položka</b>", normal),
            Paragraph("<b>Množství</b>", right),
            Paragraph("<b>Cena za kus</b>", right),
            Paragraph("<b>Celkem</b>", right),
        ]
    ]

    for item in items:
        item_name = escape(item.product_name)

        if item.variant_name:
            item_name += (
                f"<br/><font size='8'>"
                f"{escape(item.variant_name)}</font>"
            )

        item_rows.append(
            [
                Paragraph(item_name, normal),
                Paragraph(str(item.quantity), right),
                Paragraph(
                    _format_money(item.unit_price),
                    right,
                ),
                Paragraph(
                    _format_money(item.line_total),
                    right,
                ),
            ]
        )

    items_table = Table(
        item_rows,
        repeatRows=1,
        colWidths=[
            92 * mm,
            23 * mm,
            31 * mm,
            31 * mm,
        ],
    )

    items_table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e9e9e9")),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.lightgrey),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )

    story.append(items_table)
    story.append(Spacer(1, 5 * mm))

    totals = Table(
        [
            [
                Paragraph("Mezisoučet", normal),
                Paragraph(
                    _format_money(invoice.subtotal),
                    right,
                ),
            ],
            [
                Paragraph("Doprava", normal),
                Paragraph(
                    _format_money(invoice.shipping_price),
                    right,
                ),
            ],
            [
                Paragraph("<b>Celkem k úhradě</b>", normal),
                Paragraph(
                    f"<b>{_format_money(invoice.total)}</b>",
                    right,
                ),
            ],
        ],
        colWidths=[45 * mm, 38 * mm],
        hAlign="RIGHT",
    )

    totals.setStyle(
        TableStyle(
            [
                ("LINEABOVE", (0, -1), (-1, -1), 1.2, colors.black),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )

    story.append(totals)
    story.append(Spacer(1, 9 * mm))

    payment_payload = build_spd_payload(
        iban=invoice.iban,
        amount=invoice.total,
        message=f"Objednavka {order.number}",
        variable_symbol=invoice.variable_symbol,
        currency=invoice.currency,
    )

    qr_image = Image(
        BytesIO(make_qr_png(payment_payload)),
        width=37 * mm,
        height=37 * mm,
    )

    payment_text = Paragraph(
        (
            "<b>Platební údaje</b><br/><br/>"
            f"Číslo účtu: {escape(invoice.bank_account)}<br/>"
            f"IBAN: {escape(invoice.iban)}<br/>"
            f"Variabilní symbol: "
            f"<b>{escape(invoice.variable_symbol)}</b><br/>"
            f"Částka: <b>{_format_money(invoice.total)}</b>"
        ),
        normal,
    )

    payment_table = Table(
        [[payment_text, qr_image]],
        colWidths=[135 * mm, 42 * mm],
    )

    payment_table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.grey),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )

    story.append(payment_table)
    story.append(Spacer(1, 6 * mm))

    if not invoice.seller_is_vat_payer:
        story.append(
            Paragraph(
                "Dodavatel není plátcem DPH.",
                section_heading,
            )
        )

    story.append(
        Paragraph(
            "Doklad byl vystaven elektronicky.",
            small,
        )
    )

    document.build(
        story,
        onFirstPage=_draw_footer,
        onLaterPages=_draw_footer,
    )

    return buffer.getvalue()


def _draw_footer(pdf, document):
    pdf.saveState()
    pdf.setFont(_FONT_REGULAR, 7.5)
    pdf.setFillColor(colors.HexColor("#666666"))
    pdf.drawCentredString(
        A4[0] / 2,
        8 * mm,
        f"Strana {document.page}",
    )
    pdf.restoreState()


def _format_money(value) -> str:
    formatted = f"{value:,.2f}"
    formatted = formatted.replace(",", "X")
    formatted = formatted.replace(".", ",")
    formatted = formatted.replace("X", " ")
    return f"{formatted} Kč"


def _multiline(value) -> str:
    return "<br/>".join(
        escape(line)
        for line in str(value or "").splitlines()
        if line.strip()
    )


def _register_fonts():
    global _FONT_READY
    global _FONT_REGULAR
    global _FONT_BOLD

    if _FONT_READY:
        return

    regular_path = finders.find(
        DOMINE_REGULAR_STATIC_PATH
    )
    bold_path = finders.find(
        DOMINE_BOLD_STATIC_PATH
    )

    if regular_path and bold_path:
        pdfmetrics.registerFont(
            TTFont("ShopDomineRegular", regular_path)
        )
        pdfmetrics.registerFont(
            TTFont("ShopDomineBold", bold_path)
        )

        _FONT_REGULAR = "ShopDomineRegular"
        _FONT_BOLD = "ShopDomineBold"
    else:
        logger.warning(
            "Fonty pro fakturu nebyly nalezeny."
        )

    _FONT_READY = True