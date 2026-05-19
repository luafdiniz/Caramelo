"""
Pudim Caramelo — admin dashboard.

Entry point. Streamlit auto-discovers pages from the pages/ directory.
"""

import streamlit as st
import pandas as pd

from lib.auth import require_auth
from lib import data
from lib.ui import setup_page, brl, kpi, brand_header


setup_page("Painel")
require_auth()

brand_header("Pudim Caramelo", "gostoso demais 🍯")

# Top KPIs
col1, col2, col3, col4 = st.columns(4)

try:
    tamanhos = data.get_tamanho_costs()
    produtos = data.get_produtos()
    compras = data.get_compras()
    fornadas = data.get_fornadas()
except Exception as e:
    st.error(f"Erro lendo planilha: {e}")
    st.stop()

with col1:
    kpi("Tamanhos cadastrados", str(len(tamanhos)))

with col2:
    kpi("Insumos no catálogo", str(len(produtos)))

with col3:
    if not compras.empty and compras["data"].notna().any():
        this_month = compras[compras["data"].dt.to_period("M") == pd.Timestamp.now().to_period("M")]
        total_mes = this_month["preco_total"].sum() if not this_month.empty else 0
        kpi("Gasto este mês", brl(total_mes), help="Total em Compras do mês corrente")
    else:
        kpi("Gasto este mês", brl(0))

with col4:
    kpi("Fornadas registradas", str(len(fornadas)))


st.divider()

# Quick links
st.subheader("Acessar")
nav_col1, nav_col2, nav_col3 = st.columns(3)
with nav_col1:
    st.page_link("pages/1_🍮_Tamanhos.py", label="🍮 Tamanhos")
    st.page_link("pages/2_📦_Insumos.py", label="📦 Insumos")
with nav_col2:
    st.page_link("pages/3_🧮_Calculadora.py", label="🧮 Calculadora")
    st.page_link("pages/4_🏭_Produção.py", label="🏭 Produção")
with nav_col3:
    st.page_link("pages/5_🛒_Compras.py", label="🛒 Compras")


# Latest activity
st.divider()
st.subheader("Últimas compras")
if not compras.empty:
    latest = compras.sort_values("data", ascending=False).head(5).merge(
        produtos[["id", "nome"]].rename(columns={"id": "produto_id", "nome": "produto_nome"}),
        on="produto_id", how="left"
    )
    display = latest[["data", "produto_nome", "marca", "preco_total", "fornecedor_id"]].copy()
    display["data"] = display["data"].dt.strftime("%d/%m/%Y")
    display["preco_total"] = display["preco_total"].apply(brl)
    display.columns = ["Data", "Produto", "Marca", "Preço total", "Fornecedor"]
    # Read-only summary — `st.table` matches the brand-styled look used
    # across the rest of the app (Vendas histórico, Receita ingredientes).
    st.table(display.set_index("Data"))
else:
    st.info("Nenhuma compra registrada ainda.")


# Supplier recommendations
st.divider()
st.subheader("💡 Recomendações de fornecedores")
st.caption(
    "Pra produtos comprados em mais de um fornecedor, com pelo menos 2 compras em cada, "
    "identifico onde o preço médio é menor."
)

if not compras.empty:
    fornecedores = data.get_fornecedores()
    recs = []
    for prod_id in compras["produto_id"].dropna().unique():
        sub = compras[compras["produto_id"] == prod_id].dropna(subset=["data", "preco_unitario"])
        if len(sub) < 4:
            continue
        by_supplier = sub.groupby("fornecedor_id").agg(
            n=("id", "count"),
            avg_price=("preco_unitario", "mean"),
        ).reset_index()
        # Need at least 2 suppliers with 2+ compras to recommend
        reliable = by_supplier[by_supplier["n"] >= 2]
        if len(reliable) < 2:
            continue
        avg_overall = sub["preco_unitario"].mean()
        cheapest = reliable.loc[reliable["avg_price"].idxmin()]
        pct_savings = (avg_overall - cheapest["avg_price"]) / avg_overall * 100
        if pct_savings < 5:
            continue
        prod_name = produtos[produtos["id"] == prod_id]["nome"].iloc[0] if prod_id in produtos["id"].values else prod_id
        forn_name = fornecedores[fornecedores["id"] == cheapest["fornecedor_id"]]["nome"].iloc[0] if cheapest["fornecedor_id"] in fornecedores["id"].values else cheapest["fornecedor_id"]
        recs.append({
            "produto": f"{prod_id} — {prod_name}",
            "fornecedor": forn_name,
            "preco_medio": brl(cheapest["avg_price"]),
            "vs_media": f"{pct_savings:.0f}% mais barato",
        })

    if recs:
        rec_df = pd.DataFrame(recs).sort_values("vs_media", ascending=False)
        rec_df.columns = ["Produto", "Fornecedor recomendado", "Preço médio neles", "Comparado à média geral"]
        st.table(rec_df.set_index("Produto"))
    else:
        st.info("Conforme você registrar mais compras, recomendações vão aparecer aqui.")
