"""Maria Chocolate scraper — HTML server-side (Apache/CakePHP).

Diferente do VTEX (que tem catalog API JSON), Maria Chocolate serve HTML
puro. Cada produto na página de busca tem esta estrutura:

    <div class="product-name">
      <a href="URL"><h2>NOME</h2></a>
    </div>
    <p class="product-price">
      <span class="product-big-price"><ins>R$ 16,80</ins></span>
    </p>
    <p class="product-unit">... Unitário</p>

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
_SEARCH_URL = _BASE + "/busca?q={q}"
_TIMEOUT = 20
_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# Product block on the search page. `.*?` between fields is non-greedy so
# we don't accidentally match across blocks.
_PRODUCT_BLOCK = re.compile(
    r'<div class="product-name">'
    r'<a href="([^"]+)"[^>]*>'
    r'<h2>([^<]+)</h2>'
    r'.*?'
    r'<span class="product-big-price"><ins>R\$\s*([\d.]+,\d{2})</ins></span>'
    r'.*?'
    r'<p class="product-unit">',
    re.S,
)


def _parse_brl(s: str) -> float:
    """'16,80' or '1.234,56' → float."""
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    else:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return 0.0


def _fetch_search(termo: str) -> str:
    """Return the raw HTML of the search results page. Empty string on
    error — caller just gets no results."""
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
    """One ProductResult per product on the search results page.
    Downstream rules.best_of picks the best across all sites."""
    html = _fetch_search(termo)
    if not html:
        return []

    out: list[ProductResult] = []
    for url_rel, nome, preco_raw in _PRODUCT_BLOCK.findall(html):
        preco = _parse_brl(preco_raw)
        if preco <= 0:
            continue
        titulo = re.sub(r"\s+", " ", nome).strip()
        url = url_rel if url_rel.startswith("http") else _BASE + url_rel

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
