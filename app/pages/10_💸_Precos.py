"""Tabela de preços B2C/B2B com faixas por volume."""

from __future__ import annotations

import os
import sys
import streamlit as st
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.auth import require_auth
from lib import data
from lib.ui import setup_page, brl


setup_page("Preços", icon="💸")
require_auth()

st.title("💸 Tabela de Preços")
st.caption(
    "Define o preço por tamanho × tipo de cliente × faixa de volume (qtde mínima). "
    "O resolvedor escolhe a faixa com **maior `qtde_min` que ainda seja ≤ qtde da venda**."
)


if not data._has_sheet("Precos"):
    st.warning(
        "A aba **Precos** ainda não existe. "
        "Rode `python scripts/migrate_clientes_vendas.py --apply`."
    )
    st.stop()


precos = data.get_precos()
tamanhos = data.get_tamanhos()
tam_map = dict(zip(tamanhos["id"], tamanhos["nome"])) if not tamanhos.empty else {}


# --- Add new faixa ---
with st.expander("➕ Nova faixa de preço", expanded=False):
    if tamanhos.empty:
        st.info("Cadastre tamanhos primeiro.")
    else:
        with st.form("new_preco", clear_on_submit=True):
            tam_opts = {f"{r['id']} — {r['nome']}": r["id"] for _, r in tamanhos.iterrows()}
            tam_label = st.selectbox("Tamanho", list(tam_opts.keys()))
            tamanho_id = tam_opts[tam_label]
            c1, c2, c3 = st.columns(3)
            with c1:
                new_tipo = st.selectbox("Tipo de cliente", ["B2C", "B2B"])
            with c2:
                new_qtde_min = st.number_input("Qtde mínima", min_value=1, value=1, step=1)
            with c3:
                new_preco = st.number_input("Preço unitário (R$)", min_value=0.0, value=0.0, step=1.0)
            new_notas = st.text_input("Notas")

            if st.form_submit_button("➕ Cadastrar faixa", type="primary"):
                if new_preco <= 0:
                    st.error("Preço precisa ser maior que zero.")
                else:
                    # Avoid duplicate (tamanho_id, tipo, qtde_min)
                    if not precos.empty:
                        dup = precos[
                            (precos["tamanho_id"] == tamanho_id)
                            & (precos["tipo_cliente"].astype(str).str.upper() == new_tipo)
                            & (precos["qtde_min"] == new_qtde_min)
                        ]
                        if not dup.empty:
                            st.error(f"Já existe uma faixa pra {tamanho_id} / {new_tipo} / qtde ≥ {new_qtde_min}. Edita ela na tabela.")
                            st.stop()
                    try:
                        data.get_service().spreadsheets().values().append(
                            spreadsheetId=data._spreadsheet_id(),
                            range="Precos!A1",
                            valueInputOption="USER_ENTERED",
                            body={"values": [[
                                tamanho_id, new_tipo, int(new_qtde_min),
                                float(new_preco), new_notas.strip(),
                            ]]},
                        ).execute()
                        data.invalidate_cache()
                        st.success(f"✅ Faixa adicionada: {tamanho_id} {new_tipo} qtde ≥ {new_qtde_min} → {brl(new_preco)}")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erro: {e}")


if precos.empty:
    st.info(
        "Nenhuma faixa cadastrada ainda. Enquanto não cadastrar, o resolvedor "
        "usa `Tamanhos.preco_venda` como fallback (preço B2C de balcão)."
    )
    st.stop()


disp = precos.copy()
disp["Tamanho"] = disp["tamanho_id"].map(lambda t: f"{t} — {tam_map.get(t, t)}")
# We sort for display but reset_index so iloc and original index don't
# diverge — the save path looks up sheet rows by (tamanho_id, tipo_cliente,
# qtde_min) at write time anyway, but a clean index avoids accidentally
# trusting `orig_row.name` if we ever revert.
disp = disp.sort_values(["tamanho_id", "tipo_cliente", "qtde_min"]).reset_index(drop=True)

# Toggle: view (st.table) vs edit (data_editor).
prc_edit_key = "precos_edit_mode"
if prc_edit_key not in st.session_state:
    st.session_state[prc_edit_key] = False
prc_edit_active = st.session_state[prc_edit_key]

view = pd.DataFrame({
    "Tamanho": disp["Tamanho"].values,
    "Tipo": disp["tipo_cliente"].values,
    "Qtde mín.": disp["qtde_min"].values.astype(int),
    "Preço unit.": disp["preco_unit"].values,
    "Notas": disp["notas"].values,
    "Excluir": [False] * len(disp),
})

