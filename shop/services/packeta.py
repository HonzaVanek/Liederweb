import json
import logging
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings


logger = logging.getLogger(__name__)


PACKETA_VALIDATE_URL = "https://widget.packeta.com/v6/pps/api/widget/v1/validate"


class PacketaValidationError(Exception):
    pass


def validate_packeta_pickup_point(point_id):
    api_key = getattr(
        settings,
        "PACKETA_API_KEY",
        "",
    ).strip()

    if not api_key:
        raise PacketaValidationError(
            "Zásilkovna není správně nakonfigurovaná. Chybí API key."
        )

    point_id = str(point_id or "").strip()

    if not point_id:
        raise PacketaValidationError(
            "Vyberte výdejní místo Zásilkovny."
        )

    payload = {
        "apiKey": api_key,
        "point": {
            "id": point_id,
        },
        # Musí odpovídat omezením použitým ve widgetu.
        "options": {
            "country": "cz",
            "vendors": [
                {
                    "country": "cz",
                },
                {
                    "country": "cz",
                    "group": "zbox",
                },
            ],
        },
    }

    request = Request(
        PACKETA_VALIDATE_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-Language": "cs",
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=5) as response:
            result = json.loads(
                response.read().decode("utf-8")
            )

    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        logger.exception(
            "Nepodařilo se ověřit výdejní místo Zásilkovny."
        )

        raise PacketaValidationError(
            "Výdejní místo se teď nepodařilo ověřit. "
            "Zkuste ho prosím vybrat znovu."
        ) from exc

    if not result.get("isValid"):
        logger.warning(
            "Packeta odmítla výdejní místo %s: %s",
            point_id,
            result.get("errors"),
        )

        raise PacketaValidationError(
            "Vybrané výdejní místo už není dostupné. "
            "Vyberte prosím jiné."
        )

    point = result.get("point") or {}
    address = point.get("address") or {}

    name = (point.get("name") or "").strip()
    street = (address.get("street") or "").strip()
    city = (address.get("city") or "").strip()
    postal_code = (address.get("zip") or "").strip()
    country = (address.get("country") or "").strip().upper()
    group = (point.get("group") or "").strip()


    if group == "zbox":
        display_parts = ["Z-BOX"]

        if city:
            display_parts.append(city)

        display_name = " ".join(display_parts)

        if street:
            display_name += f", {street}"

    else:
        display_name = name

        # Kdyby validační endpoint vrátil jen velmi obecný název,
        # doplníme bezpečně adresu.
        if street and street not in display_name:
            if city:
                display_name += f" – {city}, {street}"
            else:
                display_name += f" – {street}"


    return {
        "id": point_id,
        "name": display_name,
        "street": street,
        "city": city,
        "postal_code": postal_code,
        "country": country,
    }