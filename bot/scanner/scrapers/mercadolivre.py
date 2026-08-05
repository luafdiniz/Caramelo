"""Mercado Livre scraper — via /products/search + /products/{id}/items.

Descoberta 2026-08-05: `/sites/MLB/search` retorna 403 forbidden para apps
não-certificados (independente do fluxo OAuth). A rota que funciona é o
**Catálogo Unificado**:

    /products/search?q=X&site_id=MLB  →  lista de catalog products (fichas)
    /products/{id}/items              →  vendedores ofertando aquele produto

Limitação: só retorna listings que os vendedores VINCULARAM ao catálogo.
Muitos listings ficam soltos ("No winners found"), invisíveis pra API.
Cobertura na prática: OK pra itens populares (leite condensado Cemil, formas
Plastilania 220ml/500ml); ruim pra Plastilania 1,1L (nenhum vendedor
vinculado ao catálogo hoje).

OAuth flow: ML rotaciona o refresh_token a cada uso. Depois de refresh,
`_write_back_refresh_token()` grava o novo valor em `ML_REFRESH_TOKEN`
via API do GitHub (precisa `GH_PAT` com scope=repo). Sem GH_PAT, o cron
funciona 1x e depois falha — o token velho vira "already used" no ML.

Setup inicial: `bot/scripts/setup_ml_oauth.py --client-id X --client-secret Y`
"""

from __future__ import annotations

import base64
import json
import os
import statistics
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
_PRODUCTS_SEARCH = "https://api.mercadolibre.com/products/search"
_PRODUCT_ITEMS = "https://api.mercadolibre.com/products/{pid}/items"
_TIMEOUT = 15
# How many catalog products to expand into items per query. 5 is enough for
# the top brand/model matches; more balloons API calls without adding hits.
_MAX_CATALOG_PRODUCTS = 5

_access_cache: dict = {"token": None, "expires_at": 0.0}


def _write_back_refresh_token(new_token: str) -> None:
    """Push a rotated refresh_token to the GitHub `ML_REFRESH_TOKEN` secret
    via API. Silently skipped if `GH_PAT` env is absent — caller sees a log
    line pointing at the manual fix.
    """
    pat = os.environ.get("GH_PAT", "").strip()
    repo = os.environ.get("GH_REPO", "luafdiniz/Caramelo").strip()
    if not pat:
        print(
            f"ml.refresh: GH_PAT not set — cannot write-back rotated token. "
            f"Cron will fail on next run. Manual fix: set ML_REFRESH_TOKEN "
            f"to ...{new_token[-8:]} in GH Secrets."
        )
        return

    try:
        import requests
        from nacl import public
    except ImportError as e:
        print(f"ml.refresh: write-back deps missing ({e}); token: ...{new_token[-8:]}")
        return

    try:
        pk_resp = requests.get(
            f"https://api.github.com/repos/{repo}/actions/secrets/public-key",
            headers={
                "Authorization": f"Bearer {pat}",
                "Accept": "application/vnd.github+json",
            },
            timeout=10,
        )
        pk_resp.raise_for_status()
        pk = pk_resp.json()
        pk_bytes = base64.b64decode(pk["key"])
        sealed = public.SealedBox(public.PublicKey(pk_bytes))
        enc = base64.b64encode(sealed.encrypt(new_token.encode())).decode()

        put_resp = requests.put(
            f"https://api.github.com/repos/{repo}/actions/secrets/ML_REFRESH_TOKEN",
            headers={
                "Authorization": f"Bearer {pat}",
                "Accept": "application/vnd.github+json",
            },
            json={"encrypted_value": enc, "key_id": pk["key_id"]},
            timeout=10,
        )
        if put_resp.status_code in (201, 204):
            print(f"ml.refresh: ✓ wrote back rotated token ...{new_token[-8:]}")
        else:
            print(f"ml.refresh: write-back HTTP {put_resp.status_code}: {put_resp.text[:200]}")
    except Exception as e:
        print(f"ml.refresh: write-back failed: {e}")


