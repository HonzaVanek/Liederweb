from shop.models import ProductVariant


def sync_track_purchase_variant(
    track,
    *,
    price,
):
    variant = track.purchase_variant

    if price is None:
        if variant and variant.is_active:
            variant.is_active = False
            variant.save(
                update_fields=["is_active"]
            )

        return

    variant_name = (
        f"MP3 – CD {track.disc_number} / "
        f"{track.track_number:02d} – {track.title}"
    )

    sort_order = (
        track.disc_number * 100
        + track.track_number
    )

    if variant is None:
        variant = ProductVariant.objects.create(
            product=track.product,
            name=variant_name,
            sku=f"MP3-{track.product_id}-{track.pk}",
            fulfilment_type=(
                ProductVariant.FulfilmentType.DIGITAL
            ),
            price=price,
            is_full_album_download=False,
            track_stock=False,
            stock_quantity=0,
            is_active=track.is_active,
            sort_order=sort_order,
        )

        track.purchase_variant = variant
        track.save(
            update_fields=["purchase_variant"]
        )

        return

    variant.name = variant_name
    variant.fulfilment_type = (
        ProductVariant.FulfilmentType.DIGITAL
    )
    variant.price = price
    variant.is_full_album_download = False
    variant.is_active = track.is_active
    variant.track_stock = False
    variant.stock_quantity = 0
    variant.sort_order = sort_order

    variant.save(
        update_fields=[
            "name",
            "fulfilment_type",
            "price",
            "is_full_album_download",
            "is_active",
            "track_stock",
            "stock_quantity",
            "sort_order",
        ]
    )