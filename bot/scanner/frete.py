"""Freight estimation via VTEX orderForms/simulation API.

Given a SKU + seller + quantity + CEP, returns the cheapest delivery
SLA (postal service, courier, etc.). Free-shipping thresholds are
respected automatically — if the cart total is above the store minimum,
the API returns R$ 0.00 in the winning SLA.

Uses subprocess+curl for the same TLS-fingerprint reason as the
catalog scraper (see scrapers/vtex.py docstring).
"""

from __future__ import annotations

import json
import os
import subprocess
from typing import Optional

from scanner.scrapers.vtex import HOSTNAMES


_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

_TIMEOUT = 20


def _cep() -> str:
    return os.environ.get("CEP_ENTREGA", "31140500").strip().replace("-", "")


def _curl_post_json(url: str, body: dict) -> Optional[dict]:
    args = [
        "curl", "-sL", "--max-time", str(_TIMEOUT),
        "-A", _UA,
        "-H", "Content-Type: application/json",
        "-H", "Accept: application/json",
        "-X", "POST",
        "-d", json.dumps(body),
        url,
    ]
    proc = subprocess.run(
        args, capture_output=True, text=True, timeout=_TIMEOUT + 5,
    )
    if proc.returncode != 0:
        return None
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return None


def estimate_vtex(
    site_key: str,
    sku_id: str,
    quantity: int = 1,
    seller_id: str = "1",
    cep: Optional[str] = None,
) -> tuple[float, str]:
    """Return (cheapest_frete_reais, prazo_dias_bd).

    Returns (0.0, "") on any error — caller should degrade to pure preco.
    """
    hostname = HOSTNAMES.get(site_key)
    if not hostname or not sku_id:
        return 0.0, ""

    url = f"https://{hostname}/api/checkout/pub/orderForms/simulation"
    body = {
        "items": [{"id": str(sku_id), "quantity": int(quantity), "seller": str(seller_id)}],
        "country": "BRA",
        "postalCode": cep or _cep(),
    }
    data = _curl_post_json(url, body)
    if not data:
        return 0.0, ""

    best_price = None
    best_days = ""
    for li in data.get("logisticsInfo", []) or []:
        for sla in li.get("slas", []) or []:
            # Skip pickup points — we want delivery
            if sla.get("pickupPointId"):
                continue
            price_cents = sla.get("price")
            if price_cents is None:
                continue
            price = float(price_cents) / 100.0
            if best_price is None or price < best_price:
                best_price = price
                best_days = str(sla.get("shippingEstimate", ""))

    if best_price is None:
        return 0.0, ""
    return best_price, best_days
