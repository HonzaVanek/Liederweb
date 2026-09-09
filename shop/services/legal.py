from django.db.models import Max
from django.utils import timezone

from shop.models import ShopLegalDocument


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
    return get_current_legal_document(
        ShopLegalDocument.DocumentType.TERMS
    )


def get_current_privacy_document():
    return get_current_legal_document(
        ShopLegalDocument.DocumentType.PRIVACY
    )


def get_next_legal_document_version(document_type):
    max_version = (
        ShopLegalDocument.objects
        .filter(document_type=document_type)
        .aggregate(max_version=Max("version"))
        ["max_version"]
    )

    return (max_version or 0) + 1


def build_legal_document_text(document):
    effective_from = document.effective_from.strftime(
        "%d.%m.%Y"
    )

    return (
        f"{document.title}\n"
        f"Verze {document.version}\n"
        f"Účinné od {effective_from}\n\n"
        f"{document.body.strip()}\n"
    )