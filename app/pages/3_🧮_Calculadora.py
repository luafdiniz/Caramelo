"""Calculadora multi-direcional.

Seis presets, cada um responde a uma pergunta que a Luiza faz no dia a dia:

  1. Custo unitário e margem (default)
  2. Preço de venda pra atingir margem alvo
  3. Quantas unidades pra atingir meta de faturamento
  4. Quantos kg consigo produzir com orçamento X
  5. Faturamento e lucro de uma fornada
  6. Conversor preço por kg ↔ preço por unidade

A página é um shell fino sobre `app/lib/calc.py` — os solvers vivem lá.
Inputs com `st.number_input`, outputs em `compact_kpi`, warnings impressos
no rodapé.
"""

import os
import sys
import streamlit as st
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.auth import require_auth
from lib import data, calc
from lib.ui import setup_page, brl, pct, compact_kpi


setup_page("Calculadora", icon="🧮")
require_auth()

st.title("🧮 Calculadora multi-direcional")
st.caption(
    "Escolha o que quer descobrir, preencha o que sabe, o resto a tela "
    "calcula. Não muda nada na planilha — só simulação."
)


tamanhos = data.get_tamanhos()
if tamanhos.empty:
    st.info("Cadastre pelo menos um tamanho na página 🍮 Tamanhos.")
    st.stop()

# --- Tamanho selector (opcional) — pré-popula inputs ---
opts = {"— Sem tamanho base —": None}
opts.update({f"{r['id']} — {r['nome']}": r["id"] for _, r in tamanhos.iterrows()})
sel = st.selectbox("Tamanho base (opcional)", list(opts.keys()), index=1)
tamanho_id = opts[sel]

base = calc.CalcState()
if tamanho_id:
    trow = tamanhos[tamanhos["id"] == tamanho_id].iloc[0]
    peso_unit = float(trow["peso_kg"] or 0) or None
    rendimento = float(trow.get("rendimento") or 0) or None
    preco_atual = float(trow["preco_venda"]) if pd.notna(trow["preco_venda"]) else None

    custo_ali, _ = data.calc_custo_alimento_unid(tamanho_id)
    custo_emb, _ = data.calc_custo_embalagem_unid(tamanho_id)
    # custo_ali já é per unit — converter pra "receita inteira" multiplicando
    # pelo rendimento (qtde de unidades produzidas com 1 receita base).
    base.peso_unit = peso_unit
    base.peso_base_padrao = (peso_unit or 0) * (rendimento or 0) or None
    base.custo_ingredientes_padrao = (
        custo_ali * (rendimento or 0) if rendimento else None
    )
    base.custo_embalagem_unit = custo_emb
    base.preco_venda_unit = preco_atual

# --- Radio: qual preset ---
preset_key = st.radio(
    "Resolver para:",
    calc.PRESET_KEYS,
    format_func=lambda k: calc.PRESET_LABELS[k],
    horizontal=False,
)

st.divider()


