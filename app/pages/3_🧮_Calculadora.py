"""Calculadora page: cost breakdown + price/margin simulator."""

import os
import sys
import streamlit as st
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.auth import require_auth
from lib import data
from lib.ui import setup_page, brl, pct, compact_kpi


setup_page("Calculadora", icon="🧮")
require_auth()

st.title("🧮 Calculadora de preço e margem")
st.caption(
    "Veja o custo unitário ao vivo e simule diferentes preços de venda. "
    "Não muda nada na planilha — só uma calculadora visual."
)

tamanhos = data.get_tamanhos()
if tamanhos.empty:
    st.info("Cadastre pelo menos um tamanho na página 🍮 Tamanhos.")
    st.stop()

# Selector
opts = {f"{r['id']} — {r['nome']}": r["id"] for _, r in tamanhos.iterrows()}
sel = st.selectbox("Tamanho", list(opts.keys()))
tamanho_id = opts[sel]

custo_ali, _ = data.calc_custo_alimento_unid(tamanho_id)
custo_emb, _ = data.calc_custo_embalagem_unid(tamanho_id)
custo_total = custo_ali + custo_emb
preco_atual = tamanhos[tamanhos["id"] == tamanho_id]["preco_venda"].iloc[0]
preco_atual = float(preco_atual) if pd.notna(preco_atual) else None

# KPIs
k1, k2, k3, k4 = st.columns(4)
with k1:
    compact_kpi("Custo alimento", brl(custo_ali))
with k2:
    compact_kpi("Custo embalagem", brl(custo_emb))
with k3:
    compact_kpi("Custo total/unid", brl(custo_total))
with k4:
    if preco_atual:
        lucro = preco_atual - custo_total
        margem = lucro / preco_atual if preco_atual > 0 else 0
        compact_kpi("Margem atual", pct(margem), help=f"Lucro: {brl(lucro)}")
    else:
        compact_kpi("Margem atual", "—", help="Preço não definido")

st.divider()

# --- Simulador 1: preço por margem desejada ---
st.markdown("#### Simulação 1 — qual preço pra cada margem")

margens = [10, 20, 30, 40, 50, 60, 70, 80]
rows1 = []
for m in margens:
    price = custo_total / (1 - m / 100) if (1 - m / 100) > 0 else None
    lucro = price - custo_total if price else None
    rows1.append({
        "Margem desejada": f"{m}%",
        "Preço de venda": brl(price),
        "Lucro / unidade": brl(lucro),
    })
st.dataframe(pd.DataFrame(rows1), hide_index=True, use_container_width=True)


# --- Simulador 2: margem por preço fixado ---
st.markdown("#### Simulação 2 — margem em diferentes preços")

sim_c1, sim_c2, sim_c3 = st.columns(3)
with sim_c1:
    preco_min = float(st.number_input(
        "Preço mínimo (R$)",
        min_value=0.0, value=float(round(custo_total)), step=5.0,
    ))
with sim_c2:
    preco_max = float(st.number_input(
        "Preço máximo (R$)",
        min_value=preco_min, value=preco_min + 60, step=5.0,
    ))
with sim_c3:
    step = float(st.number_input("Passo (R$)", min_value=1.0, value=5.0, step=1.0))

rows2 = []
p = preco_min
while p <= preco_max:
    lucro = p - custo_total
    margem = lucro / p if p > 0 else 0
    rows2.append({
        "Preço de venda": brl(p),
        "Lucro / unidade": brl(lucro),
        "Margem": pct(margem),
    })
    p += step
st.dataframe(pd.DataFrame(rows2), hide_index=True, use_container_width=True)


# --- Quick action: salvar preço ---
st.divider()
st.markdown("#### Salvar preço de venda")
st.caption("Atualiza o preço de venda deste tamanho na planilha (campo Preco_Venda).")

new_price = st.number_input(
    "Novo preço de venda (R$)",
    min_value=0.0,
    value=float(preco_atual) if preco_atual else float(round(custo_total * 2)),
    step=1.0,
)

if st.button(f"Salvar R$ {new_price:.2f} como preço de {tamanho_id}", type="primary"):
    try:
        service = data.get_service()
        # Find row of this tamanho
        result = service.spreadsheets().values().get(
            spreadsheetId=data._spreadsheet_id(), range="Tamanhos!A:A"
        ).execute()
        ids = [r[0] if r else "" for r in result.get("values", [])]
        if tamanho_id in ids:
            row_num = ids.index(tamanho_id) + 1
            service.spreadsheets().values().update(
                spreadsheetId=data._spreadsheet_id(),
                range=f"Tamanhos!G{row_num}",  # G = Preco_Venda
                valueInputOption="USER_ENTERED",
                body={"values": [[new_price]]},
            ).execute()
            data.invalidate_cache()
            st.success(f"✅ Preço de {tamanho_id} atualizado para {brl(new_price)}")
        else:
            st.error(f"Não encontrei o tamanho {tamanho_id} na planilha.")
    except Exception as e:
        st.error(f"Erro: {e}")
