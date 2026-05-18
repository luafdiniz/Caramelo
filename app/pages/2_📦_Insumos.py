"""Insumos page: list, filter, drill into price history, edit/delete, create new.

In the spreadsheet this tab is called 'Produtos' (legacy), but the UI says
'Insumos' to match the business vocabulary — these are raw materials, not the
final sold products (which are Tamanhos).
"""

import os
import sys
import streamlit as st
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.auth import require_auth
from lib import data
from lib.ui import setup_page, brl, brl_md, compact_kpi, card_title


setup_page("Insumos", icon="📦")
require_auth()

st.title("📦 Insumos")
st.caption("Catálogo de matérias-primas, preço atual e histórico por fornecedor.")


CAT_EMOJI = {"ALI": "🍯", "FOR": "🥣", "EMB": "📦", "EQP": "🔧", "OPR": "🧻"}
CAT_LABEL = {
    "ALI": "Alimentos (ingredientes da receita)",
    "FOR": "Formas",
    "EMB": "Embalagens",
    "EQP": "Equipamentos duráveis",
    "OPR": "Operacionais (consumíveis)",
}


tab_list, tab_new = st.tabs(["📋 Insumos cadastrados", "➕ Novo insumo"])


# ============================================================================
# Lista de insumos
# ============================================================================
with tab_list:
    produtos = data.get_produtos()
    compras = data.get_compras()
    fornecedores = data.get_fornecedores()

    if produtos.empty:
        st.info("Nenhum insumo cadastrado.")
        st.stop()

    # Compute stats per produto
    def stats_for(produto_id: str) -> dict:
        sub = compras[compras["produto_id"] == produto_id].dropna(subset=["data"])
        if sub.empty:
            return {
                "preco_atual": None, "menor": None, "maior": None,
                "media": None, "n_compras": 0, "ultima_data": None,
                "fornecedor_atual": None,
            }
        latest = sub.sort_values("data", ascending=False).iloc[0]
        return {
            "preco_atual": float(latest["preco_unitario"] or 0),
            "menor": float(sub["preco_unitario"].min()),
            "maior": float(sub["preco_unitario"].max()),
            "media": float(sub["preco_unitario"].mean()),
            "n_compras": len(sub),
            "ultima_data": latest["data"],
            "fornecedor_atual": latest["fornecedor_id"],
        }

    prods_enriched = produtos.copy()
    stats_records = [stats_for(p) for p in prods_enriched["id"]]
    for k in ["preco_atual", "menor", "maior", "media", "n_compras", "ultima_data", "fornecedor_atual"]:
        prods_enriched[k] = [s[k] for s in stats_records]

    # Filters
    col_search, col_cat = st.columns([3, 2])
    with col_search:
        search = st.text_input("Buscar", placeholder="Nome ou ID")
    with col_cat:
        categorias_disponiveis = sorted(prods_enriched["categoria"].unique())
        cat_filter = st.multiselect(
            "Categoria",
            categorias_disponiveis,
            default=categorias_disponiveis,
        )

    # Sort controls
    sort_col, dir_col = st.columns([3, 1])
    with sort_col:
        sort_by = st.selectbox(
            "Ordenar por",
            ["Nome (A-Z)", "ID", "Categoria", "Preço atual", "Menor preço", "Maior preço", "Nº compras", "Última compra"],
            index=0,
        )
    with dir_col:
        asc = st.selectbox("Direção", ["Crescente ↑", "Decrescente ↓"], index=0, key="ins_dir") == "Crescente ↑"

    sort_map = {
        "Nome (A-Z)": "nome",
        "ID": "id",
        "Categoria": "categoria",
        "Preço atual": "preco_atual",
        "Menor preço": "menor",
        "Maior preço": "maior",
        "Nº compras": "n_compras",
        "Última compra": "ultima_data",
    }

    filtered = prods_enriched[prods_enriched["categoria"].isin(cat_filter)]
    if search:
        s = search.lower()
        filtered = filtered[
            filtered["id"].str.lower().str.contains(s)
            | filtered["nome"].str.lower().str.contains(s)
        ]
    filtered = filtered.sort_values(sort_map[sort_by], ascending=asc, na_position="last")

    st.caption(f"{len(filtered)} de {len(prods_enriched)} insumos")

    for _, p in filtered.iterrows():
        emoji = CAT_EMOJI.get(p["categoria"], "•")
        with st.container(border=True):
            head_col1, head_col2, head_col3 = st.columns([4, 2, 2])
            with head_col1:
                # Pull "Cadastrado via bot ..." out of free-text notes and render
                # it as a 🤖 hover icon instead — it's metadata, not a note.
                import html as _html
                notas_raw = (p.get("notas") or "").strip()
                is_bot_created = notas_raw.lower().startswith("cadastrado via bot")
                notas_user = "" if is_bot_created else notas_raw

                meta_parts = [_html.escape(p["categoria"]), _html.escape(p["unidade"])]
                if notas_user:
                    meta_parts.append(f"📝 {_html.escape(notas_user)}")
                if is_bot_created:
                    meta_parts.append(
                        '<span title="Cadastrado via bot" style="cursor: help;">🤖</span>'
                    )
                meta = " · ".join(meta_parts)
                card_title(
                    f"{emoji} {p['nome']}",
                    badge=p["id"],
                    meta=meta,
                    meta_is_html=True,
                    meta_below=True,
                )
            with head_col2:
                ultima = p.get("ultima_data")
                ultima_str = (
                    ultima.strftime('%d/%m/%Y')
                    if ultima is not None and pd.notna(ultima) else "—"
                )
                compact_kpi(
                    "Preço atual",
                    brl(p["preco_atual"]),
                    help=f"Última compra: {ultima_str}",
                )
            with head_col3:
                compact_kpi("Compras", str(int(p["n_compras"])))

            # Detail expander: history + edit + delete
            with st.expander("📊 Histórico, edição e gestão"):
                # --- History/analysis section ---
                if int(p["n_compras"]) > 0:
                    sub = compras[compras["produto_id"] == p["id"]].dropna(subset=["data"]).copy()
                    sub = sub.sort_values("data")

                    k1, k2, k3 = st.columns(3)
                    with k1:
                        compact_kpi("Menor preço", brl(p["menor"]))
                    with k2:
                        compact_kpi("Preço médio", brl(p["media"]))
                    with k3:
                        compact_kpi("Maior preço", brl(p["maior"]))

                    if len(sub) > 1:
                        st.markdown("**Evolução do preço unitário**")
                        chart_df = sub[["data", "preco_unitario"]].copy()
                        st.line_chart(chart_df.set_index("data"), height=240)

                    st.markdown("**Por fornecedor**")
                    by_supplier = sub.groupby("fornecedor_id").agg(
                        n_compras=("id", "count"),
                        preco_medio=("preco_unitario", "mean"),
                        preco_min=("preco_unitario", "min"),
                        preco_max=("preco_unitario", "max"),
                        ultima_data=("data", "max"),
                    ).reset_index()
                    by_supplier = by_supplier.merge(
                        fornecedores[["id", "nome"]].rename(columns={"id": "fornecedor_id", "nome": "fornecedor_nome"}),
                        on="fornecedor_id", how="left",
                    )
                    reliable = by_supplier[by_supplier["n_compras"] >= 2]
                    cheapest_id = None
                    if not reliable.empty:
                        cheapest_id = reliable.loc[reliable["preco_medio"].idxmin(), "fornecedor_id"]

                    disp = by_supplier.copy()
                    disp["fornecedor"] = disp.apply(
                        lambda r: f"{'⭐ ' if r['fornecedor_id'] == cheapest_id else ''}{r['fornecedor_nome'] or r['fornecedor_id']}",
                        axis=1,
                    )
                    disp["ultima_data"] = disp["ultima_data"].dt.strftime("%d/%m/%Y")
                    disp["preco_medio"] = disp["preco_medio"].apply(brl)
                    disp["preco_min"] = disp["preco_min"].apply(brl)
                    disp["preco_max"] = disp["preco_max"].apply(brl)
                    disp = disp[["fornecedor", "n_compras", "preco_medio", "preco_min", "preco_max", "ultima_data"]]
                    disp.columns = ["Fornecedor", "Nº compras", "Preço médio", "Menor", "Maior", "Última compra"]
                    st.table(disp.set_index("Fornecedor"))

                    median_price = sub["preco_unitario"].median()
                    outliers = sub[sub["preco_unitario"] > median_price * 1.5]
                    if not outliers.empty and median_price > 0:
                        st.warning(
                            f"⚠️ {len(outliers)} compra(s) ficaram >50% acima da mediana ({brl_md(median_price)}). "
                            "Pode ser emergência ou erro — confere se faz sentido."
                        )

                # --- Edit section ---
                st.divider()
                st.markdown("**✏️ Editar este insumo**")
                with st.form(f"edit_prod_{p['id']}"):
                    new_nome = st.text_input("Nome", value=p["nome"])
                    ec1, ec2 = st.columns(2)
                    with ec1:
                        new_unidade = st.text_input("Unidade", value=p["unidade"] or "UN")
                    with ec2:
                        new_marca = st.text_input(
                            "Marca padrão",
                            value=p.get("marca_padrao") or "",
                            help="Usada como fallback quando o bot não extrai a marca da nota",
                        )
                    new_notas = st.text_input("Notas", value=p.get("notas") or "")
                    if st.form_submit_button("💾 Salvar alterações", use_container_width=True, type="primary"):
                        try:
                            row_num = data.find_row_by_id("Produtos", p["id"])
                            service = data.get_service()
                            # Update columns B (Nome), C (Unidade), D (Notas) and F (Marca_padrao).
                            # Column E (Relacionados) is left as-is.
                            service.spreadsheets().values().update(
                                spreadsheetId=data._spreadsheet_id(),
                                range=f"Produtos!B{row_num}:D{row_num}",
                                valueInputOption="USER_ENTERED",
                                body={"values": [[new_nome, new_unidade, new_notas]]},
                            ).execute()
                            service.spreadsheets().values().update(
                                spreadsheetId=data._spreadsheet_id(),
                                range=f"Produtos!F{row_num}",
                                valueInputOption="USER_ENTERED",
                                body={"values": [[new_marca]]},
                            ).execute()
                            data.invalidate_cache()
                            st.success(f"✅ {p['id']} atualizado!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Erro: {e}")

                # --- Delete section ---
                st.divider()
                st.markdown("**🗑️ Deletar este insumo**")
                n_compras = int(p["n_compras"])
                if n_compras > 0:
                    st.warning(
                        f"⚠️ Este insumo tem **{n_compras} compra(s)** registradas. "
                        "Se você deletar, essas compras vão ficar órfãs (apontando pra um ID que não existe). "
                        "Considere apenas se tem certeza."
                    )

                confirm_key = f"confirm_del_{p['id']}"
                if st.session_state.get(confirm_key):
                    st.error(f"Confirma deletar {p['id']} — {p['nome']}? Esta ação é irreversível.")
                    cdc1, cdc2 = st.columns(2)
                    with cdc1:
                        if st.button("✅ Sim, deletar", key=f"do_del_{p['id']}", type="primary"):
                            try:
                                row_num = data.find_row_by_id("Produtos", p["id"])
                                data.delete_row("Produtos", row_num)
                                data.invalidate_cache()
                                del st.session_state[confirm_key]
                                st.success(f"✅ {p['id']} deletado.")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Erro: {e}")
                    with cdc2:
                        if st.button("❌ Cancelar", key=f"cancel_del_{p['id']}"):
                            del st.session_state[confirm_key]
                            st.rerun()
                else:
                    if st.button("🗑️ Deletar insumo", key=f"req_del_{p['id']}"):
                        st.session_state[confirm_key] = True
                        st.rerun()