def _kpi_block(state: calc.CalcState, fields: list[tuple[str, str, str]]) -> None:
    """Render KPIs. fields = list of (state_attr, label, formatter_name)."""
    cols = st.columns(min(4, len(fields)))
    for i, (attr, label, fmt) in enumerate(fields):
        with cols[i % len(cols)]:
            v = getattr(state, attr, None)
            if v is None:
                compact_kpi(label, "—")
            elif fmt == "brl":
                compact_kpi(label, brl(v))
            elif fmt == "pct":
                compact_kpi(label, pct(v))
            elif fmt == "qtde":
                compact_kpi(label, f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
            else:
                compact_kpi(label, str(v))


# --- Per-preset input + output blocks --------------------------------------

if preset_key == "custo_e_margem":
    c1, c2 = st.columns(2)
    with c1:
        base.peso_base_receita = st.number_input(
            "Peso da receita (kg)",
            min_value=0.0, value=float(base.peso_base_padrao or 1.0), step=0.5,
        ) or None
    with c2:
        base.preco_venda_unit = st.number_input(
            "Preço de venda por unidade (R$)",
            min_value=0.0, value=float(base.preco_venda_unit or 0.0), step=1.0,
        ) or None
    out = calc.solve_custo_e_margem(base)
    st.markdown("##### Resultado")
    _kpi_block(out, [
        ("qtde_unidades_produzidas", "Unidades produzidas", "qtde"),
        ("custo_unit", "Custo por unidade", "brl"),
        ("lucro_unit", "Lucro por unidade", "brl"),
        ("margem", "Margem", "pct"),
    ])

elif preset_key == "preco_para_margem":
    c1, c2 = st.columns(2)
    with c1:
        base.peso_base_receita = st.number_input(
            "Peso da receita (kg)",
            min_value=0.0, value=float(base.peso_base_padrao or 1.0), step=0.5,
        ) or None
    with c2:
        margem_alvo_pct = st.number_input(
            "Margem alvo (%)", min_value=0.0, max_value=99.0, value=50.0, step=5.0,
        )
    out = calc.solve_preco_para_margem(base, margem_alvo=margem_alvo_pct / 100)
    st.markdown("##### Resultado")
    _kpi_block(out, [
        ("custo_unit", "Custo por unidade", "brl"),
        ("preco_venda_unit", "Preço de venda sugerido", "brl"),
        ("lucro_unit", "Lucro por unidade", "brl"),
        ("preco_venda_kg", "Preço por kg", "brl"),
    ])

elif preset_key == "qtde_para_faturar":
    c1, c2 = st.columns(2)
    with c1:
        base.meta_faturamento = st.number_input(
            "Meta de faturamento (R$)", min_value=0.0, value=1000.0, step=100.0,
        ) or None
    with c2:
        base.preco_venda_unit = st.number_input(
            "Preço de venda por unidade (R$)",
            min_value=0.0, value=float(base.preco_venda_unit or 50.0), step=1.0,
        ) or None
    out = calc.solve_qtde_para_faturar(base)
    st.markdown("##### Resultado")
    _kpi_block(out, [
        ("qtde_unidades_produzidas", "Unidades a vender", "qtde"),
        ("peso_base_receita", "Peso total de massa (kg)", "qtde"),
        ("custo_total", "Custo total estimado", "brl"),
        ("lucro_total", "Lucro estimado", "brl"),
    ])

elif preset_key == "kg_com_orcamento":
    base.orcamento_insumos = st.number_input(
        "Orçamento disponível pra insumos (R$)",
        min_value=0.0, value=200.0, step=10.0,
    ) or None
    if not base.peso_base_padrao or not base.custo_ingredientes_padrao:
        st.warning(
            "Pra este preset, selecione um Tamanho base no topo — "
            "ele fornece o custo de referência da receita."
        )
    out = calc.solve_kg_com_orcamento(base)
    st.markdown("##### Resultado")
    _kpi_block(out, [
        ("peso_base_receita", "Massa que dá pra produzir (kg)", "qtde"),
        ("qtde_unidades_produzidas", "Unidades possíveis", "qtde"),
        ("faturamento", "Faturamento potencial", "brl"),
        ("lucro_total", "Lucro potencial", "brl"),
    ])

elif preset_key == "resultado_fornada":
    c1, c2, c3 = st.columns(3)
    with c1:
        base.peso_base_receita = st.number_input(
            "Peso da fornada (kg)",
            min_value=0.0, value=float(base.peso_base_padrao or 2.0), step=0.5,
        ) or None
    with c2:
        base.preco_venda_unit = st.number_input(
            "Preço de venda por unidade (R$)",
            min_value=0.0, value=float(base.preco_venda_unit or 50.0), step=1.0,
        ) or None
    with c3:
        st.metric("Peso unitário", f"{base.peso_unit or 0:.2f} kg",
                  help="Vem do Tamanho selecionado.")
    out = calc.solve_resultado_fornada(base)
    st.markdown("##### Resultado")
    _kpi_block(out, [
        ("qtde_unidades_produzidas", "Unidades", "qtde"),
        ("custo_total", "Custo total", "brl"),
        ("faturamento", "Faturamento", "brl"),
        ("lucro_total", "Lucro", "brl"),
    ])

elif preset_key == "preco_kg_unid":
    direcao = st.radio("Direção", ["Preço/un → Preço/kg", "Preço/kg → Preço/un"], horizontal=True)
    if direcao == "Preço/un → Preço/kg":
        base.preco_venda_unit = st.number_input(
            "Preço por unidade (R$)",
            min_value=0.0, value=float(base.preco_venda_unit or 50.0), step=1.0,
        ) or None
        base.preco_venda_kg = None
    else:
        base.preco_venda_kg = st.number_input(
            "Preço por kg (R$/kg)", min_value=0.0, value=80.0, step=1.0,
        ) or None
        base.preco_venda_unit = None
    out = calc.solve_preco_kg_unid(base)
    st.markdown("##### Resultado")
    _kpi_block(out, [
        ("preco_venda_unit", "Preço por unidade", "brl"),
        ("preco_venda_kg", "Preço por kg", "brl"),
        ("peso_unit", "Peso unitário (kg)", "qtde"),
    ])
else:
    out = base


for w in out.warnings:
    st.warning(w)


# --- Ação "Salvar preço de venda" — só no preset 1 quando há tamanho ---
if preset_key == "custo_e_margem" and tamanho_id and out.preco_venda_unit:
    st.divider()
    st.markdown("##### Atualizar preço de venda")
    new_price = st.number_input(
        f"Novo preço de venda pra {tamanho_id} (R$)",
        min_value=0.0,
        value=float(out.preco_venda_unit),
        step=1.0,
    )
    if st.button(f"💾 Salvar R$ {new_price:.2f} como preço de {tamanho_id}",
                 type="primary"):
        try:
            service = data.get_service()
            result = service.spreadsheets().values().get(
                spreadsheetId=data._spreadsheet_id(), range="Tamanhos!A:A"
            ).execute()
            ids = [r[0] if r else "" for r in result.get("values", [])]
            if tamanho_id in ids:
                row_num = ids.index(tamanho_id) + 1
                service.spreadsheets().values().update(
                    spreadsheetId=data._spreadsheet_id(),
                    range=f"Tamanhos!G{row_num}",
                    valueInputOption="USER_ENTERED",
                    body={"values": [[new_price]]},
                ).execute()
                data.invalidate_cache()
                st.success(f"✅ Preço de {tamanho_id} atualizado para {brl(new_price)}")
            else:
                st.error(f"Não encontrei o tamanho {tamanho_id} na planilha.")
        except Exception as e:
            st.error(f"Erro: {e}")


with st.expander("🔍 Memória de cálculo"):
    st.markdown(
        "**Base usada:**\n"
        f"- Peso unitário: {base.peso_unit}\n"
        f"- Peso da receita padrão (base): {base.peso_base_padrao}\n"
        f"- Custo de ingredientes da receita padrão: {base.custo_ingredientes_padrao}\n"
        f"- Custo de embalagem por unidade: {base.custo_embalagem_unit}\n"
        f"- Preço de venda atual: {base.preco_venda_unit}"
    )
    st.markdown("**Equações usadas estão em `app/lib/calc.py`.**")
