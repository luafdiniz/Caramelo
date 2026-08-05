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
    access_token = data.get("access_token")
    if not refresh_token:
        print("Response inválido — code pode ter expirado (dura ~30s).")
        print(f"Detalhes: {json.dumps(data, indent=2)[:500]}")
        return 1

    print()
    print("=" * 70)
    print("PASSO 2 — Testar o access_token do exchange numa busca REAL")
    print("=" * 70)
    print(f"access_token: {access_token[:20]}..." if access_token else "access_token: (ausente!)")

    # Diagnostic: does the access_token that ML just handed us actually work
    # against /sites/MLB/search? Separates "OAuth flow broken" (both fail) from
    # "only refresh flow broken" (search works, refresh doesn't).
    if access_token:
        search_proc = subprocess.run(
            [
                "curl", "-sL", "--max-time", "20",
                "-H", f"Authorization: Bearer {access_token}",
                "-H", "Accept: application/json",
                "https://api.mercadolibre.com/sites/MLB/search?q=leite&limit=1",
            ],
            capture_output=True, text=True, timeout=25,
        )
        try:
            search_data = json.loads(search_proc.stdout)
        except json.JSONDecodeError:
            print(f"⚠️  busca resp não-JSON: {search_proc.stdout[:200]}")
            search_data = {}

        if isinstance(search_data, dict) and search_data.get("results"):
            print(f"✅ access_token FUNCIONA — recebeu {len(search_data['results'])} resultado(s).")
            print(f"   Isso confirma que OAuth em si tá OK; problema é SÓ no refresh flow.")
        else:
            msg = (search_data.get("message") or search_data.get("error")
                   or str(search_data)[:300])
            print(f"❌ access_token TAMBÉM falha na busca: {msg}")
            print(f"   Isso indica bloqueio de app/conta, não bug no refresh.")

    print()
    print("=" * 70)
    print("PASSO 3 — Testar refresh flow")
    print("=" * 70)
    print(f"Token recebido do exchange: {refresh_token}")

    # Immediately try to refresh with this token. If ML says "already used",
    # something's off with the app config or ML side. If it works, we get
    # a NEW refresh_token (ML rotates) — that's what we save to GH.
    test_body = (
        f"grant_type=refresh_token"
        f"&client_id={args.client_id}"
        f"&client_secret={args.client_secret}"
        f"&refresh_token={refresh_token}"
    )
    test_proc = subprocess.run(
        [
            "curl", "-sL", "--max-time", "20",
            "-X", "POST",
            "-H", "Content-Type: application/x-www-form-urlencoded",
            "-H", "Accept: application/json",
            "-d", test_body,
            TOKEN_URL,
        ],
        capture_output=True, text=True, timeout=25,
    )
    try:
        test_data = json.loads(test_proc.stdout)
    except json.JSONDecodeError:
        print(f"⚠️  refresh test — resposta não-JSON: {test_proc.stdout[:200]}")
        return 1

    if not test_data.get("access_token"):
        print(f"⚠️  refresh test FALHOU: {json.dumps(test_data, indent=2)[:400]}")
        print(f"O ML rejeitou este refresh_token na primeira tentativa.")
        print(f"Isso é bug/config do lado do ML — ver se 'Refresh Token' está mesmo")
        print(f"marcado nos Fluxos OAuth do app.")
        return 1

    print(f"✓ Refresh flow funciona. ML retornou access_token válido.")
    rotated = test_data.get("refresh_token")
    if rotated and rotated != refresh_token:
        print(f"✓ ML rotacionou o refresh_token (esperado — é rotativo).")
        print(f"Novo token: {rotated}")
        refresh_token = rotated
    else:
        print(f"✓ ML NÃO rotacionou — mesmo token vale pra próximo uso.")

    # Set the GH secret via --body-file so we don't rely on prompt paste
    # (which sometimes trims special chars). Write to a temp file, run
    # gh secret set --body-file <tmp>, delete.
    import tempfile
    import os as _os
    with tempfile.NamedTemporaryFile("w", delete=False, suffix=".txt") as tf:
        tf.write(refresh_token)
        tmp_path = tf.name
    try:
        proc = subprocess.run(
            ["gh", "secret", "set", "ML_REFRESH_TOKEN",
             "-R", "luafdiniz/Caramelo",
             "--body-file", tmp_path],
            capture_output=True, text=True,
        )
        if proc.returncode != 0:
            print(f"⚠️  gh secret set falhou: {proc.stderr[:200]}")
            print(f"Token: {refresh_token}")
            print("Cola manualmente em GH → Settings → Secrets → ML_REFRESH_TOKEN")
            return 1
        print("✓ ML_REFRESH_TOKEN atualizado no GitHub")
    finally:
        _os.unlink(tmp_path)

    print()
    print(f"Testa: gh workflow run 'Scanner de Preços' -R luafdiniz/Caramelo -f dry_run=true")
    return 0


if __name__ == "__main__":
    sys.exit(main())
