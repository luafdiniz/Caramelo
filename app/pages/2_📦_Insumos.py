"""Insumos page: list, filter, drill into price history, edit/delete, create new.

In the spreadsheet this tab is called 'Produtos' (legacy), but the UI says
'Insumos' to match the business vocabulary — these are raw materials, not the
final sold products (which are Tamanhos).

The list view is a compact table-like layout (one row per produto) with an
inline "✏️ Atualizar preço" popover that writes a new Compra tagged as a
manual adjustment, so the price flows through the existing latest_unit_price
pipeline. Full edit / history / delete lives in the "✏️ Editar" expander.
"""

import os
import sys
from datetime import date
import streamlit as st
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.auth import require_auth
from lib import data
from lib.ui import (
    setup_page,
    brl,
    brl_md,
    compact_kpi,
    PURPLE_DARK,
    CARAMEL,
    CARAMEL_LIGHT,
    DARK_BROWN,
)


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


# Lightweight styling for the table-like list — header strip, row labels,
# slim cell text, thin separator between rows. Scoped via class names so it
# doesn't leak into other pages.
_LIST_CSS = f"""
<style>
.insumos-header {{
    border-bottom: 2px solid {CARAMEL_LIGHT};
    margin: 0.25rem 0 0.5rem 0;
    padding-bottom: 0.4rem;
}}
.insumos-header-label {{
    color: {CARAMEL} !important;
    font-size: 0.72rem !important;
    font-weight: 700 !important;
    letter-spacing: 0.05em;
    text-transform: uppercase;
    line-height: 1.2 !important;
    margin: 0 !important;
}}
.insumos-row-name {{
    font-family: 'Fraunces', serif !important;
    color: {PURPLE_DARK} !important;
    font-size: 1.0rem !important;
    font-weight: 700 !important;
    line-height: 1.2 !important;
    margin: 0 !important;
}}
.insumos-row-meta {{
    color: {CARAMEL} !important;
    font-size: 0.75rem !important;
    font-weight: 500 !important;
    margin: 2px 0 0 0 !important;
    line-height: 1.3 !important;
}}
.insumos-row-meta strong {{ color: {PURPLE_DARK} !important; }}
.insumos-cell {{
    color: {DARK_BROWN} !important;
    font-size: 0.92rem !important;
    margin: 0 !important;
    padding-top: 0.15rem;
}}
.insumos-cell-price {{
    font-family: 'Fraunces', serif !important;
    color: {PURPLE_DARK} !important;
    font-weight: 700 !important;
    font-size: 1.05rem !important;
}}
.insumos-cell-muted {{
    color: {CARAMEL} !important;
    font-size: 0.85rem !important;
}}
hr.insumos-sep {{
    border: none;
    border-top: 1px solid rgba(176, 120, 66, 0.18);
    margin: 0.4rem 0;
}}
</style>
"""
st.markdown(_LIST_CSS, unsafe_allow_html=True)


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
            ["Nome (A-Z)", "ID", "Categoria", "Marca", "Preço atual", "Menor preço", "Maior preço", "Nº compras", "Última compra"],
            index=0,
        )
    with dir_col:
        asc = st.selectbox("Direção", ["Crescente ↑", "Decrescente ↓"], index=0, key="ins_dir") == "Crescente ↑"

    sort_map = {
        "Nome (A-Z)": "nome",
        "ID": "id",
        "Categoria": "categoria",
        "Marca": "marca_padrao",
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

    # Lookup helper: fornecedor id -> nome (for the price-update popover)
    forn_id_to_nome = (
        dict(zip(fornecedores["id"], fornecedores["nome"]))
        if not fornecedores.empty else {}
    )

    # ---- Header strip (table column labels) ----
    # Columns: Insumo (4) | Marca (2) | Preço atual + popover (3) | Compras (1) | Última (2) | Editar (1)
    COL_WIDTHS = [4, 2, 3, 1, 2, 1]
    h1, h2, h3, h4, h5, h6 = st.columns(COL_WIDTHS)
    with h1:
        st.markdown('<div class="insumos-header"><p class="insumos-header-label">Insumo</p></div>', unsafe_allow_html=True)
    with h2:
        st.markdown('<div class="insumos-header"><p class="insumos-header-label">Marca</p></div>', unsafe_allow_html=True)
    with h3:
        st.markdown('<div class="insumos-header"><p class="insumos-header-label">Preço atual</p></div>', unsafe_allow_html=True)
    with h4:
        st.markdown('<div class="insumos-header"><p class="insumos-header-label">Compras</p></div>', unsafe_allow_html=True)
    with h5:
        st.markdown('<div class="insumos-header"><p class="insumos-header-label">Última</p></div>', unsafe_allow_html=True)
    with h6:
        st.markdown('<div class="insumos-header"><p class="insumos-header-label">&nbsp;</p></div>', unsafe_allow_html=True)

    # ---- One row per produto ----
    import html as _html
    for _, p in filtered.iterrows():
        emoji = CAT_EMOJI.get(p["categoria"], "•")

        # Build meta string (categoria · unidade · relacionados · 🤖 bot tag)
        notas_raw = (p.get("notas") or "").strip()
        is_bot_created = notas_raw.lower().startswith("cadastrado via bot")
        notas_user = "" if is_bot_created else notas_raw

        meta_parts = [
            _html.escape(p["categoria"]),
            _html.escape(p["unidade"] or ""),
        ]
        relacionados = p.get("relacionados") or []
        if isinstance(relacionados, list) and relacionados:
            meta_parts.append(f"🔗 {_html.escape(', '.join(relacionados))}")
        if notas_user:
            meta_parts.append(f"📝 {_html.escape(notas_user)}")
        if is_bot_created:
            meta_parts.append('<span title="Cadastrado via bot" style="cursor: help;">🤖</span>')
        meta_html = " · ".join(meta_parts)

        c1, c2, c3, c4, c5, c6 = st.columns(COL_WIDTHS)

        # Col 1: emoji + nome + ID badge + meta
        with c1:
            st.markdown(
                f'<p class="insumos-row-name">{emoji} {_html.escape(p["nome"])} '
                f'<code>{_html.escape(p["id"])}</code></p>'
                f'<p class="insumos-row-meta">{meta_html}</p>',
                unsafe_allow_html=True,
            )

        # Col 2: marca padrão
        with c2:
            marca = (p.get("marca_padrao") or "").strip()
            st.markdown(
                f'<p class="insumos-cell">{_html.escape(marca) if marca else "—"}</p>',
                unsafe_allow_html=True,
            )

        # Col 3: preço atual + popover for inline update
        with c3:
            price_col, edit_col = st.columns([3, 2])
            with price_col:
                preco_str = brl(p["preco_atual"]) if p["preco_atual"] is not None else "—"
                st.markdown(
                    f'<p class="insumos-cell insumos-cell-price">{preco_str}</p>',
                    unsafe_allow_html=True,
                )
            with edit_col:
                with st.popover("✏️", help="Atualizar preço", use_container_width=False):
                    st.markdown(f"**Atualizar preço de {p['nome']}**")
                    st.caption(
                        "Vai registrar uma Compra de ajuste manual "
                        "(qtde 1, preço total = novo preço unitário)."
                    )
                    # Default fornecedor = most recent for this produto, else
                    # the first one available globally.
                    default_forn = p.get("fornecedor_atual")
                    forn_options = []
                    if not fornecedores.empty:
                        forn_options = list(fornecedores["id"])
                    if not forn_options:
                        st.warning("Cadastre um fornecedor antes de atualizar o preço.")
                    else:
                        try:
                            default_idx = (
                                forn_options.index(default_forn)
                                if default_forn in forn_options else 0
                            )
                        except ValueError:
                            default_idx = 0
                        forn_id = st.selectbox(
                            "Fornecedor",
                            forn_options,
                            index=default_idx,
                            format_func=lambda fid: f"{forn_id_to_nome.get(fid, fid)} ({fid})",
                            key=f"forn_sel_{p['id']}",
                        )
                        novo_preco = st.number_input(
                            "Novo preço (R$ por unidade)",
                            min_value=0.0,
                            value=float(p["preco_atual"] or 0.0),
                            step=0.10,
                            format="%.2f",
                            key=f"novo_preco_{p['id']}",
                        )
                        if st.button(
                            "💾 Salvar",
                            key=f"save_preco_{p['id']}",
                            type="primary",
                            use_container_width=True,
                        ):
                            if novo_preco <= 0:
                                st.error("Informe um preço maior que zero.")
                            else:
                                try:
                                    data._sheets.append_compra(
                                        data._spreadsheet_id(),
                                        data=date.today().strftime("%Y-%m-%d"),
                                        produto_id=p["id"],
                                        fornecedor_id=forn_id,
                                        marca=(p.get("marca_padrao") or "").strip(),
                                        qtde_embalagens=1,
                                        unidades_por_embalagem=1,
                                        preco_total=float(novo_preco),
                                        notas="Ajuste manual de preço (sem compra)",
                                        service=data.get_service(),
                                    )
                                    data.invalidate_cache()
                                    st.success(
                                        f"✅ Preço de {p['id']} atualizado para {brl(novo_preco)}"
                                    )
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Erro: {e}")

        # Col 4: nº compras
        with c4:
            st.markdown(
                f'<p class="insumos-cell">{int(p["n_compras"])}</p>',
                unsafe_allow_html=True,
            )

        # Col 5: última compra
        with c5:
            ultima = p.get("ultima_data")
            ultima_str = (
                ultima.strftime("%d/%m/%Y")
                if ultima is not None and pd.notna(ultima) else "—"
            )
            st.markdown(
                f'<p class="insumos-cell insumos-cell-muted">{ultima_str}</p>',
                unsafe_allow_html=True,
            )

        # Col 6: edit expander trigger — we just render an expander on its own
        # row below for simplicity; col 6 holds a small visual cue.
        with c6:
            st.markdown(
                '<p class="insumos-cell insumos-cell-muted" style="text-align:right;">›</p>',
                unsafe_allow_html=True,
            )

        # Detail expander: history + edit + delete (full management surface)
        with st.expander("✏️ Editar", expanded=False):
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

        # Thin separator between rows — keeps the table feel without per-row borders.
        st.markdown('<hr class="insumos-sep" />', unsafe_allow_html=True)


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
