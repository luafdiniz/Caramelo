"""One-time setup for the ML Authorization Code flow.

Usage:
    cd bot
    .venv/bin/python scripts/setup_ml_oauth.py \\
        --client-id <APP_ID> --client-secret <SECRET_KEY>

Steps performed:
  1. Prints the authorization URL. You open it in the browser, logged into
     your Mercado Livre account, and authorize the app.
  2. ML redirects to https://github.com/luafdiniz/Caramelo?code=XXX
     (browser will show 404 — that's fine, we only need the URL).
  3. You paste the ?code= value here.
  4. Script exchanges the code for a long-lived refresh_token and prints it.

You then save the refresh_token as a GitHub secret:
    gh secret set ML_REFRESH_TOKEN -R luafdiniz/Caramelo
    # paste the token when prompted (input is hidden)

After that, `bot/scanner/scrapers/mercadolivre.py` reads it from env every
scan and exchanges for a fresh access_token.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys


REDIRECT_URI = "https://github.com/luafdiniz/Caramelo"
AUTH_URL = "https://auth.mercadolivre.com.br/authorization"
TOKEN_URL = "https://api.mercadolibre.com/oauth/token"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--client-id", required=True)
    parser.add_argument("--client-secret", required=True)
    args = parser.parse_args()

    auth_url = (
        f"{AUTH_URL}?response_type=code"
        f"&client_id={args.client_id}"
        f"&redirect_uri={REDIRECT_URI}"
    )
    print()
    print("=" * 70)
    print("PASSO 1 — Autorizar o app")
    print("=" * 70)
    print()
    print("Abre esta URL no browser (logada no Mercado Livre):")
    print()
    print(f"  {auth_url}")
    print()
    print("Cada vez que você abre esta URL e clica 'Autorizar', o ML gera")
    print("um code novo. O anterior expira.")
    print()
    print("Após autorizar, o browser vai pra:")
    print(f"  {REDIRECT_URI}?code=XXXXXX...")
    print("(GitHub vai mostrar 404 — normal, é só pra capturar o code na URL)")
    print()
    code = input("Cola aqui apenas o valor do 'code' (sem 'code='): ").strip()
    if not code:
        print("Code vazio, abortando.")
        return 1

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
    if not refresh_token:
        print("Response inválido — code pode ter expirado (dura ~30s).")
        print(f"Detalhes: {json.dumps(data, indent=2)[:500]}")
        return 1

    print()
    print("=" * 70)
    print("✓ REFRESH TOKEN OBTIDO")
    print("=" * 70)
    print()
    print("Cole o valor abaixo em ML_REFRESH_TOKEN no GitHub:")
    print()
    print(f"  {refresh_token}")
    print()
    print("Comando pra setar via CLI (input escondido):")
    print()
    print(f"  gh secret set ML_REFRESH_TOKEN -R luafdiniz/Caramelo")
    print()
    print("Depois disso, roda o dry-run:")
    print()
    print(f"  gh workflow run 'Scanner de Preços' -R luafdiniz/Caramelo -f dry_run=true")
    return 0


if __name__ == "__main__":
    sys.exit(main())
