"""Fornecedores page: list, edit, delete, create.

Mirrors the Insumos page structure: per-row card with metrics + expander
for edit/delete; separate tab for creating a new fornecedor.
"""

import os
import sys
import streamlit as st
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.auth import require_auth
from lib import data
from lib.ui import setup_page, brl, compact_kpi, card_title


setup_page("Fornecedores", icon="🏪")
require_auth()

st.title("🏪 Fornecedores")
st.caption("Quem fornece o quê — lista, contato, e quanto você já gastou em cada um.")


TIPO_OPTIONS = ["Supermercado", "Loja", "Online", "Feira", "Gráfica", "Atacado", "Outro"]


tab_list, tab_new = st.tabs(["📋 Fornecedores cadastrados", "➕ Novo fornecedor"])


# ============================================================================
# Lista
# ============================================================================
with tab_list:
    forns = data.get_fornecedores()
    compras = data.get_compras()

    if forns.empty:
        st.info("Nenhum fornecedor cadastrado.")
        st.stop()

    # Enrich with metrics: n_compras, total_gasto, ultima_compra
    def stats_for(forn_id: str) -> dict:
        sub = compras[compras["fornecedor_id"] == forn_id].dropna(subset=["data"])
        if sub.empty:
            return {"n_compras": 0, "total_gasto": 0.0, "ultima_compra": None}
        return {
            "n_compras": int(len(sub)),
            "total_gasto": float(sub["preco_total"].sum()),
            "ultima_compra": sub["data"].max(),
        }

    forns_enriched = forns.copy()
    stats_records = [stats_for(f) for f in forns_enriched["id"]]
    for k in ["n_compras", "total_gasto", "ultima_compra"]:
        forns_enriched[k] = [s[k] for s in stats_records]

    # Filters
    col_search, col_tipo = st.columns([3, 2])
    with col_search:
        search = st.text_input("Buscar", placeholder="Nome ou ID")
    with col_tipo:
        tipos_disponiveis = sorted([t for t in forns_enriched["tipo"].unique() if t])
        tipo_filter = st.multiselect("Tipo", tipos_disponiveis, default=tipos_disponiveis)

    # Sort
    sort_col, dir_col = st.columns([3, 1])
    with sort_col:
        sort_by = st.selectbox(
            "Ordenar por",
            ["Nome (A-Z)", "ID", "Nº compras", "Total gasto", "Última compra"],
            index=0,
        )
    with dir_col:
        asc = st.selectbox("Direção", ["Crescente ↑", "Decrescente ↓"], index=0, key="forn_dir") == "Crescente ↑"

    sort_map = {
        "Nome (A-Z)": "nome",
        "ID": "id",
        "Nº compras": "n_compras",
        "Total gasto": "total_gasto",
        "Última compra": "ultima_compra",
    }

    filtered = forns_enriched.copy()
    if tipo_filter:
        filtered = filtered[filtered["tipo"].isin(tipo_filter) | filtered["tipo"].isna() | (filtered["tipo"] == "")]
    if search:
        s = search.lower()
        filtered = filtered[
            filtered["id"].str.lower().str.contains(s)
            | filtered["nome"].str.lower().str.contains(s)
        ]
    filtered = filtered.sort_values(sort_map[sort_by], ascending=asc, na_position="last")

    st.caption(f"{len(filtered)} de {len(forns_enriched)} fornecedores")

    for _, f in filtered.iterrows():
        with st.container(border=True):
            head_col1, head_col2, head_col3 = st.columns([4, 2, 2])
            with head_col1:
                meta_parts = [f["tipo"] or "—"]
                if f.get("localizacao"):
                    meta_parts.append(f["localizacao"])
                if f.get("notas"):
                    meta_parts.append(f"📝 {f['notas']}")
                card_title(f["nome"] or "(sem nome)", badge=f["id"], meta=" · ".join(meta_parts))
            with head_col2:
                ultima = f.get("ultima_compra")
                ultima_str = (
                    ultima.strftime("%d/%m/%Y")
                    if ultima is not None and pd.notna(ultima) else "—"
                )
                compact_kpi("Total gasto", brl(f["total_gasto"]), help=f"Última compra: {ultima_str}")
            with head_col3:
                compact_kpi("Compras", str(int(f["n_compras"])))

            with st.expander("✏️ Editar / 🗑️ Deletar"):
                # --- Edit ---
                with st.form(f"edit_forn_{f['id']}"):
                    new_nome = st.text_input("Nome", value=f["nome"] or "")
                    c1, c2 = st.columns(2)
                    with c1:
                        current_tipo = f.get("tipo") or "Loja"
                        tipo_options = TIPO_OPTIONS + ([current_tipo] if current_tipo and current_tipo not in TIPO_OPTIONS else [])
                        new_tipo = st.selectbox(
                            "Tipo",
                            tipo_options,
                            index=tipo_options.index(current_tipo) if current_tipo in tipo_options else 0,
                        )
                    with c2:
                        new_localizacao = st.text_input("Localização", value=f.get("localizacao") or "")
                    new_notas = st.text_input("Notas", value=f.get("notas") or "")

                    if st.form_submit_button("💾 Salvar alterações", use_container_width=True, type="primary"):
                        try:
                            row_num = data.find_row_by_id("Fornecedores", f["id"])
                            service = data.get_service()
                            service.spreadsheets().values().update(
                                spreadsheetId=data._spreadsheet_id(),
                                range=f"Fornecedores!B{row_num}:E{row_num}",
                                valueInputOption="USER_ENTERED",
                                body={"values": [[new_nome, new_tipo, new_localizacao, new_notas]]},
                            ).execute()
                            data.invalidate_cache()
                            st.success(f"✅ {f['id']} atualizado!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Erro: {e}")

                # --- Delete ---
                st.divider()
                st.markdown("**🗑️ Deletar este fornecedor**")
                n_compras = int(f["n_compras"])
                if n_compras > 0:
                    st.warning(
                        f"⚠️ Este fornecedor tem **{n_compras} compra(s)** registradas. "
                        "Se deletar, essas compras vão ficar órfãs (apontando pra um ID que não existe). "
                        f"Considere editar pra corrigir o nome em vez de deletar."
                    )

                confirm_key = f"confirm_del_forn_{f['id']}"
                if st.session_state.get(confirm_key):
                    st.error(f"Confirma deletar {f['id']} — {f['nome'] or '(sem nome)'}? Esta ação é irreversível.")
                    cdc1, cdc2 = st.columns(2)
                    with cdc1:
                        if st.button("✅ Sim, deletar", key=f"do_del_forn_{f['id']}", type="primary"):
                            try:
                                row_num = data.find_row_by_id("Fornecedores", f["id"])
                                data.delete_row("Fornecedores", row_num)
                                data.invalidate_cache()
                                del st.session_state[confirm_key]
                                st.success(f"✅ {f['id']} deletado.")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Erro: {e}")
                    with cdc2:
                        if st.button("❌ Cancelar", key=f"cancel_del_forn_{f['id']}"):
                            del st.session_state[confirm_key]
                            st.rerun()
                else:
                    if st.button("🗑️ Deletar fornecedor", key=f"req_del_forn_{f['id']}"):
                        st.session_state[confirm_key] = True
                        st.rerun()


