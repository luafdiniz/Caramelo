"""Tabela de preços B2C/B2B com faixas por volume."""

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
disp = disp.sort_values(["tamanho_id", "tipo_cliente", "qtde_min"])

# Render as data_editor (limited — qtde_min and preco are editable; tamanho/tipo not)
view = pd.DataFrame({
    "Tamanho": disp["Tamanho"].values,
    "Tipo": disp["tipo_cliente"].values,
    "Qtde mín.": disp["qtde_min"].values.astype(int),
    "Preço unit.": disp["preco_unit"].values,
    "Notas": disp["notas"].values,
    "Excluir": [False] * len(disp),
})

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

# Diff against original
changes = []
deletions = []
for i, row in edited.iterrows():
    orig = view.iloc[i]
    orig_row = disp.iloc[i]  # original (untransformed) row to find sheet position
    sheet_row = (orig_row.name + 2)  # +1 header, +1 1-indexed
    if bool(row["Excluir"]):
        deletions.append({"sheet_row": sheet_row, "label": f"{orig['Tamanho']} {orig['Tipo']} qtde≥{orig['Qtde mín.']}"})
        continue
    if (int(row["Qtde mín."]) != int(orig["Qtde mín."])
        or abs(float(row["Preço unit."]) - float(orig["Preço unit."])) > 0.005
        or str(row["Notas"] or "").strip() != str(orig["Notas"] or "").strip()):
        changes.append({
            "sheet_row": sheet_row,
            "qtde_min": int(row["Qtde mín."]),
            "preco": float(row["Preço unit."]),
            "notas": str(row["Notas"] or "").strip(),
        })

has = bool(changes or deletions)
if has:
    bullets = []
    if changes:
        bullets.append(f"✏️ {len(changes)} edição(ões)")
    if deletions:
        bullets.append(f"🗑️ {len(deletions)} exclusão(ões)")
    st.caption("Alterações pendentes: " + " · ".join(bullets))

if st.button("💾 Salvar", type="primary", disabled=not has):
    try:
        service = data.get_service()
        ssid = data._spreadsheet_id()

        for c in changes:
            r = c["sheet_row"]
            service.spreadsheets().values().update(
                spreadsheetId=ssid, range=f"Precos!C{r}:E{r}",
                valueInputOption="USER_ENTERED",
                body={"values": [[c["qtde_min"], c["preco"], c["notas"]]]},
            ).execute()

        # Deletions: do them in reverse row order so earlier indices stay stable.
        for d in sorted(deletions, key=lambda x: -x["sheet_row"]):
            data.delete_row("Precos", d["sheet_row"])

        data.invalidate_cache()
        st.success(f"✅ Salvo: {len(changes)} edição(ões), {len(deletions)} exclusão(ões).")
        st.rerun()
    except Exception as e:
        st.error(f"Erro: {e}")
