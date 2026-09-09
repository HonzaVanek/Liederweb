import html
import re

from django.db.models import Max
from django.utils import timezone

from shop.models import ShopLegalDocument



BOLD_RE = re.compile(r"\*\*(?!\s)(.+?)(?<!\s)\*\*")
ITALIC_RE = re.compile(r"(?<!\*)\*(?![\s*])(.+?)(?<![\s*])\*(?!\*)")


def get_current_legal_document(document_type):
    return (
        ShopLegalDocument.objects
        .filter(
            document_type=document_type,
            is_published=True,
            effective_from__lte=timezone.localdate(),
        )
        .order_by(
            "-effective_from",
            "-version",
            "-id",
        )
        .first()
    )


def get_current_legal_document(document_type):
    return (
        ShopLegalDocument.objects
        .filter(
            document_type=document_type,
            is_published=True,
            effective_from__lte=timezone.localdate(),
        )
        .order_by(
            "-effective_from",
            "-version",
            "-id",
        )
        .first()
    )


def get_current_terms_document():
    return get_current_legal_document(ShopLegalDocument.DocumentType.TERMS)


def get_current_privacy_document():
    return get_current_legal_document(ShopLegalDocument.DocumentType.PRIVACY)


def get_next_legal_document_version(document_type):
    max_version = (
        ShopLegalDocument.objects
        .filter(document_type=document_type)
        .aggregate(max_version=Max("version"))
        ["max_version"]
    )

    return (max_version or 0) + 1

def _build_plain_legal_body(body):
    text = (body or "").strip()

    text = BOLD_RE.sub(r"\1", text)
    text = ITALIC_RE.sub(r"\1", text)

    # Např. &nbsp;, &#160;, &#xA0;
    text = html.unescape(text)

    # V TXT nemá nezlomitelná mezera význam.
    text = text.replace("\xa0", " ")

    return text


def build_legal_document_text(document):
    effective_from = document.effective_from.strftime("%d.%m.%Y")

    body = _build_plain_legal_body(document.body)

    return (
        f"{document.title}\n"
        f"Verze {document.version}\n"
        f"Účinné od {effective_from}\n\n"
        f"{body}\n"
    )