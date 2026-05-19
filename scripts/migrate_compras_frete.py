"""
Add `frete` and `desconto` columns to the Compras tab.

New columns:
    L: frete     — number. Delivery/freight cost for the whole Compra, repeated
                   on every row of the same Compra (since Compras is flat with
                   one row per item and there's no `header` tab).
    M: desconto  — number. Discount applied to the whole Compra (positive value).

Together they let the cost layer record the EFFECTIVE preco_unitario — i.e.
preco_unitario already with frete and desconto rateado proportionally over the
items of that Compra. The raw values stay in L/M for audit purposes.

Usage:
    # Dry-run (default):
    python scripts/migrate_compras_frete.py

    # Apply:
    python scripts/migrate_compras_frete.py --apply

Idempotent. Re-running after apply is a no-op.

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


NEW_HEADERS = ["frete", "desconto"]


def _read_headers(svc, ssid: str) -> list[str]:
    res = svc.spreadsheets().values().get(
        spreadsheetId=ssid, range="Compras!1:1"
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
    print(f"=== Migrate Compras frete/desconto — {mode} ===\n")

    headers = _read_headers(svc, ssid)
    print(f"Current Compras headers ({len(headers)} cols): {headers}")

    has_l = len(headers) >= 12 and headers[11].strip().lower() == "frete"
    has_m = len(headers) >= 13 and headers[12].strip().lower() == "desconto"

    if has_l and has_m:
        print("\nMigration already applied — frete + desconto found in L/M.")
        sys.exit(0)

    if (has_l and not has_m) or (has_m and not has_l):
        print("\nERROR: half-migrated state. Fix manually before re-running.",
              file=sys.stderr)
        sys.exit(1)

    if len(headers) > 11:
        print(
            f"\nERROR: Compras already has {len(headers)} columns but L is "
            f"{headers[11]!r}, not 'frete'. Refusing to overwrite.",
            file=sys.stderr,
        )
        sys.exit(1)

    print("\nPlanned changes:")
    print("  - Write L1 = 'frete'")
    print("  - Write M1 = 'desconto'")
    print("  - Existing rows keep L/M empty (treated as 0).")

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
        spreadsheetId=ssid, range="Compras!L1:M1",
        valueInputOption="USER_ENTERED",
        body={"values": [NEW_HEADERS]},
    ).execute()
    print("  ✓ Headers written.")

    print("\n=== DONE ===\n")
    print("Next: deploy code that reads/writes frete/desconto on Compras.")


if __name__ == "__main__":
    main()
