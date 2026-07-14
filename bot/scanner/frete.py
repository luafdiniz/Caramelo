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


@dataclass
class SimulationResult:
    """Full result of one orderForms/simulation call for N units."""
    quantity_used: int
    frete: float                  # R$
    prazo: str
    total_produto: float          # after promo discounts (before freight)
    total_descontos: float        # R$ (negative), promo effect
    total_final: float            # total_produto + frete
    total_bruto: float            # sum of listPrices — pre-promo


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


def _extract_totals(data: dict) -> tuple[float, float, float]:
    """Return (produto_com_desconto, desconto, bruto). Reads Sum-of-sellingPrice
    per line item and cross-checks with the top-level 'totals' array.
    """
    items = data.get("items", []) or []
    total_bruto = 0.0
    total_com_desconto = 0.0
    for item in items:
        list_price = float(item.get("listPrice") or item.get("price") or 0) / 100.0
        q = int(item.get("quantity") or 0) or 1
        total_bruto += list_price * q
        pd = item.get("priceDefinition") or {}
        line_total = float(pd.get("total") or 0) / 100.0
        if line_total:
            total_com_desconto += line_total
        else:
            total_com_desconto += float(item.get("sellingPrice") or 0) / 100.0 * q

    # Prefer explicit totals[Discounts] if present — more reliable than
    # inferring from line items when the API splits promos across lines.
    for t in data.get("totals", []) or []:
        if t.get("id") == "Discounts":
            desconto = float(t.get("value") or 0) / 100.0
            return round(total_bruto + desconto, 2), round(desconto, 2), round(total_bruto, 2)

    return round(total_com_desconto, 2), round(total_com_desconto - total_bruto, 2), round(total_bruto, 2)


def _simulate(site_key: str, sku_id: str, quantity: int, seller_id: str,
              cep: Optional[str] = None) -> Optional[SimulationResult]:
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
        if not data.get("items"):
            print(f"frete {site_key}/{sku_id} q={quantity}: empty items in response")
            if attempt < _RETRIES:
                time.sleep(1.0)
                continue
            return None
        frete_val, prazo = _best_sla(data)
        prod_com_desc, desconto, bruto = _extract_totals(data)
        return SimulationResult(
            quantity_used=quantity,
            frete=frete_val,
            prazo=prazo,
            total_produto=prod_com_desc,
            total_descontos=desconto,
            total_final=round(prod_com_desc + frete_val, 2),
            total_bruto=bruto,
        )
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
    return result.frete, result.prazo


def simulate_cart(
    site_key: str,
    sku_id: str,
    quantity: int,
    seller_id: str = "1",
    cep: Optional[str] = None,
) -> Optional[SimulationResult]:
    """Full cart simulation — freight + promotions + per-site overrides."""
    from scanner import frete_overrides
    sim = _simulate(site_key, sku_id, quantity, seller_id, cep=cep)
    if sim is None:
        return None
    return frete_overrides.apply(site_key, sim)


def simulate_curve(
    site_key: str,
    sku_id: str,
    seller_id: str,
    quantities: list[int],
    cep: Optional[str] = None,
) -> list[SimulationResult]:
    """Simulate the cart at each quantity — returns SimulationResult with
    frete + total after promotional discounts. Callers use this to render
    the price/un curve and highlight free-shipping breakpoints."""
    from scanner import frete_overrides  # local import avoids cycle
    qs = sorted({max(int(q), 1) for q in quantities})
    out: list[SimulationResult] = []
    for q in qs:
        sim = _simulate(site_key, sku_id, q, seller_id, cep=cep)
        if sim is None:
            sim = SimulationResult(
                quantity_used=q, frete=0.0, prazo="",
                total_produto=0.0, total_descontos=0.0,
                total_final=0.0, total_bruto=0.0,
            )
        else:
            sim = frete_overrides.apply(site_key, sim)
        out.append(sim)
    return out


def default_grid(qtde_bulk: int, extra: list[int] | None = None) -> list[int]:
    """Grid centered on the natural pack size. [1, bulk] plus any `extras`
    (e.g. 2 for promo isolation, breakpoint for free-freight)."""
    b = max(int(qtde_bulk or 1), 1)
    grid = {1, b}
    for x in extra or []:
        if x and int(x) >= 1:
            grid.add(int(x))
    return sorted(grid)
