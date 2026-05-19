"""
Create the Clientes, Vendas and Precos tabs that Tema D depends on.

Tabs created (in order):

  1. `Clientes`         A:J  — list of customers (B2C / B2B)
  2. `Vendas`           A:L  — individual sale events
  3. `Precos`           A:E  — price by (tamanho, tipo_cliente, qtde_min) — supports volume tiers

Also seeds a permanent customer `CLI-000 — Cliente Avulso` (B2C) so balcão
sales don't need a real CLI-NNN entry.

Usage:
    python scripts/migrate_clientes_vendas.py            # dry-run
    python scripts/migrate_clientes_vendas.py --apply

Idempotent: re-running detects existing tabs and skips them.

Required env vars: SPREADSHEET_ID, GOOGLE_SERVICE_ACCOUNT_JSON.
"""

from __future__ import annotations
import argparse
import os
import sys
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "bot"))

from bot.lib import sheets as _sheets  # noqa: E402


CLIENTES_HEADERS = [
    "id", "nome", "tipo", "contato", "endereco",
    "dia_entrega_preferido", "periodicidade", "observacoes",
    "data_cadastro", "ativo",
]
VENDAS_HEADERS = [
    "id", "data", "cliente_id", "tamanho_id", "qtde",
    "preco_unit_efetivo", "preco_total", "canal",
    "forma_pagamento", "status", "custo_unit_estimado", "notas",
]
PRECOS_HEADERS = [
    "tamanho_id", "tipo_cliente", "qtde_min", "preco_unit", "notas",
]


def _sheet_titles(svc, ssid: str) -> list[str]:
    meta = svc.spreadsheets().get(spreadsheetId=ssid).execute()
    return [s["properties"]["title"] for s in meta["sheets"]]


def _add_sheet(svc, ssid: str, title: str) -> None:
    svc.spreadsheets().batchUpdate(
        spreadsheetId=ssid,
        body={"requests": [{"addSheet": {"properties": {"title": title}}}]},
    ).execute()


def _write_headers(svc, ssid: str, sheet: str, headers: list[str]) -> None:
    svc.spreadsheets().values().update(
        spreadsheetId=ssid, range=f"{sheet}!A1",
        valueInputOption="USER_ENTERED",
        body={"values": [headers]},
    ).execute()


def _append_row(svc, ssid: str, sheet: str, row: list) -> None:
    svc.spreadsheets().values().append(
        spreadsheetId=ssid, range=f"{sheet}!A1",
        valueInputOption="USER_ENTERED",
        body={"values": [row]},
    ).execute()


def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    ssid = os.environ.get("SPREADSHEET_ID")
    if not ssid:
        print("ERROR: SPREADSHEET_ID env var not set.", file=sys.stderr)
        sys.exit(2)

    svc = _sheets.get_service()
    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"=== Migrate Clientes/Vendas/Precos — {mode} ===\n")

    titles = _sheet_titles(svc, ssid)
    plan = []
    if "Clientes" not in titles:
        plan.append(("Clientes", CLIENTES_HEADERS,
                     ["CLI-000", "Cliente Avulso", "B2C", "", "", "", "",
                      "Balcão / venda casual sem cadastro", date.today().isoformat(), True]))
    else:
        print("  · Clientes já existe — pulando.")
    if "Vendas" not in titles:
        plan.append(("Vendas", VENDAS_HEADERS, None))
    else:
        print("  · Vendas já existe — pulando.")
    if "Precos" not in titles:
        plan.append(("Precos", PRECOS_HEADERS, None))
    else:
        print("  · Precos já existe — pulando.")

    if not plan:
        print("\nNothing to migrate. Exiting.")
        sys.exit(0)

    print("\nPlanned changes:")
    for sheet, headers, seed in plan:
        print(f"  + Create tab '{sheet}' with headers: {headers}")
        if seed:
            print(f"      and seed row: {seed}")

    if not args.apply:
        print("\n=== DRY-RUN: no changes written. ===")
        sys.exit(0)

    if sys.stdin.isatty():
        ans = input("\nType 'yes' to proceed: ").strip().lower()
        if ans != "yes":
            print("Aborted.")
            sys.exit(0)

    print("\n=== APPLYING ===\n")
    for sheet, headers, seed in plan:
        print(f"→ Creating '{sheet}'…")
        _add_sheet(svc, ssid, sheet)
        _write_headers(svc, ssid, sheet, headers)
        if seed:
            _append_row(svc, ssid, sheet, seed)
            print(f"  ✓ Seeded with: {seed[0]} — {seed[1]}")
        else:
            print("  ✓ Headers written.")

    print("\n=== DONE ===\n")
    print("Next: deploy pages 8/9/10 and o resolver de preço em app/lib/data.py.")


if __name__ == "__main__":
    main()
