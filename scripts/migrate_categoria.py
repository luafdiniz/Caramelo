"""
Migrate a Produto to a different categoria (changes its ID prefix and updates
all references). Use when the bot created a produto under the wrong category
and you want a clean fix instead of leaving the ID lying about the categoria.

Usage:
    # Dry-run (default) — shows everything that would change, no writes:
    python scripts/migrate_categoria.py --from FOR-007 --to-categoria EMB

    # Apply for real:
    python scripts/migrate_categoria.py --from FOR-007 --to-categoria EMB --apply

What it does:
    1. Looks up the old produto in Produtos (errors out if not found).
    2. Picks the next free ID under the new categoria prefix (e.g. EMB-019).
    3. Lists every reference in Compras (col C: produto_id), Aliases
       (col D: resolved_id), Embalagens_Por_Tamanho (col B: produto_id)
       and Receita_Ingredientes (col B: produto_id).
    4. With --apply:
        - Creates new row in Produtos with the new ID + same data (including
          the manual price override columns G/H if set).
        - Updates each reference in place.
        - Clears the old row in Produtos.

Required env vars (same as the bot):
    SPREADSHEET_ID, GOOGLE_SERVICE_ACCOUNT_JSON (path or JSON content)
"""

from __future__ import annotations
import argparse
import os
import sys
from pathlib import Path

# Make `bot/lib/sheets.py` importable.
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "bot"))

from bot.lib import sheets as _sheets  # noqa: E402


VALID_CATEGORIAS = {"ALI", "FOR", "EMB", "GRA", "EQP", "OPR"}


