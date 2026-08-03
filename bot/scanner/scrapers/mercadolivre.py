"""Mercado Livre scraper via `api.mercadolibre.com/sites/MLB/search`.

Uses OAuth client_credentials flow — free ML dev app registered at
https://developers.mercadolibre.com.br/devcenter provides
`ML_CLIENT_ID` + `ML_CLIENT_SECRET` (set as GitHub secrets).

Token is fetched once per Python process and cached until expiry (6h).
Since GH Actions runs are ~1 min, we effectively fetch a token every run.

If either secret is missing the module silently returns [], keeping the
scanner working with the other sites.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from typing import Optional
from urllib.parse import quote

from scanner.extractor import (
    extract_qtde_unidades,
    extract_medida,
    brand_confirmed_in,
    preco_por_unidade,
)
from scanner.scrapers.base import ProductResult


_TOKEN_ENDPOINT = "https://api.mercadolibre.com/oauth/token"
_SEARCH_ENDPOINT = "https://api.mercadolibre.com/sites/MLB/search"
_TIMEOUT = 15
_MAX_RESULTS = 10

_token_cache: dict = {"token": None, "expires_at": 0.0}


def _get_token() -> Optional[str]:
    """Fetch (and cache) an OAuth bearer token via client_credentials."""
    now = time.time()
    if _token_cache["token"] and now < _token_cache["expires_at"] - 60:
        return _token_cache["token"]

    client_id = os.environ.get("ML_CLIENT_ID", "").strip()
    client_secret = os.environ.get("ML_CLIENT_SECRET", "").strip()
    if not client_id or not client_secret:
        return None

    args = [
        "curl", "-sL", "--max-time", str(_TIMEOUT),
        "-X", "POST",
        "-H", "Content-Type: application/x-www-form-urlencoded",
        "-H", "Accept: application/json",
        "-d", f"grant_type=client_credentials&client_id={client_id}&client_secret={client_secret}",
        _TOKEN_ENDPOINT,
    ]
    proc = subprocess.run(args, capture_output=True, text=True, timeout=_TIMEOUT + 5)
    if proc.returncode != 0:
        print(f"ml.oauth curl exit {proc.returncode}: {proc.stderr[:100]}")
        return None
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        print(f"ml.oauth invalid json: {proc.stdout[:100]}")
        return None

    token = data.get("access_token")
    expires_in = int(data.get("expires_in") or 21600)
    if not token:
        print(f"ml.oauth no access_token in response: {str(data)[:150]}")
        return None

    _token_cache["token"] = token
    _token_cache["expires_at"] = now + expires_in
    return token


def _brand_from_attributes(attrs: list[dict]) -> str:
    for a in attrs or []:
        if (a.get("id") or "").upper() == "BRAND":
            return a.get("value_name") or ""
    return ""


def search(termo: str, marca_obrigatoria: str = "") -> list[ProductResult]:
    token = _get_token()
    if not token:
        # Missing creds or oauth failure — silently skip (other sites still work)
        return []

    q = quote(termo, safe="")
    url = f"{_SEARCH_ENDPOINT}?q={q}&limit={_MAX_RESULTS}&condition=new"

    args = [
        "curl", "-sL", "--max-time", str(_TIMEOUT),
        "-H", f"Authorization: Bearer {token}",
        "-H", "Accept: application/json",
        url,
    ]
    proc = subprocess.run(args, capture_output=True, text=True, timeout=_TIMEOUT + 5)
    if proc.returncode != 0:
        print(f"ml.search curl exit {proc.returncode}: {proc.stderr[:100]}")
        return []
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        print(f"ml.search invalid json: {proc.stdout[:150]}")
        return []

    # Token expired mid-run? Clear cache and retry once.
    if isinstance(data, dict) and data.get("status") == 401:
        _token_cache["token"] = None
        return search(termo, marca_obrigatoria)

    out: list[ProductResult] = []
    for item in data.get("results", []) or []:
        preco = float(item.get("price") or 0)
        if preco <= 0:
            continue
        titulo = item.get("title", "") or ""
        marca = _brand_from_attributes(item.get("attributes", []) or [])
        pdp = item.get("permalink", "") or ""
        available = int(item.get("available_quantity") or 0) > 0
        preco_lista = float(item.get("original_price") or preco)

        qtde = extract_qtde_unidades(titulo)
        medida_val, medida_un = extract_medida(titulo)
        marca_ok = brand_confirmed_in(marca_obrigatoria, titulo, marca)

        out.append(ProductResult(
            site="ML",
            url=pdp,
            titulo=titulo,
            preco=preco,
            preco_lista=preco_lista,
            marca_detectada=marca,
            qtde_unidades=qtde,
            preco_unidade=preco_por_unidade(preco, qtde),
            disponivel=available,
            tem_oferta_clube=False,
            marca_confirmada=marca_ok,
            sku_id="",  # ML uses `permalink` not sku — freight not simulated
            seller_id="1",
            medida_valor=medida_val,
            medida_unidade=medida_un,
        ))
    raw_count = len(data.get('results', []) or [])
    print(f"ml.search({termo!r}) raw={raw_count} → após filtro marca={len(out)}")
    return out
