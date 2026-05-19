"""
Consolidate multiple Compras into one, updating the kept Compra's total to
reflect what you actually paid (sum of all merged purchases), then optionally
delete now-orphan Produtos.

Real-world use case: same receipt had pote + tampa + lacre, you decided to
treat pote+tampa as a single "pote" and discard the lacre. You still paid
the full amount, so the kept Compra absorbs the total spend; the discarded
purchases (and their orphan produtos) get removed.

Usage:
    # Dry-run (default) — review everything that would change:
    python scripts/consolidate_compras.py \\
        --keep-compra C-047 --new-total 81.14 \\
        --merge-compras C-046 C-048 \\
        --delete-produtos EMB-021 EMB-023

    # Apply for real (will prompt for confirmation):
    python scripts/consolidate_compras.py ... --apply

Behavior:
  1. Verifies all referenced Compras and Produtos exist.
  2. Computes the sum of preco_total across keep + merge as a sanity check
     (just for display; the new total comes from --new-total, not the sum).
  3. Lists where the to-be-deleted Produtos are referenced (other Compras,
     Aliases, Embalagens_Por_Tamanho) so you can decide.
  4. If a to-be-deleted Produto is still referenced in Compras OTHER than
     the merged ones, OR in Embalagens_Por_Tamanho, the script ABORTS with
     an error — you have to clean those refs first.
  5. With --apply:
       a. Update keep Compra's preco_total to --new-total (recompute
          preco_unitario = new_total / total_unidades).
       b. Clear merged Compras rows.
       c. Clear orphan Produtos rows.
       d. Clear Aliases that pointed to the orphan Produtos.

Required env vars: SPREADSHEET_ID, GOOGLE_SERVICE_ACCOUNT_JSON
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


COMPRAS_RANGE = "Compras!A:Z"
PRODUTOS_RANGE = "Produtos!A:F"
ALIASES_RANGE = "Aliases!A:F"
EMBT_RANGE = "Embalagens_Por_Tamanho!A:D"


def _find_row(rows, col_idx, value):
    """Return (sheet_row_number, row_list) for first row where col_idx == value, or (None, None)."""
    for i, r in enumerate(rows):
        if r and len(r) > col_idx and r[col_idx] == value:
            return i + 1, r
    return None, None


def _float(v) -> float:
    if v is None or v == "":
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    # Strip "R$", spaces, and convert pt-BR decimal comma to dot.
    s = str(v).strip().replace("R$", "").replace(" ", "").replace(" ", "")
    # Handle pt-BR thousand separator: "1.234,56" → "1234.56"
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    else:
        s = s.replace(",", ".")
    try:
        return float(s)
    except (TypeError, ValueError):
        return 0.0


def _read_unformatted(svc, ssid, rng):
    """Read a range with UNFORMATTED_VALUE so currency cells come back as floats, not 'R$ X,YZ' strings."""
    return svc.spreadsheets().values().get(
        spreadsheetId=ssid, range=rng,
        valueRenderOption="UNFORMATTED_VALUE",
    ).execute().get("values", [])


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--keep-compra", required=True, help="Compra ID that stays (e.g. C-047)")
    parser.add_argument("--new-total", required=True, type=float, help="New preco_total for the kept compra (e.g. 81.14)")
    parser.add_argument("--merge-compras", nargs="+", default=[], help="Compra IDs to delete (e.g. C-046 C-048)")
    parser.add_argument("--delete-produtos", nargs="+", default=[], help="Produto IDs to delete after merging (e.g. EMB-021 EMB-023)")
    parser.add_argument(
        "--also-remove-from-tamanhos", action="store_true",
        help="Also remove the to-be-deleted produtos from any Embalagens_Por_Tamanho they appear in. "
             "Without this flag, the script aborts if such refs exist."
    )
    parser.add_argument("--apply", action="store_true", help="Apply changes (default is dry-run)")
    args = parser.parse_args()

    ssid = os.environ.get("SPREADSHEET_ID")
    if not ssid:
        print("❌ SPREADSHEET_ID env var not set.", file=sys.stderr)
        sys.exit(2)

    svc = _sheets.get_service()
    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"=== Consolidate Compras — {mode} ===\n")

    # --- Read all relevant tabs once. UNFORMATTED_VALUE so currency cells
    # come back as floats, not "R$ X,YZ" strings.
    compras = _read_unformatted(svc, ssid, COMPRAS_RANGE)
    produtos = _read_unformatted(svc, ssid, PRODUTOS_RANGE)
    aliases = _read_unformatted(svc, ssid, ALIASES_RANGE)
    embt = _read_unformatted(svc, ssid, EMBT_RANGE)

    # Compras header (row 1) — figure out column indices for the fields we touch.
    # Standard schema: A=id, B=data, C=produto_id, D=fornecedor_id, E=marca,
    # F=qtde_embalagens, G=unidades_por_embalagem, H=total_unidades,
    # I=preco_total, J=preco_unitario, K=notas
    COL_ID = 0
    COL_PRODUTO = 2
    COL_QTDE = 5
    COL_UNID_EMB = 6
    COL_TOTAL_UNID = 7
    COL_PRECO_TOTAL = 8
    COL_PRECO_UNIT = 9

    keep_row_n, keep_row = _find_row(compras[1:], COL_ID, args.keep_compra)
    if keep_row_n is None:
        print(f"❌ Compra to keep not found: {args.keep_compra}")
        sys.exit(1)
    keep_row_n += 1  # +1 because compras[1:] skipped header

    merge_targets = []
    for cid in args.merge_compras:
        rn, r = _find_row(compras[1:], COL_ID, cid)
        if rn is None:
            print(f"❌ Compra to merge not found: {cid}")
            sys.exit(1)
        merge_targets.append((rn + 1, r))

    # --- Show keep + merge summary
    keep_preco = _float(keep_row[COL_PRECO_TOTAL] if len(keep_row) > COL_PRECO_TOTAL else 0)
    print(f"KEEP — Compra {args.keep_compra} (row {keep_row_n}):")
    print(f"  Produto: {keep_row[COL_PRODUTO] if len(keep_row) > COL_PRODUTO else ''}")
    print(f"  Preço atual: R$ {keep_preco:.2f}")
    print(f"  Novo preço:  R$ {args.new_total:.2f}")
    qtde = _float(keep_row[COL_QTDE] if len(keep_row) > COL_QTDE else 1) or 1
    unid_emb = _float(keep_row[COL_UNID_EMB] if len(keep_row) > COL_UNID_EMB else 1) or 1
    total_unid = qtde * unid_emb
    new_preco_unit = args.new_total / total_unid if total_unid else 0
    print(f"  Total unidades: {total_unid:g}  →  novo preço unitário: R$ {new_preco_unit:.4f}\n")

    merge_sum = 0.0
    print(f"MERGE (will be deleted): {len(merge_targets)} compras")
    for rn, r in merge_targets:
        p = _float(r[COL_PRECO_TOTAL] if len(r) > COL_PRECO_TOTAL else 0)
        merge_sum += p
        print(f"  row {rn}: {r[COL_ID]} — produto {r[COL_PRODUTO] if len(r) > COL_PRODUTO else '?'} — R$ {p:.2f}")
    print(f"  Soma dos merges: R$ {merge_sum:.2f}")
    print(f"  Soma keep + merges: R$ {keep_preco + merge_sum:.2f}")
    if abs((keep_preco + merge_sum) - args.new_total) > 0.01:
        print(f"  ⚠️  Soma diverge do --new-total (R$ {args.new_total:.2f}). Confirma que era essa a intenção.")
    print()

    # --- Check orphan produto references
    merge_compra_ids = {cid for cid, _ in [(r[COL_ID], r) for _, r in merge_targets]}
    # ^ same as args.merge_compras but verified

    print(f"DELETE PRODUTOS: {len(args.delete_produtos)}")
    abort = False
    produto_action_rows = {}  # produto_id -> sheet row number
    embt_refs_to_clear = []  # list of (sheet_row_number, row_data) to clear if --also-remove-from-tamanhos
    for pid in args.delete_produtos:
        rn, r = _find_row(produtos[1:], 0, pid)
        if rn is None:
            print(f"  ❌ Produto não encontrado: {pid}")
            abort = True
            continue
        rn += 1
        produto_action_rows[pid] = rn
        print(f"  Produtos row {rn}: {pid} — {r[1] if len(r) > 1 else ''}")

        # Refs in Compras (other than the merged ones)
        offending_compras = [
            (i + 2, c) for i, c in enumerate(compras[1:])
            if c and len(c) > COL_PRODUTO and c[COL_PRODUTO] == pid
            and c[COL_ID] not in args.merge_compras and c[COL_ID] != args.keep_compra
        ]
        if offending_compras:
            print(f"    ❌ Ainda referenciado em {len(offending_compras)} outras Compras (não-mescladas):")
            for rn2, r2 in offending_compras:
                print(f"      row {rn2}: {r2[COL_ID]}")
            abort = True

        # Refs in Embalagens_Por_Tamanho (col B = produto_id)
        embt_refs = [
            (i + 2, e) for i, e in enumerate(embt[1:])
            if e and len(e) > 1 and e[1] == pid
        ]
        if embt_refs:
            if args.also_remove_from_tamanhos:
                print(f"    ⚠️  Referenciado em Embalagens_Por_Tamanho ({len(embt_refs)} linhas) — será limpo:")
                for rn2, r2 in embt_refs:
                    print(f"      row {rn2}: tamanho {r2[0]} (será removido)")
                    embt_refs_to_clear.append(rn2)
            else:
                print(f"    ❌ Referenciado em Embalagens_Por_Tamanho ({len(embt_refs)} linhas):")
                for rn2, r2 in embt_refs:
                    print(f"      row {rn2}: tamanho {r2[0]}")
                print(f"      💡 Rode de novo com --also-remove-from-tamanhos pra tirar essas embalagens dos tamanhos.")
                abort = True

        # Aliases that resolved to this produto (will be deleted along with the produto)
        alias_refs = [
            (i + 2, a) for i, a in enumerate(aliases[1:])
            if a and len(a) > 3 and a[3] == pid
        ]
        if alias_refs:
            print(f"    Aliases que serão apagados ({len(alias_refs)}):")
            for rn2, r2 in alias_refs:
                print(f"      row {rn2}: {r2[0]} — \"{r2[2] if len(r2) > 2 else ''}\"")

    if abort:
        print("\n❌ Abort: existem referências ativas que precisam ser limpas antes.")
        sys.exit(1)

    if not args.apply:
        print("\n=== DRY-RUN: nada foi escrito. Rode com --apply pra commitar. ===")
        sys.exit(0)

    confirm = input("\nDigite 'sim' pra aplicar as mudanças: ").strip().lower()
    if confirm != "sim":
        print("Cancelado.")
        sys.exit(0)

    print("\n=== APPLYING ===\n")

    # 1. Update keep compra: I (preco_total), J (preco_unitario)
    svc.spreadsheets().values().update(
        spreadsheetId=ssid,
        range=f"Compras!I{keep_row_n}:J{keep_row_n}",
        valueInputOption="USER_ENTERED",
        body={"values": [[args.new_total, new_preco_unit]]},
    ).execute()
    print(f"  ✓ Compras!I{keep_row_n}:J{keep_row_n} updated to R$ {args.new_total:.2f} / R$ {new_preco_unit:.4f}")

    # 2. Clear merged compras
    for rn, r in merge_targets:
        svc.spreadsheets().values().clear(
            spreadsheetId=ssid,
            range=f"Compras!A{rn}:K{rn}",
        ).execute()
        print(f"  ✓ Compras row {rn} ({r[COL_ID]}) cleared")

    # 3. Clear aliases tied to deleted produtos
    for pid in args.delete_produtos:
        for i, a in enumerate(aliases[1:]):
            if a and len(a) > 3 and a[3] == pid:
                rn = i + 2
                svc.spreadsheets().values().clear(
                    spreadsheetId=ssid,
                    range=f"Aliases!A{rn}:F{rn}",
                ).execute()
                print(f"  ✓ Aliases row {rn} cleared (was → {pid})")

    # 4. Clear Embalagens_Por_Tamanho refs for produtos being deleted
    for rn in embt_refs_to_clear:
        svc.spreadsheets().values().clear(
            spreadsheetId=ssid,
            range=f"Embalagens_Por_Tamanho!A{rn}:D{rn}",
        ).execute()
        print(f"  ✓ Embalagens_Por_Tamanho row {rn} cleared")

    # 5. Clear produtos rows
    for pid, rn in produto_action_rows.items():
        svc.spreadsheets().values().clear(
            spreadsheetId=ssid,
            range=f"Produtos!A{rn}:F{rn}",
        ).execute()
        print(f"  ✓ Produtos row {rn} ({pid}) cleared")

    print(f"\n✅ Consolidation complete.")
    print("Heads up: o cache do app cai em ~30s. Dá Atualizar na página Insumos / Compras pra confirmar.")


if __name__ == "__main__":
    main()
