from pathlib import Path

from django.db import transaction

from shop.models import (
    AlbumTrack,
    DigitalDownloadGrant,
    Order,
    ProductVariant,
)


class DigitalDownloadGrantError(Exception):
    pass


def _basename(filename):
    """
    Vrátí pouze název souboru bez případné cesty.
    Funguje i pro názvy obsahující Windows backslashe.
    """
    if not filename:
        return ""

    normalized = str(filename).replace("\\", "/")
    return Path(normalized).name


def _create_track_grant(
    *,
    order,
    order_item,
    track,
):
    """
    Vytvoří nárok ke stažení jedné celé MP3.
    """
    if not track.full_audio:
        raise DigitalDownloadGrantError(
            f'Stopa "{track.title}" nemá plnou MP3.'
        )

    download_filename = (
        _basename(track.original_filename)
        or _basename(track.full_audio.name)
        or f"{track.title}.mp3"
    )

    grant, created = (
        DigitalDownloadGrant.objects.get_or_create(
            order=order,
            file_type=DigitalDownloadGrant.FileType.TRACK,
            storage_name=track.full_audio.name,
            defaults={
                "order_item": order_item,
                "product_name": order_item.product_name,
                "display_title": track.title,
                "download_filename": download_filename,
                "disc_number": track.disc_number,
                "track_number": track.track_number,
            },
        )
    )

    return grant, created


def _create_booklet_grant(
    *,
    order,
    order_item,
    product,
):
    """
    Vytvoří nárok na booklet celého digitálního alba.

    Pokud produkt booklet nemá, nic se nevytvoří.
    """
    if not product.digital_booklet:
        return None, False

    download_filename = (
        _basename(
            product.digital_booklet_original_filename
        )
        or _basename(product.digital_booklet.name)
        or "booklet.pdf"
    )

    grant, created = (
        DigitalDownloadGrant.objects.get_or_create(
            order=order,
            file_type=DigitalDownloadGrant.FileType.BOOKLET,
            storage_name=product.digital_booklet.name,
            defaults={
                "order_item": order_item,
                "product_name": order_item.product_name,
                "display_title": "Booklet",
                "download_filename": download_filename,
                "disc_number": None,
                "track_number": None,
            },
        )
    )

    return grant, created


@transaction.atomic
def grant_digital_downloads(order):
    """
    Vytvoří download granty pro zaplacenou objednávku.

    Jednotlivá MP3:
        varianta napojená na AlbumTrack
        -> jedna MP3

    Celé digitální album:
        is_full_album_download=True
        -> všechny MP3 produktu
        -> booklet, pokud existuje

    Funkce je idempotentní:
    opakované zavolání nevytvoří duplicity.

    Vrací počet nově vytvořených grantů.
    """

    if order.payment_status != Order.PaymentStatus.PAID:
        return 0

    created_count = 0

    order_items = (
        order.items
        .select_related(
            "variant",
            "variant__product",
        )
        .all()
    )

    for order_item in order_items:

        # Fyzické produkty a vstupenky nás nezajímají.
        if (
            order_item.fulfilment_type
            != ProductVariant.FulfilmentType.DIGITAL
        ):
            continue

        variant = order_item.variant

        if variant is None:
            raise DigitalDownloadGrantError(
                (
                    "Digitální položka objednávky "
                    f'"{order_item.product_name} – '
                    f'{order_item.variant_name}" '
                    "už nemá přiřazenou variantu produktu."
                )
            )

        product = variant.product

        # -------------------------------------------------
        # CELÉ DIGITÁLNÍ ALBUM
        # -------------------------------------------------

        if variant.is_full_album_download:
            tracks = (
                product.tracks
                .all()
                .order_by(
                    "disc_number",
                    "track_number",
                    "id",
                )
            )

            if not tracks.exists():
                raise DigitalDownloadGrantError(
                    (
                        f'Produkt "{product.name}" je označen '
                        "jako celé digitální album, "
                        "ale nemá žádné stopy."
                    )
                )

            for track in tracks:
                _, created = _create_track_grant(
                    order=order,
                    order_item=order_item,
                    track=track,
                )

                if created:
                    created_count += 1

            _, created = _create_booklet_grant(
                order=order,
                order_item=order_item,
                product=product,
            )

            if created:
                created_count += 1

            continue

        # -------------------------------------------------
        # JEDNOTLIVÁ MP3
        # -------------------------------------------------

        track = (
            AlbumTrack.objects
            .filter(
                purchase_variant_id=variant.id,
            )
            .first()
        )

        if track is None:
            raise DigitalDownloadGrantError(
                (
                    f'Digitální varianta "{variant.name}" '
                    "není ani celé album, ani není "
                    "přiřazená k žádné stopě."
                )
            )

        _, created = _create_track_grant(
            order=order,
            order_item=order_item,
            track=track,
        )

        if created:
            created_count += 1

    return created_count