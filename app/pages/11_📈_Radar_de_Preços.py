"""Radar de Preços — histórico do scanner (bot/scanner) por insumo.

Lê Precos_Observados e mostra, por insumo, a evolução do melhor preço/un
entregue ao longo do tempo, com mín/máx e onde o preço de hoje cai na faixa.
Versão viva do Artifact (regenerado à mão); aqui sempre reflete a planilha.
"""

from __future__ import annotations

import os
import sys
import streamlit as st
import pandas as pd
import altair as alt

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.auth import require_auth
from lib import data
from lib.ui import setup_page, brl


ACCENT = "#b06a2c"
GRID = "#c9bda9"

setup_page("Radar de Preços", icon="📈")
require_auth()

st.title("📈 Radar de Preços")
st.caption(
    "Melhor preço encontrado de cada insumo pelo scanner, **por unidade e com "
    "frete rateado** — o que sai de verdade por pudim ou forma. Uma linha = o "
    "preço do dia no site mais barato. As quedas continuam sendo avisadas na "
    "hora, à parte."
)

col_a, col_b = st.columns([1, 4])
with col_a:
    if st.button("🔄 Atualizar", use_container_width=True):
        data.invalidate_cache()
        st.rerun()

if not data._has_sheet("Precos_Observados"):
    st.warning("A aba **Precos_Observados** ainda não existe — o scanner não rodou nenhuma vez.")
    st.stop()

obs = data.get_precos_observados()
if obs.empty:
    st.info("Ainda não há observações registradas.")
    st.stop()

alertas = data.get_scanner_alertas()
produtos = data.get_produtos()
nome_by_insumo = dict(zip(produtos["id"], produtos["nome"])) if not produtos.empty else {}

# scanner_id -> nome amigável do insumo (fallback pro termo de busca / id)
nome_by_scanner = {}
ativos = []
for _, a in alertas.iterrows():
    if not a["ativo"]:
        continue
    ativos.append(a["scanner_id"])
    nome_by_scanner[a["scanner_id"]] = (
        nome_by_insumo.get(a["insumo_id"]) or a["termo_busca"] or a["scanner_id"]
    )

# Só os vencedores (a linha do melhor preço); non-winner rows são pra gráfico por-site futuro.
win = obs[obs["is_best"] & (obs["preco_unidade"] > 0)].copy()
win["dia"] = win["timestamp"].dt.normalize()

hoje = obs["timestamp"].max()
st.caption(f"Atualizado até **{hoje.strftime('%d/%m/%Y %H:%M')}** · {len(obs)} leituras registradas.")


def _daily_best(scanner_id: str) -> pd.DataFrame:
    """Menor preço/un por dia (com o site desse menor)."""
    d = win[win["scanner_id"] == scanner_id]
    if d.empty:
        return d
    idx = d.groupby("dia")["preco_unidade"].idxmin()
    out = d.loc[idx, ["dia", "preco_unidade", "site"]].sort_values("dia")
    return out.rename(columns={"dia": "date", "preco_unidade": "preco"})


def _tag(pos: float) -> str:
    if pos <= 0.34:
        return "🟢 tá barato"
    if pos >= 0.66:
        return "🔴 tá caro"
    return "🟡 no meio"


def render_card(scanner_id: str):
    serie = _daily_best(scanner_id)
    nome = nome_by_scanner.get(scanner_id, scanner_id)
    st.markdown(f"#### {nome}")
    if serie.empty:
        st.caption("Sem dados.")
        return

    mn = float(serie["preco"].min())
    mx = float(serie["preco"].max())
    cur = serie.iloc[-1]
    pos = (cur["preco"] - mn) / (mx - mn) if mx > mn else 0.5

    m1, m2 = st.columns([1, 1])
    m1.metric("Agora", brl(cur["preco"]), help=f"Site mais barato hoje: {cur['site']}")
    m2.metric("Situação", _tag(pos), help=f"mín {brl(mn)} · máx {brl(mx)} nos últimos meses")

    pad = (mx - mn) * 0.12 or 0.5
    line = (
        alt.Chart(serie)
        .mark_line(color=ACCENT, strokeWidth=2, interpolate="monotone")
        .encode(
            x=alt.X("date:T", title=None, axis=alt.Axis(format="%d/%m", tickCount=5, grid=False)),
            y=alt.Y(
                "preco:Q", title=None,
                scale=alt.Scale(domain=[mn - pad, mx + pad]),
                axis=alt.Axis(format="$.2f", grid=True, gridColor="#efe7d9", tickCount=4),
            ),
            tooltip=[
                alt.Tooltip("date:T", title="Dia", format="%d/%m/%Y"),
                alt.Tooltip("preco:Q", title="R$/un", format=".2f"),
                alt.Tooltip("site:N", title="Site"),
            ],
        )
    )
    rules = (
        alt.Chart(pd.DataFrame({"y": [mn, mx]}))
        .mark_rule(strokeDash=[3, 4], color=GRID)
        .encode(y="y:Q")
    )
    endpoint = (
        alt.Chart(serie.iloc[[-1]])
        .mark_point(color=ACCENT, filled=True, size=70)
        .encode(x="date:T", y="preco:Q")
    )
    chart = (rules + line + endpoint).properties(height=240).configure_view(strokeWidth=0)
    st.altair_chart(chart, use_container_width=True)


# 2 por linha
for i in range(0, len(ativos), 2):
    cols = st.columns(2)
    for col, scn in zip(cols, ativos[i:i + 2]):
        with col:
            render_card(scn)

st.divider()
st.caption(
    "Cada ponto é o site mais barato daquele dia — quando um site some da busca, "
    "a linha pula pro próximo mais barato, então um degrau pode ser troca de loja, "
    "não só mudança de preço. Desde 30/09 o scanner guarda todos os sites; em breve "
    "dá pra comparar loja por loja aqui."
)