if not prc_edit_active:
    # --- VIEW MODE ---
    view_disp = view.drop(columns=["Excluir"]).copy()
    view_disp["Preço unit."] = view_disp["Preço unit."].apply(lambda v: brl(float(v)) if pd.notna(v) else "—")
    st.table(view_disp.set_index("Tamanho"))
    if st.button("✏️ Editar tabela", key="precos_edit_btn"):
        st.session_state[prc_edit_key] = True
        st.rerun()
    st.stop()

st.info("✏️ Modo de edição **ativo**.")
if st.button("✖ Cancelar edição", key="precos_cancel_btn"):
    st.session_state[prc_edit_key] = False
    st.rerun()

edited = st.data_editor(
    view, hide_index=True, use_container_width=True, num_rows="fixed",
    key="precos_editor",
    column_config={
        "Tamanho": st.column_config.TextColumn("Tamanho", disabled=True),
        "Tipo": st.column_config.TextColumn("Tipo", disabled=True,
                                            help="Pra mudar tipo, exclui e cadastra de novo."),
        "Qtde mín.": st.column_config.NumberColumn("Qtde mín.", min_value=1, step=1),
        "Preço unit.": st.column_config.NumberColumn("Preço unit.", min_value=0.0, format="R$ %.2f"),
        "Excluir": st.column_config.CheckboxColumn("Excluir"),
    },
)

# Diff against original.
#
# Important: we identify each row by its (tamanho_id, tipo_cliente,
# qtde_min) **before edit**, NOT by its DataFrame index. The Precos tab can
# legitimately have blank rows in the middle (someone cleared a row in the
# spreadsheet), and `disp.iloc[i].name + 2` would land on the wrong sheet
# row in that case. We resolve the actual sheet row at save time by
# scanning Precos!A:C for the original key.
changes = []
deletions = []
for i, row in edited.iterrows():
    orig = view.iloc[i]
    orig_row = disp.iloc[i]  # has tamanho_id, tipo_cliente, qtde_min
    key = {
        "tamanho_id": str(orig_row["tamanho_id"]),
        "tipo_cliente": str(orig_row["tipo_cliente"]),
        "qtde_min_original": int(orig_row["qtde_min"]),
    }
    if bool(row["Excluir"]):
        deletions.append({
            **key,
            "label": f"{orig['Tamanho']} {orig['Tipo']} qtde≥{orig['Qtde mín.']}",
        })
        continue
    if (int(row["Qtde mín."]) != int(orig["Qtde mín."])
        or abs(float(row["Preço unit."]) - float(orig["Preço unit."])) > 0.005
        or str(row["Notas"] or "").strip() != str(orig["Notas"] or "").strip()):
        changes.append({
            **key,
            "qtde_min": int(row["Qtde mín."]),
            "preco": float(row["Preço unit."]),
            "notas": str(row["Notas"] or "").strip(),
        })


def _find_preco_sheet_row(service, ssid: str, tamanho_id: str, tipo_cliente: str, qtde_min: int) -> int | None:
    """Resolve the 1-indexed Precos sheet row for a (tamanho_id, tipo_cliente,
    qtde_min) tuple. Returns None if no row matches.

    We scan A:C directly (with UNFORMATTED_VALUE so qtde_min comes back as a
    number) instead of trusting the DataFrame index — this is the robust
    alternative to the old `iloc.name + 2` that breaks on blank rows.
    """
    rows = service.spreadsheets().values().get(
        spreadsheetId=ssid, range="Precos!A:C",
        valueRenderOption="UNFORMATTED_VALUE",
    ).execute().get("values", [])
    for i, r in enumerate(rows[1:], start=2):  # +1 header, +1 for 1-indexed
        if not r or len(r) < 3:
            continue
        try:
            r_qmin = int(r[2])
        except (TypeError, ValueError):
            continue
        if (
            str(r[0]) == tamanho_id
            and str(r[1]).upper() == tipo_cliente.upper()
            and r_qmin == qtde_min
        ):
            return i
    return None


# --- C5: Duplicate detection on the edited rows (compute before showing save).
# Catches the case where someone edits the qtde_min of one row into a value
# that already exists for another (tamanho_id, tipo_cliente) — the create
# path already guards this, edit didn't.
duplicate_warnings: list[str] = []
combo_counts: dict[tuple[str, str, int], int] = {}
for i, row in edited.iterrows():
    if bool(row["Excluir"]):
        continue
    orig_row = disp.iloc[i]
    key = (str(orig_row["tamanho_id"]), str(orig_row["tipo_cliente"]).upper(), int(row["Qtde mín."]))
    combo_counts[key] = combo_counts.get(key, 0) + 1
for (tid, tipo, qmin), count in combo_counts.items():
    if count > 1:
        nome = tam_map.get(tid, tid)
        duplicate_warnings.append(f"{tid} — {nome} / {tipo} / qtde ≥ {qmin}")

