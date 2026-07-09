"""Mercado Livre scraper — DISABLED in the MVP.

Original approach used https://api.mercadolibre.com/sites/MLB/search but it
now requires OAuth (returns 403 without token). HTML scraping of
lista.mercadolivre.com.br triggers the "suspicious traffic" bot-check page.

To enable later, either:
  (a) Register a ML app and use client_credentials OAuth to hit the public
      API with a Bearer token, or
  (b) Adopt curl_cffi / Playwright to pass ML's TLS+behavior fingerprinting
      on the HTML pages.

Leaving the function so runner/config code needs no change once we bring it
back.
"""

from __future__ import annotations

from scanner.scrapers.base import ProductResult


def search(termo: str, marca_obrigatoria: str = "") -> list[ProductResult]:
    print(f"ml.search({termo!r}) skipped — ML disabled in MVP (see module docstring)")
    return []