def _refresh_access_token() -> Optional[str]:
    """Trade ML_REFRESH_TOKEN for a short-lived access_token. Persists any
    rotated refresh_token back to GH Secrets."""
    client_id = os.environ.get("ML_CLIENT_ID", "").strip()
    client_secret = os.environ.get("ML_CLIENT_SECRET", "").strip()
    refresh_token = os.environ.get("ML_REFRESH_TOKEN", "").strip()
    if not client_id or not client_secret or not refresh_token:
        return None

    proc = subprocess.run(
        [
            "curl", "-sL", "--max-time", str(_TIMEOUT),
            "-X", "POST",
            "-H", "Content-Type: application/x-www-form-urlencoded",
            "-H", "Accept: application/json",
            "-d", (f"grant_type=refresh_token&client_id={client_id}"
                   f"&client_secret={client_secret}&refresh_token={refresh_token}"),
            _TOKEN_ENDPOINT,
        ],
        capture_output=True, text=True, timeout=_TIMEOUT + 5,
    )
    if proc.returncode != 0:
        print(f"ml.refresh curl exit {proc.returncode}: {proc.stderr[:100]}")
        return None
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        print(f"ml.refresh invalid json: {proc.stdout[:150]}")
        return None

    access_token = data.get("access_token")
    new_refresh = data.get("refresh_token")
    expires_in = int(data.get("expires_in") or 21600)

    if not access_token:
        print(f"ml.refresh no access_token: {str(data)[:200]}")
        return None

    if new_refresh and new_refresh != refresh_token:
        # Update env so re-entry within the same process picks it up.
        os.environ["ML_REFRESH_TOKEN"] = new_refresh
        _write_back_refresh_token(new_refresh)

    _access_cache["token"] = access_token
    _access_cache["expires_at"] = time.time() + expires_in
    return access_token


def _get_access_token() -> Optional[str]:
    now = time.time()
    if _access_cache["token"] and now < _access_cache["expires_at"] - 60:
        return _access_cache["token"]
    return _refresh_access_token()


def _brand_from_attributes(attrs: list[dict]) -> str:
    for a in attrs or []:
        if (a.get("id") or "").upper() == "BRAND":
            return a.get("value_name") or ""
    return ""


def _fetch_catalog_products(token: str, termo: str) -> list[dict]:
    """Return top catalog products (dicts) matching `termo`. Empty list on
    error / empty result."""
    q = quote(termo, safe="")
    url = (
        f"{_PRODUCTS_SEARCH}?q={q}&site_id=MLB&status=active"
        f"&limit={_MAX_CATALOG_PRODUCTS}"
    )
    proc = subprocess.run(
        [
            "curl", "-sL", "--max-time", str(_TIMEOUT),
            "-H", f"Authorization: Bearer {token}",
            "-H", "Accept: application/json",
            url,
        ],
        capture_output=True, text=True, timeout=_TIMEOUT + 5,
    )
    if proc.returncode != 0:
        return []
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, dict) or not data.get("results"):
        msg = (data or {}).get("message") or (data or {}).get("error") or ""
        if msg:
            print(f"ml.products/search({termo!r}) empty: {msg}")
        return []
    return data["results"] or []


def _fetch_items_for_product(token: str, product_id: str) -> list[dict]:
    """Return the list of items (seller offers) for a catalog product.
    Empty on 404 "No winners found" — many catalog products still lack any
    linked seller listings."""
    url = _PRODUCT_ITEMS.format(pid=product_id) + "?limit=100"
    proc = subprocess.run(
        [
            "curl", "-sL", "--max-time", str(_TIMEOUT),
            "-H", f"Authorization: Bearer {token}",
            "-H", "Accept: application/json",
            url,
        ],
        capture_output=True, text=True, timeout=_TIMEOUT + 5,
    )
    if proc.returncode != 0:
        return []
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return []
    if isinstance(data, dict) and data.get("results"):
        return data["results"]
    return []