# --- C6: B2B faixa more expensive than B2C for the same (tamanho_id,
# qtde_min). Soft warning only — there can be legitimate reasons (split
# delivery fee absorbed into the B2B unit price, etc), but in the common
# case this is a typo we want to surface.
b2c_b2b_warnings: list[str] = []
edited_for_check = edited.copy()
edited_for_check["_tamanho_id"] = [str(disp.iloc[i]["tamanho_id"]) for i in edited_for_check.index]
edited_for_check["_tipo"] = [str(disp.iloc[i]["tipo_cliente"]).upper() for i in edited_for_check.index]
# Index the B2C rows so we can compare each B2B row to the matching B2C one
# at the same (tamanho_id, qtde_min). Missing B2C is fine — no comparison.
b2c_index: dict[tuple[str, int], float] = {}
for _, r in edited_for_check.iterrows():
    if bool(r["Excluir"]):
        continue
    if r["_tipo"] == "B2C":
        b2c_index[(r["_tamanho_id"], int(r["Qtde mín."]))] = float(r["Preço unit."])
for _, r in edited_for_check.iterrows():
    if bool(r["Excluir"]):
        continue
    if r["_tipo"] != "B2B":
        continue
    matching_b2c = b2c_index.get((r["_tamanho_id"], int(r["Qtde mín."])))
    if matching_b2c is not None and float(r["Preço unit."]) > matching_b2c + 0.005:
        nome = tam_map.get(r["_tamanho_id"], r["_tamanho_id"])
        b2c_b2b_warnings.append(
            f"{r['_tamanho_id']} — {nome} qtde ≥ {int(r['Qtde mín.'])}: "
            f"B2B {brl(float(r['Preço unit.']))} > B2C {brl(matching_b2c)}"
        )

has = bool(changes or deletions)
if has:
    bullets = []
    if changes:
        bullets.append(f"✏️ {len(changes)} edição(ões)")
    if deletions:
        bullets.append(f"🗑️ {len(deletions)} exclusão(ões)")
    st.caption("Alterações pendentes: " + " · ".join(bullets))

if duplicate_warnings:
    # Hard block — saving these would create exactly the kind of duplicates
    # the resolver can't disambiguate.
    st.error(
        "❌ Há combinações duplicadas (Tamanho × Tipo × Qtde mín.) — "
        "não dá pra salvar até resolver:\n\n- " + "\n- ".join(duplicate_warnings)
    )

if b2c_b2b_warnings:
    # Soft warning — we still let the user save; sometimes the B2B price is
    # higher on purpose (e.g. small qtde with delivery embedded).
    st.warning(
        "⚠️ Atenção: faixa B2B mais cara que B2C pro mesmo tamanho/qtde "
        "— costuma ser erro de digitação. Confirma antes de salvar:\n\n- "
        + "\n- ".join(b2c_b2b_warnings)
    )

if st.button("💾 Salvar", type="primary", disabled=not has or bool(duplicate_warnings)):
    try:
        service = data.get_service()
        ssid = data._spreadsheet_id()

        not_found: list[str] = []

        for c in changes:
            r = _find_preco_sheet_row(
                service, ssid, c["tamanho_id"], c["tipo_cliente"], c["qtde_min_original"]
            )
            if r is None:
                not_found.append(
                    f"{c['tamanho_id']} {c['tipo_cliente']} qtde≥{c['qtde_min_original']}"
                )
                continue
            service.spreadsheets().values().update(
                spreadsheetId=ssid, range=f"Precos!C{r}:E{r}",
                valueInputOption="USER_ENTERED",
                body={"values": [[c["qtde_min"], c["preco"], c["notas"]]]},
            ).execute()

        # Deletions: resolve each sheet row at write time and delete in
        # descending order so earlier indices stay stable.
        resolved_deletions = []
        for d in deletions:
            r = _find_preco_sheet_row(
                service, ssid, d["tamanho_id"], d["tipo_cliente"], d["qtde_min_original"]
            )
            if r is None:
                not_found.append(d["label"])
            else:
                resolved_deletions.append(r)
        for sheet_row in sorted(resolved_deletions, reverse=True):
            data.delete_row("Precos", sheet_row)

        data.invalidate_cache()
        st.session_state[prc_edit_key] = False
        if not_found:
            st.warning(
                "Algumas linhas não foram encontradas e ficaram pra trás "
                "(podem ter sido removidas em outra aba): "
                + "; ".join(not_found)
            )
        st.success(f"✅ Salvo: {len(changes)} edição(ões), {len(resolved_deletions)} exclusão(ões).")
        st.rerun()
    except Exception as e:
        st.error(f"Erro: {e}")
