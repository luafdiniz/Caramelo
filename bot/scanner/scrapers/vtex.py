"""VTEX Commerce API scraper.

One function serves all VTEX-based sites (Supernosso, Apoio Entrega, Santo
Antônio). Uses `curl` via subprocess because these sites gate the API behind
TLS fingerprinting — Python's `requests` (urllib3) is detected and returns
`400 Bad Request! Scripts are not allowed!`. curl passes the check.
"""

from __future__ import annotations

import json
import subprocess
from urllib.parse import quote

from scanner.extractor import (
    extract_qtde_unidades,
    brand_confirmed_in,
    preco_por_unidade,
)
from scanner.scrapers.base import ProductResult


HOSTNAMES = {
    "supernosso": "www.supernosso.com",
    "apoio": "www.apoioentrega.com",
    "santoantonio": "www.lojasantoantonio.com.br",
}

_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

_TIMEOUT = 15
_MAX_RESULTS = 10


def _curl_get_json(url: str) -> list | dict:
    """GET a URL via subprocess curl. Returns parsed JSON or raises."""
    args = [
        "curl", "-sL", "--max-time", str(_TIMEOUT),
        "-A", _UA,
        "-H", "Accept: application/json",
        "-H", "Accept-Language: pt-BR,pt;q=0.9,en;q=0.8",
        url,
    ]
    proc = subprocess.run(
        args, capture_output=True, text=True, timeout=_TIMEOUT + 5,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"curl exit {proc.returncode}: {proc.stderr[:200]}")
    body = proc.stdout
    if body.startswith("Bad Request") or body.startswith("Forbidden"):
        raise RuntimeError(f"upstream rejected: {body[:100]}")
    return json.loads(body)


def _extract_offer(product: dict) -> tuple[float, float, bool, bool, str, str]:
    """Return (preco, preco_lista, disponivel, tem_oferta_clube, sku_id, seller_id)."""
    for item in product.get("items", []):
        sku_id = str(item.get("itemId") or "")
        for seller in item.get("sellers", []):
            seller_id = str(seller.get("sellerId") or "1")
            offer = seller.get("commertialOffer") or {}
            price = float(offer.get("Price") or 0)
            list_price = float(offer.get("ListPrice") or price)
            available = int(offer.get("AvailableQuantity") or 0) > 0
            teasers = offer.get("Teasers") or []
            has_club = bool(teasers)
            if price > 0:
                return price, list_price, available, has_club, sku_id, seller_id
    return 0.0, 0.0, False, False, "", "1"


def search(site_key: str, termo: str, marca_obrigatoria: str = "") -> list[ProductResult]:
    hostname = HOSTNAMES.get(site_key)
    if not hostname:
        raise ValueError(f"vtex.search: unknown site_key {site_key!r}")

    # VTEX's WAF rejects '+' as space (urlencode default). Use %20 via quote().
    ft = quote(termo, safe="")
    url = (
        f"https://{hostname}/api/catalog_system/pub/products/search/"
        f"?ft={ft}&_from=0&_to={_MAX_RESULTS - 1}"
    )

    try:
        products = _curl_get_json(url)
    except Exception as e:
        print(f"vtex.search({site_key}, {termo!r}) failed: {e}")
        return []

    if not isinstance(products, list):
        return []

    out: list[ProductResult] = []
    for p in products:
        preco, preco_lista, disponivel, tem_clube, sku_id, seller_id = _extract_offer(p)
        if preco <= 0:
            continue
        titulo = p.get("productName", "") or ""
        marca = p.get("brand", "") or ""
        pdp = p.get("link", "") or ""
        if pdp and not pdp.startswith("http"):
            pdp = f"https://{hostname}/{pdp.lstrip('/')}"

        qtde = extract_qtde_unidades(titulo)
        marca_ok = brand_confirmed_in(marca_obrigatoria, titulo, marca)
        out.append(ProductResult(
            site=site_key,
            url=pdp,
            titulo=titulo,
            preco=preco,
            preco_lista=preco_lista,
            marca_detectada=marca,
            qtde_unidades=qtde,
            preco_unidade=preco_por_unidade(preco, qtde),
            disponivel=disponivel,
            tem_oferta_clube=tem_clube,
            marca_confirmada=marca_ok,
            sku_id=sku_id,
            seller_id=seller_id,
        ))
    return out
