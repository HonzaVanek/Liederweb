import logging
import re
from pathlib import Path
from uuid import uuid4

import qrcode
from PIL import Image, UnidentifiedImageError

from django.conf import settings
from django.contrib import messages
from django.shortcuts import render
from django.utils import timezone

from core.decorators import staff_required


logger = logging.getLogger(__name__)

HEX_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")


def _get_int_from_post(request, name, default, minimum, maximum):
    try:
        value = int(request.POST.get(name, default))
    except (TypeError, ValueError):
        return default

    return max(minimum, min(value, maximum))


def _get_color_from_post(request, name, default):
    value = request.POST.get(name, default)

    if not value or not HEX_COLOR_RE.match(value):
        return default

    return value


def _cleanup_old_qr_codes(save_dir, keep_last=20):
    try:
        files = sorted(
            save_dir.glob("qr_code_*.png"),
            key=lambda path: path.stat().st_mtime,
        )

        for old_file in files[:-keep_last]:
            old_file.unlink(missing_ok=True)

    except Exception:
        logger.exception("Nepodařilo se smazat starší QR kódy.")


@staff_required
def generate_qr(request):
    qr_image_url = None
    data = ""

    if request.method == "POST":
        data = request.POST.get("qr_text", "").strip()

        if not data:
            messages.error(request, "Zadej text nebo URL pro QR kód.")
            return render(request, "core/generate_qr.html", {"data": data})

        # Rozumný limit, aby někdo omylem nevložil obří text.
        if len(data) > 4000:
            messages.error(request, "Text pro QR kód je příliš dlouhý.")
            return render(request, "core/generate_qr.html", {"data": data})

        qr_size = _get_int_from_post(
            request,
            name="qr_size",
            default=10,
            minimum=1,
            maximum=20,
        )

        qr_border = _get_int_from_post(
            request,
            name="qr_border",
            default=4,
            minimum=0,
            maximum=10,
        )

        qr_color = _get_color_from_post(
            request,
            name="qr_color",
            default="#000000",
        )

        qr_background_color = _get_color_from_post(
            request,
            name="qr_background_color",
            default="#ffffff",
        )

        use_custom_logo = request.POST.get("use_custom_logo") == "on"
        custom_logo_file = request.FILES.get("custom_logo_file")

        logo = None

        if use_custom_logo and custom_logo_file:
            if custom_logo_file.size > 3 * 1024 * 1024:
                messages.warning(
                    request,
                    "Logo je moc velké. QR kód jsem vygeneroval bez něj.",
                )
            else:
                try:
                    logo = Image.open(custom_logo_file).convert("RGBA")
                except (UnidentifiedImageError, OSError):
                    logger.exception("Nepodařilo se otevřít logo pro QR kód.")
                    messages.warning(
                        request,
                        "Logo se nepodařilo načíst. QR kód jsem vygeneroval bez něj.",
                    )
                    logo = None

        qr = qrcode.QRCode(
            version=None,
            box_size=qr_size,
            border=qr_border,
            error_correction=qrcode.constants.ERROR_CORRECT_H,
        )
        qr.add_data(data)
        qr.make(fit=True)

        image = qr.make_image(
            fill_color=qr_color,
            back_color=qr_background_color,
        ).convert("RGBA")

        if logo:
            qr_w, qr_h = image.size

            # Logo max. 20 % šířky QR kódu.
            # Víc už je zbytečně rizikové pro čitelnost.
            logo_target_width = int(qr_w * 0.20)
            ratio = logo_target_width / float(logo.size[0])
            logo_target_height = int(float(logo.size[1]) * ratio)

            logo = logo.resize(
                (logo_target_width, logo_target_height),
                Image.LANCZOS,
            )

            position = (
                (qr_w - logo_target_width) // 2,
                (qr_h - logo_target_height) // 2,
            )

            image.alpha_composite(logo, dest=position)

        save_dir = Path(settings.MEDIA_ROOT) / "qr_codes"
        save_dir.mkdir(parents=True, exist_ok=True)

        filename = (
            f"qr_code_"
            f"{timezone.now().strftime('%Y%m%d%H%M%S')}_"
            f"{uuid4().hex[:8]}.png"
        )

        full_path = save_dir / filename
        image.save(full_path, format="PNG")

        qr_image_url = f"{settings.MEDIA_URL.rstrip('/')}/qr_codes/{filename}"

        _cleanup_old_qr_codes(save_dir, keep_last=20)

        messages.success(request, "QR kód byl vygenerován.")

    return render(
        request,
        "core/generate_qr.html",
        {
            "qr_image_url": qr_image_url,
            "data": data,
        },
    )