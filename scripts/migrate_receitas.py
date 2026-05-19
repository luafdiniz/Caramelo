"""
Migrate the spreadsheet from a single-receita schema to the new receitas-list
schema.

Old schema (one flat list of ingredients, single recipe):
    Receita: produto_id | nome | qtde | unidade

New schema:
    Receitas:             receita_id | nome | padrao | notas
    Receita_Ingredientes: receita_id | produto_id | nome | qtde | unidade | componente
    Tamanhos:             adds a new column I `receita_id` (optional, empty = use padrao)

Usage:
    # Dry-run (default) — shows everything that would change, no writes:
    python scripts/migrate_receitas.py

    # Apply for real (after reviewing the dry-run output):
    python scripts/migrate_receitas.py --apply

What it does:
    1. Verifies the Receita tab exists and Receitas does NOT (refuses to re-run).
    2. Reads the legacy Receita rows and classifies each ingredient into one
       of two componentes: "calda" or "massa".
       Rule: nome (case-insensitive) starts with "açúcar" / "acucar"  OR
             contains "água" / "agua"  -> "calda"
             everything else            -> "massa"
       The classification is printed before any write so the user can sanity
       check it.
    3. Creates the Receitas tab with one row:  REC-001 | Tradicional | TRUE | ""
    4. Creates the Receita_Ingredientes tab and writes each legacy row to it
       with receita_id=REC-001 and its assigned componente.
    5. Renames the original `Receita` tab to `_Receita_old` (does NOT delete,
       so rollback stays trivial).
    6. Adds the `receita_id` header to Tamanhos column I (values stay empty —
       every existing tamanho falls back to the padrao at calc time).

Required env vars (same as the bot / other scripts):
    SPREADSHEET_ID, GOOGLE_SERVICE_ACCOUNT_JSON (path or JSON content)
"""

from __future__ import annotations
import argparse
import os
import sys
import unicodedata
from pathlib import Path

# Make `bot/lib/sheets.py` importable.
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "bot"))

from bot.lib import sheets as _sheets  # noqa: E402


DEFAULT_RECEITA_ID = "REC-001"
DEFAULT_RECEITA_NOME = "Tradicional"

RECEITAS_HEADERS = ["receita_id", "nome", "padrao", "notas"]
INGREDIENTES_HEADERS = ["receita_id", "produto_id", "nome", "qtde", "unidade", "componente"]


def _strip_accents(s: str) -> str:
    """Remove diacritics so 'água' and 'agua' compare equal."""
    return "".join(
        c for c in unicodedata.normalize("NFD", s or "")
        if unicodedata.category(c) != "Mn"
    )


def classify_componente(nome: str) -> str:
    """
    Assign 'calda' or 'massa' to an ingredient by its name.

    Rule (matches what's printed in the dry-run):
      - starts with "açúcar"/"acucar" → calda  (caramelizes into the syrup)
      - contains "água"/"agua"        → calda  (only the calda uses water)
      - everything else                → massa
    """
    n_lower = (nome or "").strip().lower()
    n_noaccents = _strip_accents(n_lower)

    if n_noaccents.startswith("acucar"):
        return "calda"
    if "agua" in n_noaccents:
        return "calda"
    return "massa"


def _sheet_titles(svc, ssid: str) -> list[str]:
    meta = svc.spreadsheets().get(spreadsheetId=ssid).execute()
    return [s["properties"]["title"] for s in meta["sheets"]]


def _sheet_id(svc, ssid: str, title: str) -> int:
    meta = svc.spreadsheets().get(spreadsheetId=ssid).execute()
    for s in meta["sheets"]:
        if s["properties"]["title"] == title:
            return s["properties"]["sheetId"]
    raise ValueError(f"Sheet {title!r} not found")


def _add_sheet(svc, ssid: str, title: str) -> int:
    """Create a new tab and return its sheetId."""
    resp = svc.spreadsheets().batchUpdate(
        spreadsheetId=ssid,
        body={"requests": [{"addSheet": {"properties": {"title": title}}}]},
    ).execute()
    return resp["replies"][0]["addSheet"]["properties"]["sheetId"]


