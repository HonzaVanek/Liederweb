from decimal import Decimal
from io import StringIO, BytesIO
from urllib.parse import quote

import segno


def clean_spd_text(value: str, max_length: int = 60) -> str:
    value = (value or "").strip()
    value = value.replace("*", " ").replace("\n", " ")
    value = " ".join(value.split())
    return value[:max_length]


def build_spd_payload(
    *,
    iban: str,
    amount: Decimal,
    message: str,
    variable_symbol: str = "",
    currency: str = "CZK",
) -> str:
    parts = [
        "SPD",
        "1.0",
        f"ACC:{iban.replace(' ', '')}",
        f"AM:{amount:.2f}",
        f"CC:{currency}",
    ]

    message = clean_spd_text(message)
    if message:
        parts.append(f"MSG:{quote(message, safe=' /.-_')}")

    if variable_symbol:
        parts.append(f"X-VS:{variable_symbol}")

    return "*".join(parts) + "*"


def make_qr_svg(payload: str) -> str:
    qr = segno.make(payload, error="m")

    buffer = BytesIO()
    qr.save(
        buffer,
        kind="svg",
        scale=5,
        xmldecl=False,
        svgns=True,
        border=2,
    )

    return buffer.getvalue().decode("utf-8")