# ============================================================================
# Novo fornecedor
# ============================================================================
with tab_new:
    st.markdown("### Cadastrar um novo fornecedor")
    st.caption("Pra ter na lista de quem você compra (mesmo antes de ter alguma compra cadastrada).")

    with st.form("new_forn", clear_on_submit=True):
        new_nome = st.text_input("Nome", placeholder="ex: Mercado Central")
        c1, c2 = st.columns(2)
        with c1:
            new_tipo = st.selectbox("Tipo", TIPO_OPTIONS, index=1)
        with c2:
            new_localizacao = st.text_input("Localização (opcional)", placeholder="ex: BH centro")
        new_notas = st.text_input("Notas (opcional)", placeholder="ex: melhor preço de leite condensado")

        if st.form_submit_button("➕ Cadastrar fornecedor", use_container_width=True, type="primary"):
            if not new_nome.strip():
                st.error("Dá um nome pro fornecedor.")
            else:
                try:
                    new_id = data._sheets.create_fornecedor(
                        data._spreadsheet_id(),
                        new_nome.strip(),
                        tipo=new_tipo,
                        localizacao=new_localizacao.strip(),
                        notas=new_notas.strip() or "Cadastrado pelo app",
                        service=data.get_service(),
                    )
                    data.invalidate_cache()
                    st.success(f"✅ Fornecedor criado: **{new_id} — {new_nome}**")
                    st.balloons()
                except Exception as e:
                    st.error(f"Erro criando: {e}")
                    import traceback
                    st.code(traceback.format_exc())
