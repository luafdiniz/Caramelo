"""Mercado Livre scraper — Authorization Code flow with auto-rotating refresh token.

Client Credentials tokens are silently forbidden on `sites/MLB/search` (ML
returns 403 even with valid app-only tokens). We use the Authorization Code
grant: user autoriza the app once, we store the resulting refresh_token in
the `_ScannerAuth` tab of the Sheet, and refresh a short-lived access_token
on every scan.

ML rotates the refresh_token on every use — the new one is written back to
the Sheet immediately so subsequent scans pick it up. If ML rejects the
refresh_token (expired ~6 months or invalidated), the scraper silently
returns [] and the other sites keep working.

Setup: run `bot/scripts/setup_ml_oauth.py` once with client_id/client_secret.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from datetime import datetime
from typing import Optional
from urllib.parse import quote

from lib import sheets
from scanner.extractor import (
    extract_qtde_unidades,
    extract_medida,
    brand_confirmed_in,
    preco_por_unidade,
)
from scanner.scrapers.base import ProductResult


_TOKEN_ENDPOINT = "https://api.mercadolibre.com/oauth/token"
_SEARCH_ENDPOINT = "https://api.mercadolibre.com/sites/MLB/search"
_AUTH_TAB = "_ScannerAuth"
_TIMEOUT = 15
_MAX_RESULTS = 10

_access_cache: dict = {"token": None, "expires_at": 0.0}


def _spreadsheet_id() -> Optional[str]:
    return os.environ.get("SPREADSHEET_ID")


def _read_auth_row(key: str) -> Optional[str]:
    sid = _spreadsheet_id()
    if not sid:
        return None
    try:
        svc = sheets.get_service()
        r = svc.spreadsheets().values().get(
            spreadsheetId=sid, range=f"{_AUTH_TAB}!A2:B",
        ).execute()
    except Exception as e:
        print(f"ml._read_auth_row: {e}")
        return None
    for row in r.get("values", []) or []:
        if len(row) >= 2 and row[0] == key:
            return str(row[1]) or None
    return None


def _write_auth_row(key: str, value: str) -> None:
    sid = _spreadsheet_id()
    if not sid:
        return
    try:
        svc = sheets.get_service()
        r = svc.spreadsheets().values().get(
            spreadsheetId=sid, range=f"{_AUTH_TAB}!A2:A",
        ).execute()
        rows = r.get("values", []) or []
        target_row = None
        for i, row in enumerate(rows, start=2):
            if row and row[0] == key:
                target_row = i
                break
        if target_row is None:
            target_row = len(rows) + 2
        now = datetime.utcnow().isoformat(timespec="seconds")
        svc.spreadsheets().values().update(
            spreadsheetId=sid, range=f"{_AUTH_TAB}!A{target_row}:C{target_row}",
            valueInputOption="RAW",
            body={"values": [[key, value, now]]},
        ).execute()
    except Exception as e:
        print(f"ml._write_auth_row: {e}")


def _refresh_access_token() -> Optional[str]:
    client_id = os.environ.get("ML_CLIENT_ID", "").strip()
    client_secret = os.environ.get("ML_CLIENT_SECRET", "").strip()
    if not client_id or not client_secret:
        return None
    refresh_token = _read_auth_row("ml_refresh_token")
    if not refresh_token:
        print("ml.refresh: no refresh_token in _ScannerAuth — run setup_ml_oauth.py")
        return None

    args = [
        "curl", "-sL", "--max-time", str(_TIMEOUT),
        "-X", "POST",
        "-H", "Content-Type: application/x-www-form-urlencoded",
        "-H", "Accept: application/json",
        "-d", (f"grant_type=refresh_token&client_id={client_id}"
               f"&client_secret={client_secret}&refresh_token={refresh_token}"),
        _TOKEN_ENDPOINT,
    ]
    proc = subprocess.run(args, capture_output=True, text=True, timeout=_TIMEOUT + 5)
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

    # ML rotates the refresh_token — persist immediately for the next scan.
    if new_refresh and new_refresh != refresh_token:
        _write_auth_row("ml_refresh_token", new_refresh)

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


def search(termo: str, marca_obrigatoria: str = "") -> list[ProductResult]:
    token = _get_access_token()
    if not token:
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
        return []
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return []

    # Expired token mid-run — clear cache and retry once
    if isinstance(data, dict) and data.get("status") in (401, "401"):
        _access_cache["token"] = None
        token = _refresh_access_token()
        if not token:
            return []
        args[args.index(f"Authorization: Bearer {token}") if False else 4] = f"Authorization: Bearer {token}"
        # Simpler: full retry
        return search(termo, marca_obrigatoria)

    if not data.get("results"):
        msg = data.get("message") or data.get("error") or ""
        if msg:
            print(f"ml.search({termo!r}) empty: {msg}")
        return []

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
            site="ML", url=pdp, titulo=titulo,
            preco=preco, preco_lista=preco_lista,
            marca_detectada=marca,
            qtde_unidades=qtde,
            preco_unidade=preco_por_unidade(preco, qtde),
            disponivel=available,
            tem_oferta_clube=False,
            marca_confirmada=marca_ok,
            sku_id="", seller_id="1",
            medida_valor=medida_val,
            medida_unidade=medida_un,
        ))
    return out
