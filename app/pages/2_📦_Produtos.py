"""Produtos page: list, filter, drill into price history and supplier analysis."""

import os
import sys
import streamlit as st
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.auth import require_auth
from lib import data
from lib.ui import setup_page, brl


setup_page("Produtos", icon="📦")
require_auth()

st.title("📦 Produtos")
st.caption("Catálogo, preço atual e histórico por fornecedor.")


# --- Load -----
produtos = data.get_produtos()
compras = data.get_compras()
fornecedores = data.get_fornecedores()

if produtos.empty:
    st.info("Nenhum produto cadastrado.")
    st.stop()

# Compute latest price and statistics per produto
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
for k in ["preco_atual", "menor", "maior", "media", "n_compras", "fornecedor_atual"]:
    prods_enriched[k] = [s[k] for s in stats_records]


# --- Filters -----
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

filtered = prods_enriched[prods_enriched["categoria"].isin(cat_filter)]
if search:
    s = search.lower()
    filtered = filtered[
        filtered["id"].str.lower().str.contains(s)
        | filtered["nome"].str.lower().str.contains(s)
    ]

st.caption(f"{len(filtered)} de {len(prods_enriched)} produtos")


# --- Table ----
CAT_EMOJI = {"ALI": "🍯", "FOR": "🥣", "EMB": "📦", "EQP": "🔧", "OPR": "🧻"}

for _, p in filtered.iterrows():
    emoji = CAT_EMOJI.get(p["categoria"], "•")
    with st.container(border=True):
        head_col1, head_col2, head_col3 = st.columns([3, 2, 2])
        with head_col1:
            st.markdown(f"### {emoji} {p['nome']}")
            st.caption(f"`{p['id']}` · {p['categoria']} · unidade: {p['unidade']}")
            if p.get("notas"):
                st.caption(f"📝 {p['notas']}")
        with head_col2:
            st.metric(
                "Preço unitário atual",
                brl(p["preco_atual"]),
                help=(
                    f"Última compra: {p['ultima_data'].strftime('%d/%m/%Y')}"
                    if p["ultima_data"] is not None else "Sem compras"
                ),
            )
        with head_col3:
            st.metric("Compras registradas", str(int(p["n_compras"])))

        if int(p["n_compras"]) > 0:
            with st.expander("📊 Histórico e análise por fornecedor"):
                sub = compras[compras["produto_id"] == p["id"]].dropna(subset=["data"]).copy()
                sub = sub.sort_values("data")

                # KPIs
                k1, k2, k3 = st.columns(3)
                with k1:
                    st.metric("Menor preço histórico", brl(p["menor"]))
                with k2:
                    st.metric("Preço médio", brl(p["media"]))
                with k3:
                    st.metric("Maior preço histórico", brl(p["maior"]))

                # Price evolution chart
                if len(sub) > 1:
                    st.markdown("**Evolução do preço unitário**")
                    chart_df = sub[["data", "preco_unitario", "fornecedor_id"]].copy()
                    chart_df["fornecedor_nome"] = chart_df["fornecedor_id"].map(
                        dict(zip(fornecedores["id"], fornecedores["nome"]))
                    )
                    st.line_chart(
                        chart_df.set_index("data")[["preco_unitario"]],
                        height=240,
                    )

                # Per-supplier analysis
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

                # Identify the cheapest reliable supplier (>= 2 compras and best avg)
                # Suppliers with only 1 compra are flagged as "amostra pequena"
                reliable = by_supplier[by_supplier["n_compras"] >= 2]
                cheapest_id = None
                if not reliable.empty:
                    cheapest_id = reliable.loc[reliable["preco_medio"].idxmin(), "fornecedor_id"]

                # Show table with badges
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
                st.dataframe(disp, hide_index=True, use_container_width=True)

                # Outlier detection — flag purchases >50% above the median
                median_price = sub["preco_unitario"].median()
                outliers = sub[sub["preco_unitario"] > median_price * 1.5]
                if not outliers.empty and median_price > 0:
                    st.warning(
                        f"⚠️ {len(outliers)} compra(s) ficaram >50% acima da mediana ({brl(median_price)}). "
                        "Pode ser emergência ou erro — confere se faz sentido:"
                    )
                    out_disp = outliers.copy().merge(
                        fornecedores[["id", "nome"]].rename(columns={"id": "fornecedor_id", "nome": "fornecedor_nome"}),
                        on="fornecedor_id", how="left",
                    )
                    out_disp["data"] = out_disp["data"].dt.strftime("%d/%m/%Y")
                    out_disp["preco_unitario"] = out_disp["preco_unitario"].apply(brl)
                    out_disp = out_disp[["data", "fornecedor_nome", "marca", "preco_unitario", "notas"]]
                    out_disp.columns = ["Data", "Fornecedor", "Marca", "Preço unit.", "Notas"]
                    st.dataframe(out_disp, hide_index=True, use_container_width=True)

                if cheapest_id and len(reliable) >= 2:
                    forn_name = fornecedores[fornecedores["id"] == cheapest_id]["nome"].iloc[0]
                    avg_cheapest = reliable[reliable["fornecedor_id"] == cheapest_id]["preco_medio"].iloc[0]
                    avg_overall = sub["preco_unitario"].mean()
                    pct_diff = (avg_overall - avg_cheapest) / avg_overall * 100
                    if pct_diff > 5:
                        st.info(
                            f"💡 **{forn_name}** tem o melhor histórico de preço pra este produto "
                            f"({brl(avg_cheapest)} médio, "
                            f"{pct_diff:.0f}% abaixo da média geral)."
                        )
