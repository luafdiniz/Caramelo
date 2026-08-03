"""One-time setup for the ML Authorization Code flow.

Usage:
    cd bot
    SPREADSHEET_ID=... GOOGLE_SERVICE_ACCOUNT_JSON=... \\
        .venv/bin/python scripts/setup_ml_oauth.py \\
            --client-id <APP_ID> --client-secret <SECRET_KEY>

Steps performed:
  1. Prints the authorization URL. You open it in the browser, logged into
     your Mercado Livre account, and authorize the app.
  2. ML redirects to https://github.com/luafdiniz/Caramelo?code=XXX
     (browser will show 404 — that's fine, we only need the URL).
  3. You paste the ?code= value here.
  4. Script exchanges the code for a long-lived refresh_token and stores it
     in the Sheet's _ScannerAuth tab.

After this, `bot/scanner/scrapers/mercadolivre.py` uses that refresh_token
to obtain short-lived access_tokens on every scan (auto-rotation handled).
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime


REDIRECT_URI = "https://github.com/luafdiniz/Caramelo"
AUTH_URL = "https://auth.mercadolivre.com.br/authorization"
TOKEN_URL = "https://api.mercadolibre.com/oauth/token"
SHEET_TAB = "_ScannerAuth"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--client-id", required=True)
    parser.add_argument("--client-secret", required=True)
    args = parser.parse_args()

    # Step 1: print the auth URL
    auth_url = (
        f"{AUTH_URL}?response_type=code"
        f"&client_id={args.client_id}"
        f"&redirect_uri={REDIRECT_URI}"
    )
    print()
    print("=" * 70)
    print("PASSO 1 — Autorizar o app no browser")
    print("=" * 70)
    print()
    print("Abre esta URL no browser (logada no Mercado Livre):")
    print()
    print(f"  {auth_url}")
    print()
    print("Após autorizar, o browser será redirecionado pra:")
    print(f"  {REDIRECT_URI}?code=XXXXXX...")
    print("(GitHub vai mostrar 404 — normal, é só pra capturar o code)")
    print()
    code = input("Cola aqui apenas o valor do 'code' (só o valor, sem 'code='): ").strip()
    if not code:
        print("Code vazio, abortando.")
        return 1

    # Step 2: exchange code for refresh_token
    print()
    print("Trocando code por refresh_token...")
    body = (
        f"grant_type=authorization_code"
        f"&client_id={args.client_id}"
        f"&client_secret={args.client_secret}"
        f"&code={code}"
        f"&redirect_uri={REDIRECT_URI}"
    )
    proc = subprocess.run(
        [
            "curl", "-sL", "--max-time", "20",
            "-X", "POST",
            "-H", "Content-Type: application/x-www-form-urlencoded",
            "-H", "Accept: application/json",
            "-d", body,
            TOKEN_URL,
        ],
        capture_output=True, text=True, timeout=25,
    )
    if proc.returncode != 0:
        print(f"curl failed: {proc.stderr[:200]}")
        return 1

    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        print(f"Response não é JSON: {proc.stdout[:300]}")
        return 1

    refresh_token = data.get("refresh_token")
    access_token = data.get("access_token")
    if not refresh_token:
        print(f"Response inválido — verifica se o code não expirou (dura ~30s).")
        print(f"Detalhes: {json.dumps(data, indent=2)[:500]}")
        return 1

    print(f"✓ Refresh token obtido (dura ~6 meses; ML rotaciona a cada uso)")
    print(f"✓ Access token válido por ~6h ({data.get('expires_in')}s)")

    # Step 3: persist refresh_token in the Sheet
    import os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from lib import sheets

    sid = os.environ.get("SPREADSHEET_ID")
    if not sid:
        print("SPREADSHEET_ID env var não setado — refresh_token NÃO foi persistido.")
        print(f"Refresh token: {refresh_token}")
        return 1

    svc = sheets.get_service()

    # Ensure tab exists
    meta = svc.spreadsheets().get(spreadsheetId=sid).execute()
    if SHEET_TAB not in {s['properties']['title'] for s in meta['sheets']}:
        svc.spreadsheets().batchUpdate(
            spreadsheetId=sid,
            body={'requests': [{'addSheet': {'properties': {'title': SHEET_TAB, 'hidden': True}}}]},
        ).execute()
        svc.spreadsheets().values().update(
            spreadsheetId=sid, range=f'{SHEET_TAB}!A1:C1',
            valueInputOption='RAW',
            body={'values': [['key', 'value', 'updated_at']]},
        ).execute()

    now = datetime.utcnow().isoformat(timespec="seconds")
    # Find or append the ml_refresh_token row
    r = svc.spreadsheets().values().get(
        spreadsheetId=sid, range=f"{SHEET_TAB}!A2:A",
    ).execute()
    rows = r.get("values", []) or []
    target = None
    for i, row in enumerate(rows, start=2):
        if row and row[0] == "ml_refresh_token":
            target = i
            break
    if target is None:
        target = len(rows) + 2

    svc.spreadsheets().values().update(
        spreadsheetId=sid, range=f"{SHEET_TAB}!A{target}:C{target}",
        valueInputOption='RAW',
        body={'values': [['ml_refresh_token', refresh_token, now]]},
    ).execute()

    print()
    print("=" * 70)
    print("✓ SETUP COMPLETO")
    print("=" * 70)
    print(f"refresh_token salvo em {SHEET_TAB}!A{target}:C{target}")
    print(f"Próximo scan já vai usar. Testa com:")
    print(f"  gh workflow run 'Scanner de Preços' -R luafdiniz/Caramelo -f dry_run=true")
    return 0


if __name__ == "__main__":
    sys.exit(main())
