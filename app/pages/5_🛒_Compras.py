"""Compras page: monthly summary + detailed history with filters."""

import os
import sys
from datetime import datetime
import streamlit as st
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.auth import require_auth
from lib import data
from lib.ui import setup_page, brl


setup_page("Compras", icon="🛒")
require_auth()

st.title("🛒 Compras")
st.caption("Histórico de compras com resumo mensal e drill-down.")


compras = data.get_compras()
produtos = data.get_produtos()
fornecedores = data.get_fornecedores()

if compras.empty:
    st.info("Nenhuma compra registrada ainda.")
    st.stop()

# Enrich with nome and categoria
compras = compras.merge(
    produtos[["id", "nome", "categoria"]].rename(columns={"id": "produto_id", "nome": "produto_nome"}),
    on="produto_id", how="left",
).merge(
    fornecedores[["id", "nome"]].rename(columns={"id": "fornecedor_id", "nome": "fornecedor_nome"}),
    on="fornecedor_id", how="left",
)


# ============================================================================
# Monthly summary
# ============================================================================
st.subheader("Resumo mensal")

compras_with_date = compras.dropna(subset=["data"]).copy()
compras_with_date["mes"] = compras_with_date["data"].dt.to_period("M")

# Pick which month to focus on
months_available = sorted(compras_with_date["mes"].unique(), reverse=True)
month_labels = [m.strftime("%B %Y").capitalize() for m in months_available]
month_idx = st.selectbox(
    "Mês",
    range(len(months_available)),
    format_func=lambda i: month_labels[i],
    index=0,
)
selected_month = months_available[month_idx]

month_data = compras_with_date[compras_with_date["mes"] == selected_month]

# KPIs
k1, k2, k3, k4 = st.columns(4)
with k1:
    st.metric("Total gasto", brl(month_data["preco_total"].sum()))
with k2:
    st.metric("Nº de compras", str(len(month_data)))
with k3:
    n_unique_prods = month_data["produto_id"].nunique()
    st.metric("Produtos diferentes", str(n_unique_prods))
with k4:
    n_unique_forn = month_data["fornecedor_id"].nunique()
    st.metric("Fornecedores", str(n_unique_forn))


# Breakdown by categoria
st.markdown("**Distribuição por categoria**")
cat_summary = month_data.groupby("categoria").agg(
    total=("preco_total", "sum"),
    n_compras=("id", "count"),
).reset_index().sort_values("total", ascending=False)

# Bar chart
chart_df = cat_summary.set_index("categoria")[["total"]]
chart_df.columns = ["Total gasto (R$)"]
st.bar_chart(chart_df, height=240)

# Table
cat_display = cat_summary.copy()
cat_display["total"] = cat_display["total"].apply(brl)
cat_display.columns = ["Categoria", "Total gasto", "Nº compras"]
st.dataframe(cat_display, hide_index=True, use_container_width=True)


# Top fornecedores do mês
st.markdown("**Top fornecedores do mês**")
forn_summary = month_data.groupby("fornecedor_nome").agg(
    total=("preco_total", "sum"),
    n_compras=("id", "count"),
).reset_index().sort_values("total", ascending=False).head(10)
forn_display = forn_summary.copy()
forn_display["total"] = forn_display["total"].apply(brl)
forn_display.columns = ["Fornecedor", "Total gasto", "Nº compras"]
st.dataframe(forn_display, hide_index=True, use_container_width=True)


st.divider()


# ============================================================================
# Detailed history
# ============================================================================
st.subheader("Compras detalhadas")

# Filters
filt1, filt2, filt3 = st.columns(3)
with filt1:
    only_month = st.checkbox(f"Apenas {month_labels[month_idx]}", value=True)
with filt2:
    categorias_disp = sorted(compras["categoria"].dropna().unique())
    cat_filter = st.multiselect("Categoria", categorias_disp, default=categorias_disp)
with filt3:
    forns_disp = sorted(compras["fornecedor_nome"].dropna().unique())
    forn_filter = st.multiselect("Fornecedor", forns_disp, default=forns_disp)

filtered = compras.copy()
if only_month:
    filtered = filtered.dropna(subset=["data"])
    filtered = filtered[filtered["data"].dt.to_period("M") == selected_month]
if cat_filter:
    filtered = filtered[filtered["categoria"].isin(cat_filter) | filtered["categoria"].isna()]
if forn_filter:
    filtered = filtered[filtered["fornecedor_nome"].isin(forn_filter) | filtered["fornecedor_nome"].isna()]

# Sort controls
sort_col, dir_col = st.columns([3, 1])
with sort_col:
    sort_by = st.selectbox(
        "Ordenar por",
        ["Data (mais recente)", "Preço total", "Preço unitário", "Produto", "Fornecedor", "ID"],
        index=0,
    )
with dir_col:
    default_asc = sort_by == "Produto" or sort_by == "Fornecedor" or sort_by == "ID"
    asc = st.selectbox(
        "Direção",
        ["Crescente ↑", "Decrescente ↓"],
        index=0 if default_asc else 1,
        key="compras_dir",
    ) == "Crescente ↑"

sort_map = {
    "Data (mais recente)": "data",
    "Preço total": "preco_total",
    "Preço unitário": "preco_unitario",
    "Produto": "produto_nome",
    "Fornecedor": "fornecedor_nome",
    "ID": "id",
}
filtered = filtered.sort_values(sort_map[sort_by], ascending=asc, na_position="last")

st.caption(f"Mostrando {len(filtered)} compra(s). Total: **{brl(filtered['preco_total'].sum())}**")

# Detailed table
disp = filtered.copy()
disp["data_str"] = disp["data"].dt.strftime("%d/%m/%Y").fillna("—")
disp["preco_total_str"] = disp["preco_total"].apply(brl)
disp["preco_unitario_str"] = disp["preco_unitario"].apply(brl)
disp["produto_disp"] = disp.apply(
    lambda r: f"{r['produto_id']} — {r['produto_nome'] or '?'}", axis=1
)

table = disp[[
    "id", "data_str", "produto_disp", "marca",
    "qtde_embalagens", "unidades_por_embalagem",
    "preco_total_str", "preco_unitario_str",
    "fornecedor_nome",
]].copy()
table.columns = [
    "ID", "Data", "Produto", "Marca",
    "Qtde emb.", "Unid./emb.",
    "Preço total", "Preço unit.", "Fornecedor",
]
st.dataframe(table, hide_index=True, use_container_width=True)


# Expandable detail for each compra
st.divider()
st.subheader("Drill-down por compra")
with st.expander("Clique pra ver detalhes individuais"):
    for _, r in filtered.head(20).iterrows():
        with st.container(border=True):
            top1, top2 = st.columns([3, 1])
            with top1:
                st.markdown(f"**{r['id']}** · {r['produto_nome']} ({r['categoria']})")
                st.caption(
                    f"{r['data'].strftime('%d/%m/%Y') if pd.notna(r['data']) else '—'} · "
                    f"{r['fornecedor_nome']} · marca: {r.get('marca') or '—'}"
                )
                if r.get("notas"):
                    st.caption(f"📝 {r['notas']}")
            with top2:
                st.metric("Total", brl(r["preco_total"]))
                st.caption(f"{r['total_unidades']:.0f} unid · {brl(r['preco_unitario'])}/un")
    if len(filtered) > 20:
        st.caption(f"…e mais {len(filtered) - 20} compra(s) (use os filtros pra refinar)")