def _next_id_for_categoria(svc, ssid: str, categoria: str) -> str:
    """Find the next free ID under a categoria prefix (e.g. EMB-019)."""
    rows = svc.spreadsheets().values().get(
        spreadsheetId=ssid, range="Produtos!A:A"
    ).execute().get("values", [])
    used_numbers = []
    prefix = f"{categoria}-"
    for r in rows:
        if r and r[0].startswith(prefix):
            try:
                used_numbers.append(int(r[0].split("-", 1)[1]))
            except (IndexError, ValueError):
                continue
    next_n = (max(used_numbers) + 1) if used_numbers else 1
    return f"{categoria}-{next_n:03d}"


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--from", dest="from_id", required=True, help="Produto ID to migrate (e.g. FOR-007)")
    parser.add_argument(
        "--to-categoria", required=True,
        help=f"Target categoria prefix. One of: {sorted(VALID_CATEGORIAS)}",
    )
    parser.add_argument("--apply", action="store_true", help="Actually apply the migration (default is dry-run)")
    args = parser.parse_args()

    if args.to_categoria not in VALID_CATEGORIAS:
        print(f"❌ Invalid --to-categoria. Must be one of {sorted(VALID_CATEGORIAS)}", file=sys.stderr)
        sys.exit(2)

    ssid = os.environ.get("SPREADSHEET_ID")
    if not ssid:
        print("❌ SPREADSHEET_ID env var not set.", file=sys.stderr)
        sys.exit(2)

    svc = _sheets.get_service()
    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"=== Migrate Categoria — {mode} ===\n")

    # 1. Find the source produto. Range now extends through column H to
    # pick up Preco_manual (G) and Preco_manual_data (H), which were added
    # by the WAC + manual override migration. If the columns are empty (no
    # override active), we still write them back as empty strings — that
    # keeps the new produto's row width consistent with the rest of the tab.
    produtos_rows = svc.spreadsheets().values().get(
        spreadsheetId=ssid, range="Produtos!A:H"
    ).execute().get("values", [])
    source_row = None
    source_index = None
    for i, r in enumerate(produtos_rows):
        if r and r[0] == args.from_id:
            source_row = r
            source_index = i + 1  # 1-based for sheet row number
            break
    if source_row is None:
        print(f"❌ Produto {args.from_id} not found in Produtos.")
        sys.exit(1)

    print(f"Source produto (row {source_index}):")
    print(f"  ID:           {source_row[0]}")
    print(f"  Nome:         {source_row[1] if len(source_row) > 1 else ''}")
    print(f"  Unidade:      {source_row[2] if len(source_row) > 2 else ''}")
    print(f"  Notas:        {source_row[3] if len(source_row) > 3 else ''}")
    print(f"  Relac.:       {source_row[4] if len(source_row) > 4 else ''}")
    print(f"  Marca pd.:    {source_row[5] if len(source_row) > 5 else ''}")
    print(f"  Preco_manual: {source_row[6] if len(source_row) > 6 else ''}")
    print(f"  Preco_data:   {source_row[7] if len(source_row) > 7 else ''}")

    current_cat = args.from_id.split("-", 1)[0] if "-" in args.from_id else ""
    if current_cat == args.to_categoria:
        print(f"\n⚠️  Already in categoria {args.to_categoria}. Nothing to do.")
        sys.exit(0)

    # 2. Decide on the new ID
    new_id = _next_id_for_categoria(svc, ssid, args.to_categoria)
    print(f"\nNew ID will be: {new_id}\n")

    # 3. Collect references
    compras_rows = svc.spreadsheets().values().get(
        spreadsheetId=ssid, range="Compras!A:Z"
    ).execute().get("values", [])
    compras_refs = [
        (i + 1, r) for i, r in enumerate(compras_rows[1:], start=1)
        if r and len(r) > 2 and r[2] == args.from_id
    ]
    print(f"Compras references: {len(compras_refs)}")
    for row_num, r in compras_refs:
        print(f"  Compras row {row_num + 1}: {r[:8]}")

    aliases_rows = svc.spreadsheets().values().get(
        spreadsheetId=ssid, range="Aliases!A:F"
    ).execute().get("values", [])
    aliases_refs = [
        (i + 1, r) for i, r in enumerate(aliases_rows[1:], start=1)
        if r and len(r) > 3 and r[3] == args.from_id
    ]
    print(f"\nAliases references: {len(aliases_refs)}")
    for row_num, r in aliases_refs:
        print(f"  Aliases row {row_num + 1}: {r}")

    embt_rows = svc.spreadsheets().values().get(
        spreadsheetId=ssid, range="Embalagens_Por_Tamanho!A:D"
    ).execute().get("values", [])
    embt_refs = [
        (i + 1, r) for i, r in enumerate(embt_rows[1:], start=1)
        if r and len(r) > 1 and r[1] == args.from_id
    ]
    print(f"\nEmbalagens_Por_Tamanho references: {len(embt_refs)}")
    for row_num, r in embt_refs:
        print(f"  Embalagens_Por_Tamanho row {row_num + 1}: {r}")

    # Receita_Ingredientes (col B = produto_id). Tab may not exist on
    # pre-migration spreadsheets — handle that quietly.
    ri_refs = []
    try:
        ri_rows = svc.spreadsheets().values().get(
            spreadsheetId=ssid, range="Receita_Ingredientes!A:F"
        ).execute().get("values", [])
        ri_refs = [
            (i + 1, r) for i, r in enumerate(ri_rows[1:], start=1)
            if r and len(r) > 1 and r[1] == args.from_id
        ]
    except Exception:
        # Tab not present yet — older schema with `Receita` (no receita_id col).
        # That one is keyed by produto_id in col A.
        try:
            ri_rows = svc.spreadsheets().values().get(
                spreadsheetId=ssid, range="Receita!A:D"
            ).execute().get("values", [])
            ri_refs = [
                (i + 1, r) for i, r in enumerate(ri_rows[1:], start=1)
                if r and len(r) > 0 and r[0] == args.from_id
            ]
        except Exception:
            ri_refs = []
    print(f"\nReceita_Ingredientes references: {len(ri_refs)}")
    for row_num, r in ri_refs:
        print(f"  Receita_Ingredientes row {row_num + 1}: {r}")

    if not args.apply:
        print("\n=== DRY-RUN: no changes written. Re-run with --apply to migrate. ===")
        sys.exit(0)

    # 4. APPLY
    print("\n=== APPLYING ===\n")

    # 4a. Create new produto row at the end of Produtos. We carry over
    # the manual price override (G/H) too — keeping it on the migrated id
    # is exactly what the user expects: the produto is the same physical
    # thing, only its categoria prefix changed.
    print(f"→ Inserting new Produtos row for {new_id}...")
    nome = source_row[1] if len(source_row) > 1 else ""
    unidade = source_row[2] if len(source_row) > 2 else ""
    notas = source_row[3] if len(source_row) > 3 else ""
    relac = source_row[4] if len(source_row) > 4 else ""
    marca_pd = source_row[5] if len(source_row) > 5 else ""
    preco_manual = source_row[6] if len(source_row) > 6 else ""
    preco_manual_data = source_row[7] if len(source_row) > 7 else ""

    next_row = len(produtos_rows) + 1
    svc.spreadsheets().values().update(
        spreadsheetId=ssid,
        range=f"Produtos!A{next_row}",
        valueInputOption="USER_ENTERED",
        body={"values": [[
            new_id, nome, unidade, notas, relac, marca_pd,
            preco_manual, preco_manual_data,
        ]]},
    ).execute()
    print(f"  ✓ {new_id} created.")

    # 4b. Update Compras references (col C, 0-indexed 2 → sheet col C)
    for row_num, _ in compras_refs:
        sheet_row = row_num + 1  # +1 because we sliced compras[1:] which starts at idx 1, then +1 for header
        svc.spreadsheets().values().update(
            spreadsheetId=ssid,
            range=f"Compras!C{sheet_row}",
            valueInputOption="USER_ENTERED",
            body={"values": [[new_id]]},
        ).execute()
        print(f"  ✓ Compras!C{sheet_row} updated.")

    # 4c. Update Aliases references (col D)
    for row_num, _ in aliases_refs:
        sheet_row = row_num + 1
        svc.spreadsheets().values().update(
            spreadsheetId=ssid,
            range=f"Aliases!D{sheet_row}",
            valueInputOption="USER_ENTERED",
            body={"values": [[new_id]]},
        ).execute()
        print(f"  ✓ Aliases!D{sheet_row} updated.")

    # 4d. Update Embalagens_Por_Tamanho references (col B)
    for row_num, _ in embt_refs:
        sheet_row = row_num + 1
        svc.spreadsheets().values().update(
            spreadsheetId=ssid,
            range=f"Embalagens_Por_Tamanho!B{sheet_row}",
            valueInputOption="USER_ENTERED",
            body={"values": [[new_id]]},
        ).execute()
        print(f"  ✓ Embalagens_Por_Tamanho!B{sheet_row} updated.")

    # 4d-bis. Update Receita_Ingredientes references. New schema has
    # produto_id at col B; legacy `Receita` tab has it at col A.
    ri_uses_new_schema = True
    try:
        svc.spreadsheets().values().get(
            spreadsheetId=ssid, range="Receita_Ingredientes!A1:A1"
        ).execute()
    except Exception:
        ri_uses_new_schema = False
    for row_num, _ in ri_refs:
        sheet_row = row_num + 1
        if ri_uses_new_schema:
            tab, col = "Receita_Ingredientes", "B"
        else:
            tab, col = "Receita", "A"
        svc.spreadsheets().values().update(
            spreadsheetId=ssid,
            range=f"{tab}!{col}{sheet_row}",
            valueInputOption="USER_ENTERED",
            body={"values": [[new_id]]},
        ).execute()
        print(f"  ✓ {tab}!{col}{sheet_row} updated.")

    # 4e. Clear the old Produtos row (full A:H so G/H aren't orphaned).
    print(f"\n→ Clearing old Produtos row {source_index} ({args.from_id})...")
    svc.spreadsheets().values().clear(
        spreadsheetId=ssid,
        range=f"Produtos!A{source_index}:H{source_index}",
    ).execute()
    print(f"  ✓ Old row cleared.")

    print(f"\n✅ Migration complete: {args.from_id} → {new_id}")
    print("Heads up: re-run the app and the bot might still have the old ID cached for ~30s.")


if __name__ == "__main__":
    main()