# ============================================================================
# Criar novo insumo
# ============================================================================
with tab_new:
    st.markdown("### Cadastrar um novo insumo")
    st.caption("Útil quando você precisa adicionar um insumo sem ter ainda comprado (vai aparecer no catálogo).")

    with st.form("new_produto", clear_on_submit=True):
        cat_options = list(CAT_LABEL.keys())
        new_cat = st.radio(
            "Categoria",
            cat_options,
            format_func=lambda c: f"{CAT_EMOJI[c]} {c} — {CAT_LABEL[c]}",
            horizontal=False,
        )

        c1, c2 = st.columns([2, 1])
        with c1:
            new_nome = st.text_input("Nome do insumo", placeholder="ex: AÇÚCAR REFINADO 1KG")
        with c2:
            new_unidade = st.selectbox(
                "Unidade",
                ["UN", "KG", "L", "M", "FOLHA", "Pente", "Dz"],
                index=0,
            )
        new_notas = st.text_input("Notas (opcional)", placeholder="ex: comprado em pente de 30")

        if st.form_submit_button("➕ Criar insumo", use_container_width=True, type="primary"):
            if not new_nome.strip():
                st.error("Dá um nome pro insumo.")
            else:
                try:
                    new_id = data._sheets.create_produto(
                        data._spreadsheet_id(),
                        new_nome.strip(),
                        new_cat,
                        unidade=new_unidade,
                        notas=new_notas.strip() or "Criado pelo app",
                        service=data.get_service(),
                    )
                    data.invalidate_cache()
                    st.success(f"✅ Insumo criado: **{new_id} — {new_nome}**")
                    st.balloons()
                except Exception as e:
                    st.error(f"Erro criando: {e}")
                    import traceback
                    st.code(traceback.format_exc())