def _rename_sheet(svc, ssid: str, old_title: str, new_title: str) -> None:
    sid = _sheet_id(svc, ssid, old_title)
    svc.spreadsheets().batchUpdate(
        spreadsheetId=ssid,
        body={"requests": [{
            "updateSheetProperties": {
                "properties": {"sheetId": sid, "title": new_title},
                "fields": "title",
            }
        }]},
    ).execute()


def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--apply", action="store_true",
        help="Actually write the changes (default is dry-run).",
    )
    args = parser.parse_args()

    ssid = os.environ.get("SPREADSHEET_ID")
    if not ssid:
        print("ERROR: SPREADSHEET_ID env var not set.", file=sys.stderr)
        sys.exit(2)

    svc = _sheets.get_service()
    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"=== Migrate Receitas — {mode} ===\n")

    # 1. Preconditions: legacy Receita must exist; new Receitas must NOT.
    titles = _sheet_titles(svc, ssid)
    if "Receita" not in titles:
        print("ERROR: tab 'Receita' not found. Nothing to migrate.", file=sys.stderr)
        sys.exit(1)
    if "Receitas" in titles:
        print(
            "ERROR: tab 'Receitas' already exists. Refusing to re-run the migration.\n"
            "If you need to redo it: rename 'Receitas' and 'Receita_Ingredientes' out of the way,\n"
            "rename '_Receita_old' back to 'Receita', and run this script again.",
            file=sys.stderr,
        )
        sys.exit(1)
    if "Receita_Ingredientes" in titles:
        print(
            "ERROR: tab 'Receita_Ingredientes' already exists but 'Receitas' does not. "
            "The sheet is in a half-migrated state — fix it manually first.",
            file=sys.stderr,
        )
        sys.exit(1)

    # 2. Read the legacy Receita rows.
    legacy = svc.spreadsheets().values().get(
        spreadsheetId=ssid, range="Receita!A2:D",
        valueRenderOption="UNFORMATTED_VALUE",
    ).execute().get("values", [])

    if not legacy:
        print("Legacy Receita tab is empty — there's nothing to migrate.")
        print("This script will still create Receitas + Receita_Ingredientes (empty)")
        print("and rename Receita to _Receita_old if you pass --apply.")

    # Normalize rows to exactly 4 columns: produto_id | nome | qtde | unidade
    legacy = [(r + [""] * 4)[:4] for r in legacy if r and (r + [""])[0].strip()]

    # 3. Classify every row and report.
    print(f"Found {len(legacy)} ingrediente row(s) in Receita.\n")
    print("Classification (rule: starts with 'açúcar' OR contains 'água' → calda; else massa):\n")
    print(f"  {'produto_id':<10} {'nome':<28} {'qtde':>8} {'unidade':<8} {'componente':<8}")
    print(f"  {'-'*10} {'-'*28} {'-'*8} {'-'*8} {'-'*8}")
    classified = []
    for r in legacy:
        produto_id, nome, qtde, unidade = r[0], r[1], r[2], r[3]
        comp = classify_componente(nome)
        classified.append((produto_id, nome, qtde, unidade, comp))
        # Truncate nome display so the table stays aligned, full value is still written.
        nome_disp = (nome[:27] + "…") if len(nome) > 28 else nome
        qtde_disp = str(qtde) if qtde != "" else ""
        print(f"  {produto_id:<10} {nome_disp:<28} {qtde_disp:>8} {unidade:<8} {comp:<8}")

    n_calda = sum(1 for c in classified if c[4] == "calda")
    n_massa = sum(1 for c in classified if c[4] == "massa")
    print(f"\nSummary: {n_calda} calda + {n_massa} massa = {len(classified)} total\n")

    # 4. Plan summary
    print("Planned changes:")
    print(f"  - Create tab 'Receitas' with header + 1 row: "
          f"{DEFAULT_RECEITA_ID} | {DEFAULT_RECEITA_NOME} | TRUE | (empty)")
    print(f"  - Create tab 'Receita_Ingredientes' with header + {len(classified)} row(s)")
    print(f"  - Rename 'Receita' to '_Receita_old' (kept as rollback)")
    print(f"  - Add header 'receita_id' in Tamanhos!I1 (existing values stay empty)")

    if not args.apply:
        print(
            "\n=== DRY-RUN: no changes written. ===\n"
            "Review the classification above. If it looks right, re-run with --apply.\n"
            "If something's miscategorized, fix the rule in `classify_componente()` "
            "(or just edit Receita_Ingredientes manually after migration)."
        )
        sys.exit(0)

    # Belt-and-braces: confirmation prompt even with --apply, since this
    # rewrites tab structure. Skip if stdin isn't a tty (CI / scripted).
    if sys.stdin.isatty():
        ans = input("\nType 'yes' to proceed: ").strip().lower()
        if ans != "yes":
            print("Aborted.")
            sys.exit(0)

    print("\n=== APPLYING ===\n")

    # 5a. Create Receitas
    print("→ Creating tab 'Receitas'…")
    _add_sheet(svc, ssid, "Receitas")
    svc.spreadsheets().values().update(
        spreadsheetId=ssid, range="Receitas!A1",
        valueInputOption="USER_ENTERED",
        body={"values": [RECEITAS_HEADERS]},
    ).execute()
    svc.spreadsheets().values().update(
        spreadsheetId=ssid, range="Receitas!A2",
        valueInputOption="USER_ENTERED",
        body={"values": [[DEFAULT_RECEITA_ID, DEFAULT_RECEITA_NOME, True, ""]]},
    ).execute()
    print("  ✓ Receitas created with REC-001 (Tradicional, padrao=TRUE).")

    # 5b. Create Receita_Ingredientes
    print("→ Creating tab 'Receita_Ingredientes'…")
    _add_sheet(svc, ssid, "Receita_Ingredientes")
    svc.spreadsheets().values().update(
        spreadsheetId=ssid, range="Receita_Ingredientes!A1",
        valueInputOption="USER_ENTERED",
        body={"values": [INGREDIENTES_HEADERS]},
    ).execute()
    if classified:
        body_rows = [
            [DEFAULT_RECEITA_ID, produto_id, nome, qtde, unidade, componente]
            for (produto_id, nome, qtde, unidade, componente) in classified
        ]
        svc.spreadsheets().values().update(
            spreadsheetId=ssid, range="Receita_Ingredientes!A2",
            valueInputOption="USER_ENTERED",
            body={"values": body_rows},
        ).execute()
    print(f"  ✓ Receita_Ingredientes created with {len(classified)} ingrediente row(s).")

    # 5c. Rename Receita to _Receita_old (preserve rollback path)
    print("→ Renaming 'Receita' to '_Receita_old'…")
    _rename_sheet(svc, ssid, "Receita", "_Receita_old")
    print("  ✓ Renamed.")

    # 5d. Add header in Tamanhos!I1
    print("→ Adding 'receita_id' header to Tamanhos!I1…")
    svc.spreadsheets().values().update(
        spreadsheetId=ssid, range="Tamanhos!I1",
        valueInputOption="USER_ENTERED",
        body={"values": [["receita_id"]]},
    ).execute()
    print("  ✓ Header added (existing rows keep empty receita_id and fall back to padrao).")

    print("\n=== DONE ===\n")
    print("Next steps:")
    print("  1. Reload the Streamlit app — the cache will refresh in ~30s, or click 🔄 Atualizar.")
    print("  2. Open the new 📜 Receitas page to review/edit the migrated recipe.")
    print("  3. Tamanhos still use the padrao (REC-001) by default. Pick a different")
    print("     receita per tamanho via the 'Receita' selectbox in the edit form.")
    print("  4. The legacy data lives in '_Receita_old' — keep it around for a while as a backup.")


if __name__ == "__main__":
    main()
