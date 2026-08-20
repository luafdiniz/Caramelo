"""Maria Chocolate scraper — Nuvemshop (mitiendanube) storefront.

A loja migrou de plataforma (era HTML CakePHP com <span class="product-big-price">;
agora é Nuvemshop). Mudanças que quebraram a v1:
- A rota de busca virou `/search?q=` (a antiga `/busca?q=` responde 404 com uma
  página genérica).
- Cada card é uma div `class="js-item-product ..."` com:
    - `data-product-id="NNN"`
    - nome em `<... js-item-name ...>NOME`
    - link em `href=".../produtos/SLUG/"`
    - preço de venda em `data-product-price="CENTAVOS"` (ex 3300 = R$ 33,00)
  Os preços NÃO estão mais em texto R$ no HTML (aparecem "R$0,00" e são
  preenchidos por JS), mas o valor real está no atributo `data-product-price`,
  então dá pra ler sem navegador headless.

Observação de catálogo: a busca full-text é estrita (AND das palavras). A loja
carrega descartáveis Plastilânia (potes, colheres, copos), mas NÃO as formas de
pudim — logo "forma pudim 500ml plastilania" volta vazio aqui de propósito
(ML/santoantonio cobrem as formas).

Frete: sem cálculo — mesmo esquema do ML. O runner deixa
`preco_com_frete = preco` pra sites fora do VTEX.
"""

from __future__ import annotations

import re
import subprocess
from urllib.parse import quote

from scanner.extractor import (
    extract_qtde_unidades,
    extract_medida,
    brand_confirmed_in,
    preco_por_unidade,
)
from scanner.scrapers.base import ProductResult


_BASE = "https://www.mariachocolate.com.br"
_SEARCH_URL = _BASE + "/search?q={q}"
_TIMEOUT = 20
_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# Per-product card. The storefront wraps each result in a div whose class
# starts with "js-item-product". We split on that marker and pull the fields
# out of each chunk (regex per chunk, not one giant cross-card regex).
_CARD_SPLIT = re.compile(r'class="js-item-product')
_RE_NAME = re.compile(r'js-item-name[^>]*>\s*([^<]{3,150})')
_RE_HREF = re.compile(r'href="(' + re.escape(_BASE) + r'/produtos/[^"]+)"')
_RE_PRICE = re.compile(r'data-product-price="(\d+)"')


def _fetch_search(termo: str) -> str:
    """Return the raw HTML of the search results page. Empty string on
    error — caller just gets no results.

    The storefront returns HTTP 200 for `/search?q=`; even on odd statuses we
    only care about the body, so we don't gate on HTTP code (curl returncode
    catches real transport failures)."""
    url = _SEARCH_URL.format(q=quote(termo, safe=""))
    proc = subprocess.run(
        [
            "curl", "-sL", "--max-time", str(_TIMEOUT),
            "-A", _USER_AGENT,
            url,
        ],
        capture_output=True, text=True, timeout=_TIMEOUT + 5,
    )
    if proc.returncode != 0:
        print(f"mariachocolate.search({termo!r}) curl exit {proc.returncode}")
        return ""
    return proc.stdout or ""


def search(termo: str, marca_obrigatoria: str = "") -> list[ProductResult]:
    """One ProductResult per product card on the search results page.
    Downstream rules.best_of picks the best across all sites."""
    html = _fetch_search(termo)
    if not html:
        return []

    out: list[ProductResult] = []
    for card in _CARD_SPLIT.split(html)[1:]:
        m_name = _RE_NAME.search(card)
        m_price = _RE_PRICE.search(card)
        if not m_name or not m_price:
            continue
        preco = int(m_price.group(1)) / 100.0
        if preco <= 0:
            continue
        titulo = re.sub(r"\s+", " ", m_name.group(1)).strip()
        m_href = _RE_HREF.search(card)
        url = m_href.group(1) if m_href else _BASE

        qtde = extract_qtde_unidades(titulo)
        medida_val, medida_un = extract_medida(titulo)
        # Maria Chocolate não expõe a marca separadamente — inferimos do
        # título (que costuma trazer "... - Plastilânia" no fim).
        marca_ok = brand_confirmed_in(marca_obrigatoria, titulo, "")

        out.append(ProductResult(
            site="mariachocolate", url=url, titulo=titulo,
            preco=preco, preco_lista=preco,
            marca_detectada="",
            qtde_unidades=qtde,
            preco_unidade=preco_por_unidade(preco, qtde),
            disponivel=True,   # search results só lista produto disponível
            tem_oferta_clube=False,
            marca_confirmada=marca_ok,
            sku_id="",
            seller_id="1",
            medida_valor=medida_val,
            medida_unidade=medida_un,
        ))
    return out