def _best_offer_from_items(items: list[dict]) -> Optional[dict]:
    """Pick the item with the lowest total price (product + shipping cost).

    Discards low-price outliers: if the cheapest listing is < 50% of the
    second cheapest, it's almost certainly a seller with 0 sales listing
    a wrong price to bait clicks. Real "great deals" cluster near the second
    cheapest, so filtering here beats getting spurious 🔥 alerts.

    (Real case 2026-08-05: 'Leite Piracanjuba 1L - 12 Unidades' PDP had one
    listing at R$ 8 (0 vendas), others at R$ 71-200 — the R$ 8 caused a false
    🔥 alerta com R$ 0,67/un.)
    """
    ranked: list[tuple[float, dict]] = []
    for it in items:
        preco = it.get("price")
        if not preco or preco <= 0:
            continue
        shipping = it.get("shipping") or {}
        frete = 0.0
        if not shipping.get("free_shipping"):
            cost = shipping.get("cost")
            if isinstance(cost, (int, float)) and cost > 0:
                frete = float(cost)
        total = float(preco) + frete
        ranked.append((total, it))
    if not ranked:
        return None
    ranked.sort(key=lambda r: r[0])

    # Outlier filter: with 3+ listings, drop any priced under 30% of the
    # *original* median. Single-pass — recomputing after each drop makes
    # the median chase upward and cascades into dropping legitimate deals
    # (visto 2026-08-05: forma pudim 500ml a R\$ 4/un foi eliminada porque
    # após remover R\$ 1,64 a mediana subiu pra R\$ 27, e R\$ 4 virou outlier).
    if len(ranked) >= 3:
        median_p = statistics.median([r[0] for r in ranked])
        threshold = median_p * 0.3
        kept = []
        for total, item in ranked:
            if total < threshold:
                print(
                    f"ml.items: descartando outlier R$ {total:.2f} "
                    f"(seller {item.get('seller_id')}) — mediana é R$ {median_p:.2f}"
                )
                continue
            kept.append((total, item))
        ranked = kept

    if not ranked:
        return None
    return ranked[0][1]


def search(termo: str, marca_obrigatoria: str = "") -> list[ProductResult]:
    """One ProductResult per matching catalog product — its cheapest linked
    seller offer. Downstream `rules.best_of()` picks the best across all
    sites."""
    token = _get_access_token()
    if not token:
        return []

    products = _fetch_catalog_products(token, termo)
    if not products:
        return []

    out: list[ProductResult] = []
    for prod in products:
        prod_id = prod.get("id") or ""
        prod_name = prod.get("name") or ""
        if not prod_id:
            continue
        marca = _brand_from_attributes(prod.get("attributes") or [])
        marca_ok = brand_confirmed_in(marca_obrigatoria, prod_name, marca)
        # Skip early if the mandatory brand doesn't match — avoids the extra
        # /items call for products that will be filtered out downstream anyway.
        if marca_obrigatoria and not marca_ok:
            continue

        items = _fetch_items_for_product(token, prod_id)
        # Debug — quantos vendedores o catálogo desse product retornou.
        # Ajuda a entender por que o outlier filter (que exige 3+ listings)
        # pode não ter disparado num alerta suspeito.
        prices_dbg = sorted([it.get("price", 0) for it in items if it.get("price")])
        print(f"ml.search({termo!r}): PID={prod_id} items={len(items)} prices={prices_dbg[:5]}")
        best = _best_offer_from_items(items)
        if not best:
            continue

        preco = float(best.get("price") or 0)
        preco_lista = float(best.get("original_price") or preco)
        # Catalog PDP URL — lands on the product's aggregated page listing
        # every seller. More useful than one seller's item URL.
        pdp = f"https://www.mercadolivre.com.br/p/{prod_id}"

        qtde = extract_qtde_unidades(prod_name)
        medida_val, medida_un = extract_medida(prod_name)

        out.append(ProductResult(
            site="ML", url=pdp, titulo=prod_name,
            preco=preco, preco_lista=preco_lista,
            marca_detectada=marca,
            qtde_unidades=qtde,
            preco_unidade=preco_por_unidade(preco, qtde),
            disponivel=True,   # /items only returns active listings
            tem_oferta_clube=False,
            marca_confirmada=marca_ok,
            sku_id="",
            seller_id=str(best.get("seller_id") or "1"),
            medida_valor=medida_val,
            medida_unidade=medida_un,
        ))

    # Cross-catalog-product outlier filter — mesmo princípio da regra
    # dentro de _best_offer_from_items, mas comparando preco_unidade
    # entre catalog products distintos. Single-pass sobre a mediana
    # original pra não recalcular e cascatear em cima de ofertas reais.
    if len(out) >= 3:
        prices = [r.preco_unidade for r in out if r.preco_unidade > 0]
        if len(prices) >= 3:
            median_pu = statistics.median(prices)
            threshold = median_pu * 0.3
            kept = []
            for r in out:
                if r.preco_unidade > 0 and r.preco_unidade < threshold:
                    print(
                        f"ml.search: descartando catalog outlier {r.url} "
                        f"@ R$ {r.preco_unidade:.3f}/un — mediana é R$ {median_pu:.3f}/un"
                    )
                    continue
                kept.append(r)
            out = kept

    return out
