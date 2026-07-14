"""Freight estimation via VTEX orderForms/simulation API.

Two entry points:
- `estimate_vtex(site, sku, qtde, seller, cep)` — cheapest delivery SLA for
  a specific quantity.
- `estimate_with_bulk(site, sku, qtde_1, qtde_bulk, seller, cep)` — returns
  freight for both a single unit and a bulk cart so callers can display
  "quanto dilui com N unidades", following the flag that free-shipping
  thresholds might make bulk purchases worthwhile.

Retries once on empty/error responses — GH Actions IPs sometimes get
throttled by the store WAF and the first call comes back with an empty
logisticsInfo. Retry usually resolves.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from dataclasses import dataclass
from typing import Optional

from scanner.scrapers.vtex import HOSTNAMES


_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

_TIMEOUT = 30
_RETRIES = 2


@dataclass
class FreteResult:
    valor: float          # R$
    prazo: str            # e.g. "9bd", "3h", ""
    quantity_used: int


def _cep() -> str:
    return os.environ.get("CEP_ENTREGA", "31140500").strip().replace("-", "")


def _curl_post_json(url: str, body: dict) -> Optional[dict]:
    args = [
        "curl", "-sL", "--max-time", str(_TIMEOUT),
        "-A", _UA,
        "-H", "Content-Type: application/json",
        "-H", "Accept: application/json",
        "-H", "Accept-Language: pt-BR,pt;q=0.9,en;q=0.8",
        "-X", "POST",
        "-d", json.dumps(body),
        url,
    ]
    proc = subprocess.run(
        args, capture_output=True, text=True, timeout=_TIMEOUT + 5,
    )
    if proc.returncode != 0:
        print(f"frete curl exit {proc.returncode}: {proc.stderr[:100]}")
        return None
    if not proc.stdout:
        print("frete curl: empty response")
        return None
    if proc.stdout.startswith("Bad Request") or proc.stdout.startswith("Forbidden"):
        print(f"frete upstream rejected: {proc.stdout[:100]}")
        return None
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        print(f"frete JSON parse fail: {e} — {proc.stdout[:100]}")
        return None


def _best_sla(data: dict) -> tuple[float, str]:
    """Cheapest non-pickup SLA. Returns (price, prazo). (0, '') if none."""
    best_price = None
    best_days = ""
    for li in data.get("logisticsInfo", []) or []:
        for sla in li.get("slas", []) or []:
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


def _simulate(site_key: str, sku_id: str, quantity: int, seller_id: str,
              cep: Optional[str] = None) -> Optional[tuple[float, str]]:
    hostname = HOSTNAMES.get(site_key)
    if not hostname or not sku_id:
        return None

    url = f"https://{hostname}/api/checkout/pub/orderForms/simulation"
    body = {
        "items": [{"id": str(sku_id), "quantity": int(quantity), "seller": str(seller_id)}],
        "country": "BRA",
        "postalCode": cep or _cep(),
    }

    for attempt in range(_RETRIES + 1):
        data = _curl_post_json(url, body)
        if data is None:
            if attempt < _RETRIES:
                time.sleep(1.0)
                continue
            return None
        # Empty items = upstream declined the cart (SKU not deliverable?)
        if not data.get("items"):
            print(f"frete {site_key}/{sku_id} q={quantity}: empty items in response")
            if attempt < _RETRIES:
                time.sleep(1.0)
                continue
            return None
        return _best_sla(data)
    return None


def estimate_vtex(
    site_key: str,
    sku_id: str,
    quantity: int = 1,
    seller_id: str = "1",
    cep: Optional[str] = None,
) -> tuple[float, str]:
    """Backwards-compatible wrapper. Returns (frete_reais, prazo_bd)."""
    result = _simulate(site_key, sku_id, quantity, seller_id, cep=cep)
    if result is None:
        return 0.0, ""
    return result


def estimate_with_bulk(
    site_key: str,
    sku_id: str,
    seller_id: str,
    qtde_bulk: int,
    cep: Optional[str] = None,
) -> tuple[FreteResult, FreteResult]:
    """Return (frete_1un, frete_bulk). Cheap two-point check."""
    one = _simulate(site_key, sku_id, 1, seller_id, cep=cep) or (0.0, "")
    bulk = _simulate(site_key, sku_id, max(qtde_bulk, 1), seller_id, cep=cep) or (0.0, "")
    return (
        FreteResult(valor=one[0], prazo=one[1], quantity_used=1),
        FreteResult(valor=bulk[0], prazo=bulk[1], quantity_used=max(qtde_bulk, 1)),
    )


def estimate_curve(
    site_key: str,
    sku_id: str,
    seller_id: str,
    quantities: list[int],
    cep: Optional[str] = None,
) -> list[FreteResult]:
    """Simulate freight at several cart sizes so callers can render a curve
    and highlight the break-point where freight zeroes (or dilutes below
    some threshold). Deduped & sorted, guaranteed ≥1.
    """
    qs = sorted({max(int(q), 1) for q in quantities})
    out: list[FreteResult] = []
    for q in qs:
        sim = _simulate(site_key, sku_id, q, seller_id, cep=cep) or (0.0, "")
        out.append(FreteResult(valor=sim[0], prazo=sim[1], quantity_used=q))
    return out


def default_grid(qtde_bulk: int) -> list[int]:
    """Sensible 4-point grid centered on the scanner's bulk_qtde.
    [1, bulk/4, bulk, bulk*2] with dedup and floor of 1."""
    b = max(int(qtde_bulk or 1), 1)
    return sorted({1, max(b // 4, 1), b, b * 2})
