"""
Add manual price override columns to the Produtos tab.

New columns:
    G: Preco_manual       — number (float). Empty = no override.
    H: Preco_manual_data  — ISO date (YYYY-MM-DD). Empty = no override.

Together they let the app store a manually-set price for a produto WITHOUT
having to create a fake Compra ("Ajuste manual de preço") just to carry the
value. The override is honored by `current_unit_price()` while its date is
newer than the most recent Compra for that produto. Next real Compra → the
override expires automatically.

Usage:
    # Dry-run (default) — shows what would change, no writes:
    python scripts/migrate_produtos_preco_manual.py

    # Apply for real:
    python scripts/migrate_produtos_preco_manual.py --apply

Idempotent: re-running after a successful apply is a no-op (it detects that
the headers already exist and exits cleanly).

Required env vars: SPREADSHEET_ID, GOOGLE_SERVICE_ACCOUNT_JSON.
"""

from __future__ import annotations
import argparse
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "bot"))

from bot.lib import sheets as _sheets  # noqa: E402


NEW_HEADERS = ["Preco_manual", "Preco_manual_data"]


def _read_headers(svc, ssid: str) -> list[str]:
    res = svc.spreadsheets().values().get(
        spreadsheetId=ssid, range="Produtos!1:1"
    ).execute()
    rows = res.get("values", [])
    return rows[0] if rows else []


def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--apply", action="store_true",
                        help="Actually write the changes (default is dry-run).")
    args = parser.parse_args()

    ssid = os.environ.get("SPREADSHEET_ID")
    if not ssid:
        print("ERROR: SPREADSHEET_ID env var not set.", file=sys.stderr)
        sys.exit(2)

    svc = _sheets.get_service()
    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"=== Migrate Produtos preco_manual — {mode} ===\n")

    headers = _read_headers(svc, ssid)
    print(f"Current Produtos headers ({len(headers)} cols): {headers}")

    has_g = len(headers) >= 7 and headers[6].strip().lower() == "preco_manual"
    has_h = len(headers) >= 8 and headers[7].strip().lower() == "preco_manual_data"

    if has_g and has_h:
        print("\nMigration already applied — Preco_manual + Preco_manual_data found in G/H.")
        print("Nothing to do.")
        sys.exit(0)

    if (has_g and not has_h) or (has_h and not has_g):
        print(
            "\nERROR: half-migrated state detected (one of G/H present, other missing).\n"
            "Fix manually before re-running.",
            file=sys.stderr,
        )
        sys.exit(1)

    if len(headers) > 6:
        print(
            f"\nERROR: Produtos already has {len(headers)} columns but G is "
            f"{headers[6]!r}, not 'Preco_manual'. Refusing to overwrite.\n"
            f"If this is wrong, edit the headers manually first.",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"\nPlanned changes:")
    print(f"  - Write G1 = 'Preco_manual'")
    print(f"  - Write H1 = 'Preco_manual_data'")
    print(f"  - Existing rows keep G/H empty (no backfill)")

    if not args.apply:
        print("\n=== DRY-RUN: no changes written. ===")
        sys.exit(0)

    if sys.stdin.isatty():
        ans = input("\nType 'yes' to proceed: ").strip().lower()
        if ans != "yes":
            print("Aborted.")
            sys.exit(0)

    print("\n=== APPLYING ===\n")
    svc.spreadsheets().values().update(
        spreadsheetId=ssid, range="Produtos!G1:H1",
        valueInputOption="USER_ENTERED",
        body={"values": [NEW_HEADERS]},
    ).execute()
    print("  ✓ Headers written.")

    print("\n=== DONE ===\n")
    print("Next steps:")
    print("  1. Reload the Streamlit app — cache refreshes in ~30s, or click 🔄.")
    print("  2. Editar 'Preço atual' em Insumos agora salva direto em Produtos.G/H,")
    print("     sem criar Compra fantasma.")
    print("  3. O override expira sozinho quando uma Compra mais nova entrar.")


if __name__ == "__main__":
    main()
