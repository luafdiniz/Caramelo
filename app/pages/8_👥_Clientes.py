"""Clientes page: cadastro de B2C e B2B + edição inline."""

import os
import sys
from datetime import date
import streamlit as st
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.auth import require_auth
from lib import data
from lib.ui import setup_page


setup_page("Clientes", icon="👥")
require_auth()

st.title("👥 Clientes")
st.caption("Cadastro de quem compra. B2B para atacado, B2C pro varejo.")


def _next_cli_id(existing_ids: list[str]) -> str:
    """Find the next CLI-NNN — uniqueness across Clientes."""
    max_n = 0
    for cid in existing_ids:
        if cid.startswith("CLI-"):
            try:
                n = int(cid.split("-")[1])
                max_n = max(max_n, n)
            except (ValueError, IndexError):
                continue
    return f"CLI-{max_n + 1:03d}"


clientes = data.get_clientes()

if clientes.empty and not data._has_sheet("Clientes"):
    st.warning(
        "A aba **Clientes** ainda não existe na planilha. "
        "Rode `python scripts/migrate_clientes_vendas.py --apply`."
    )
    st.stop()


# --- New cliente form ---
with st.expander("➕ Novo cliente", expanded=False):
    with st.form("new_cliente", clear_on_submit=True):
        c1, c2 = st.columns([2, 1])
        with c1:
            new_nome = st.text_input("Nome", placeholder="Padaria da Esquina")
        with c2:
            new_tipo = st.selectbox("Tipo", ["B2C", "B2B"], index=0)
        c3, c4 = st.columns(2)
        with c3:
            new_contato = st.text_input("Contato (WhatsApp/telefone)")
        with c4:
            new_periodicidade = st.text_input("Periodicidade", placeholder="Semanal, esporádico, …")
        new_endereco = st.text_input("Endereço")
        new_dia = st.text_input("Dia de entrega preferido", placeholder="Quinta, fim de semana, …")
        new_obs = st.text_input("Observações")

        if st.form_submit_button("➕ Cadastrar cliente", type="primary"):
            if not new_nome.strip():
                st.error("Nome é obrigatório.")
            else:
                try:
                    existing_ids = clientes["id"].astype(str).tolist() if not clientes.empty else []
                    new_id = _next_cli_id(existing_ids)
                    row = [
                        new_id, new_nome.strip(), new_tipo,
                        new_contato.strip(), new_endereco.strip(),
                        new_dia.strip(), new_periodicidade.strip(),
                        new_obs.strip(), date.today().isoformat(), True,
                    ]
                    data.get_service().spreadsheets().values().append(
                        spreadsheetId=data._spreadsheet_id(),
                        range="Clientes!A1",
                        valueInputOption="USER_ENTERED",
                        body={"values": [row]},
                    ).execute()
                    data.invalidate_cache()
                    st.success(f"✅ Cliente cadastrado: **{new_id} — {new_nome}**")
                    st.rerun()
                except Exception as e:
                    st.error(f"Erro ao cadastrar: {e}")


if clientes.empty:
    st.info("Nenhum cliente cadastrado ainda.")
    st.stop()


# --- Search + edit table ---
search = st.text_input("Buscar", placeholder="Nome ou ID")
show_inactive = st.checkbox("Mostrar inativos", value=False)

view = clientes.copy()
if not show_inactive:
    view = view[view["ativo"] == True]  # noqa: E712
if search:
    s = search.lower()
    view = view[
        view["id"].str.lower().str.contains(s)
        | view["nome"].str.lower().str.contains(s)
    ]

if view.empty:
    st.info("Nenhum cliente bate com os filtros.")
    st.stop()

st.caption(f"{len(view)} cliente(s)")

editor_df = pd.DataFrame({
    "ID": view["id"].values,
    "Nome": view["nome"].values,
    "Tipo": view["tipo"].values,
    "Contato": view["contato"].values,
    "Endereço": view["endereco"].values,
    "Dia entrega": view["dia_entrega_preferido"].values,
    "Periodicidade": view["periodicidade"].values,
    "Obs.": view["observacoes"].values,
    "Ativo": view["ativo"].astype(bool).values,
    "Excluir": [False] * len(view),
})

edited = st.data_editor(
    editor_df,
    hide_index=True,
    use_container_width=True,
    num_rows="fixed",
    key="clientes_editor",
    column_config={
        "ID": st.column_config.TextColumn("ID", disabled=True, width="small"),
        "Tipo": st.column_config.SelectboxColumn("Tipo", options=["B2C", "B2B"], required=True),
        "Ativo": st.column_config.CheckboxColumn("Ativo", help="Desmarque pra ocultar dos selectboxes (soft-delete)."),
        "Excluir": st.column_config.CheckboxColumn("Excluir", help="Marca pra deletar a linha ao salvar."),
    },
)

# Diff and save
changes: list[dict] = []
deletions: list[dict] = []
for i, row in edited.iterrows():
    orig = editor_df.iloc[i]
    cid = row["ID"]
    if bool(row["Excluir"]):
        deletions.append({"id": cid, "nome": row["Nome"]})
        continue
    changed = any(
        str(row[col] or "").strip() != str(orig[col] or "").strip()
        for col in ("Nome", "Tipo", "Contato", "Endereço", "Dia entrega",
                    "Periodicidade", "Obs.")
    ) or bool(row["Ativo"]) != bool(orig["Ativo"])
    if changed:
        changes.append({
            "id": cid,
            "nome": str(row["Nome"] or "").strip(),
            "tipo": str(row["Tipo"] or "B2C").strip(),
            "contato": str(row["Contato"] or "").strip(),
            "endereco": str(row["Endereço"] or "").strip(),
            "dia": str(row["Dia entrega"] or "").strip(),
            "periodicidade": str(row["Periodicidade"] or "").strip(),
            "obs": str(row["Obs."] or "").strip(),
            "ativo": bool(row["Ativo"]),
        })

has_changes = bool(changes or deletions)
if has_changes:
    bullets = []
    if changes:
        bullets.append(f"✏️ {len(changes)} edição(ões)")
    if deletions:
        bullets.append(f"🗑️ {len(deletions)} exclusão(ões)")
    st.caption("Alterações pendentes: " + " · ".join(bullets))

if st.button("💾 Salvar alterações", type="primary", disabled=not has_changes):
    try:
        service = data.get_service()
        ssid = data._spreadsheet_id()

        for c in changes:
            row_num = data.find_row_by_id("Clientes", c["id"])
            # B:H — campos editáveis. I (data_cadastro) fica intacta.
            service.spreadsheets().values().update(
                spreadsheetId=ssid,
                range=f"Clientes!B{row_num}:H{row_num}",
                valueInputOption="USER_ENTERED",
                body={"values": [[
                    c["nome"], c["tipo"], c["contato"], c["endereco"],
                    c["dia"], c["periodicidade"], c["obs"],
                ]]},
            ).execute()
            service.spreadsheets().values().update(
                spreadsheetId=ssid,
                range=f"Clientes!J{row_num}",
                valueInputOption="USER_ENTERED",
                body={"values": [[c["ativo"]]]},
            ).execute()

        for d in deletions:
            row_num = data.find_row_by_id("Clientes", d["id"])
            data.delete_row("Clientes", row_num)

        data.invalidate_cache()
        st.success(f"✅ Salvo: {len(changes)} edição(ões), {len(deletions)} exclusão(ões).")
        st.rerun()
    except Exception as e:
        st.error(f"Erro ao salvar: {e}")
