"""
Produção page: register a fornada and track production vs. sales.

Conceptual model:
- "Receita base" yields ~1.1kg of pudding mix (~1 forma família)
- A fornada is "I made N receitas of pudding mix and distributed across sizes"
- Distribution: for each tamanho, how many units I produced
- Outcome: per unit, how many were sold, given as cortesia, kept as test
- Cost is calculated from current Ficha Técnica per tamanho
"""

import os
import sys
from datetime import date
import streamlit as st
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.auth import require_auth
from lib import data
from lib.ui import setup_page, brl, brl_md, card_title, compact_kpi


setup_page("Produção", icon="🏭")
require_auth()

st.title("🏭 Produção (Fornadas)")
st.caption(
    "Registre cada fornada: o que produziu, em que tamanhos distribuiu, "
    "e quanto foi vendido vs. cortesia/teste."
)


# ============================================================================
# Tabs
# ============================================================================
tab_new, tab_list = st.tabs(["➕ Nova fornada", "📋 Histórico"])


with tab_new:
    tamanhos = data.get_tamanho_costs()
    if tamanhos.empty:
        st.info("Cadastre pelo menos um tamanho antes de registrar fornadas.")
        st.stop()

    st.markdown("### Dados da fornada")

    col1, col2 = st.columns(2)
    with col1:
        data_inicio = st.date_input("Data de início", value=date.today())
    with col2:
        data_fim = st.date_input("Data de fim (entrega)", value=date.today())

    notas_geral = st.text_input(
        "Observações da fornada",
        placeholder="ex: Edição de natal, fornada de teste pra lata de vela...",
    )

    st.divider()
    st.markdown("### Distribuição")
    st.caption(
        "Pra cada tamanho que você produziu, preencha quantos pudins. "
        "Não preencha o que não fez."
    )

    # Build a row per tamanho
    if "fornada_rows" not in st.session_state:
        st.session_state["fornada_rows"] = {}

    rows_data = []
    for _, t in tamanhos.iterrows():
        with st.container(border=True):
            preco_str = brl(t['preco_venda']) if pd.notna(t['preco_venda']) else '—'
            meta_str = (
                f"Custo unitário: <strong>{brl(t['custo_total'])}</strong>"
                f" · Preço cadastrado: {preco_str}"
            )
            card_title(t['nome'], badge=t['id'], meta=meta_str, meta_is_html=True)

            c1, c2, c3, c4 = st.columns(4)
            with c1:
                produzidos = st.number_input(
                    "Produzidos",
                    min_value=0, value=0, step=1,
                    key=f"prod_{t['id']}",
                )
            with c2:
                vendidos = st.number_input(
                    "Vendidos",
                    min_value=0, value=0, step=1,
                    key=f"vend_{t['id']}",
                )
            with c3:
                cortesia = st.number_input(
                    "Cortesia/influencer",
                    min_value=0, value=0, step=1,
                    key=f"cort_{t['id']}",
                )
            with c4:
                preco_efetivo = st.number_input(
                    "Preço de venda (R$)",
                    min_value=0.0,
                    value=float(t["preco_venda"]) if pd.notna(t["preco_venda"]) else 0.0,
                    step=1.0,
                    key=f"preco_{t['id']}",
                )

            teste_perda = produzidos - vendidos - cortesia
            if teste_perda < 0:
                st.error(f"Vendidos + cortesia ({vendidos + cortesia}) é maior que produzidos ({produzidos})")
            elif produzidos > 0:
                custo_total = t["custo_total"] * produzidos
                receita = vendidos * preco_efetivo
                lucro = receita - custo_total
                st.caption(
                    f"📦 Teste/perda: **{teste_perda}** · "
                    f"💰 Custo total: {brl_md(custo_total)} · "
                    f"Receita: {brl_md(receita)} · "
                    f"**Lucro: {brl_md(lucro)}**"
                )

            if produzidos > 0:
                rows_data.append({
                    "tamanho_id": t["id"],
                    "tamanho_nome": t["nome"],
                    "produzidos": produzidos,
                    "vendidos": vendidos,
                    "cortesia": cortesia,
                    "preco_efetivo": preco_efetivo,
                    "custo_unit": t["custo_total"],
                })

    # Summary
    if not rows_data:
        st.info(
            "💡 Preencha **Produzidos ≥ 1** em pelo menos um tamanho pra "
            "habilitar o botão de salvar fornada."
        )
    if rows_data:
        df = pd.DataFrame(rows_data)
        total_produzidos = df["produzidos"].sum()
        total_vendidos = df["vendidos"].sum()
        total_cortesia = df["cortesia"].sum()
        total_teste = total_produzidos - total_vendidos - total_cortesia
        total_custo = (df["produzidos"] * df["custo_unit"]).sum()
        total_receita = (df["vendidos"] * df["preco_efetivo"]).sum()
        lucro_geral = total_receita - total_custo

        st.divider()
        st.markdown("### Resumo da fornada")
        s1, s2, s3, s4, s5 = st.columns(5)
        with s1:
            compact_kpi("Total produzido", str(int(total_produzidos)))
        with s2:
            compact_kpi("Vendidos", str(int(total_vendidos)))
        with s3:
            compact_kpi("Cortesia", str(int(total_cortesia)))
        with s4:
            compact_kpi("Teste/perda", str(int(total_teste)))
        with s5:
            compact_kpi("Lucro", brl(lucro_geral))

        # Save
        if st.button("💾 Registrar fornada", type="primary", use_container_width=True):
            try:
                service = data.get_service()

                # Each (tamanho, com quantidades) vira UMA linha na aba Fornadas
                created_ids = []
                for _, r in df.iterrows():
                    new_id = data._sheets._next_id_for_prefix(
                        data._spreadsheet_id(), "Fornadas!A:A", "FN", service=service
                    )

                    existing = service.spreadsheets().values().get(
                        spreadsheetId=data._spreadsheet_id(), range="Fornadas!A:A"
                    ).execute().get("values", [])
                    next_row = len(existing) + 1

                    notas_combined = (notas_geral or "").strip()
                    if int(r["produzidos"]) - int(r["vendidos"]) - int(r["cortesia"]) > 0:
                        notas_combined += f" | Teste/perda: {int(r['produzidos']) - int(r['vendidos']) - int(r['cortesia'])}"

                    row = [[
                        new_id,
                        data_inicio.isoformat(),
                        data_fim.isoformat(),
                        r["tamanho_id"],
                        int(r["produzidos"]),
                        int(r["vendidos"]),
                        int(r["cortesia"]),
                        float(r["preco_efetivo"]),
                        f"=F{next_row}*H{next_row}",  # receita_total
                        float(r["custo_unit"]),
                        f"=J{next_row}*E{next_row}",  # custo_total
                        f"=I{next_row}-K{next_row}",  # lucro
                        notas_combined.strip(" |"),
                    ]]
                    service.spreadsheets().values().update(
                        spreadsheetId=data._spreadsheet_id(),
                        range=f"Fornadas!A{next_row}",
                        valueInputOption="USER_ENTERED",
                        body={"values": row},
                    ).execute()
                    created_ids.append(new_id)

                data.invalidate_cache()
                st.success(f"✅ Fornada registrada: {', '.join(created_ids)}")
                st.balloons()

                # Clear form session state on next render
                for key in list(st.session_state.keys()):
                    if key.startswith(("prod_", "vend_", "cort_", "preco_")):
                        del st.session_state[key]

            except Exception as e:
                st.error(f"Erro registrando fornada: {e}")
                import traceback
                st.code(traceback.format_exc())
    else:
        st.caption("Preencha pelo menos uma linha de tamanho com quantidade > 0.")


with tab_list:
    fornadas = data.get_fornadas()
    tamanhos = data.get_tamanhos()

    if fornadas.empty:
        st.info("Nenhuma fornada registrada ainda.")
    else:
        # Join tamanho name
        fornadas = fornadas.merge(
            tamanhos[["id", "nome"]].rename(columns={"id": "tamanho_id", "nome": "tamanho_nome"}),
            on="tamanho_id", how="left",
        )

        # Monthly aggregation at top
        st.markdown("### Resumo por mês")
        if fornadas["data_inicio"].notna().any():
            month_grp = fornadas.copy()
            month_grp["mes"] = month_grp["data_inicio"].dt.to_period("M")
            agg = month_grp.groupby("mes").agg(
                fornadas=("id", "count"),
                produzidos=("qtde_produzida", "sum"),
                vendidos=("qtde_vendida", "sum"),
                receita=("receita_total", "sum"),
                custo=("custo_total", "sum"),
                lucro=("lucro", "sum"),
            ).reset_index()
            agg["mes"] = agg["mes"].astype(str)
            agg["receita"] = agg["receita"].apply(brl)
            agg["custo"] = agg["custo"].apply(brl)
            agg["lucro"] = agg["lucro"].apply(brl)
            agg.columns = ["Mês", "Fornadas", "Produzidos", "Vendidos", "Receita", "Custo", "Lucro"]
            st.dataframe(agg, hide_index=True, use_container_width=True)

        st.divider()
        st.markdown("### Histórico detalhado")

        # Sort controls
        sort_col, dir_col = st.columns([3, 1])
        with sort_col:
            sort_by = st.selectbox(
                "Ordenar por",
                ["Data (mais recente)", "Lucro", "Receita", "Qtde produzida", "Qtde vendida"],
                index=0,
                key="forn_sort",
            )
        with dir_col:
            asc = st.selectbox("Direção", ["Crescente ↑", "Decrescente ↓"], index=1, key="forn_dir") == "Crescente ↑"

        sort_map = {
            "Data (mais recente)": "data_inicio",
            "Lucro": "lucro",
            "Receita": "receita_total",
            "Qtde produzida": "qtde_produzida",
            "Qtde vendida": "qtde_vendida",
        }
        disp = fornadas.sort_values(sort_map[sort_by], ascending=asc, na_position="last").copy()
        disp["data_inicio_str"] = disp["data_inicio"].dt.strftime("%d/%m/%Y")
        for _, r in disp.iterrows():
            with st.container(border=True):
                col1, col2, col3 = st.columns([2, 2, 1])
                with col1:
                    st.markdown(f"**{r['id']}** — {r['tamanho_nome']}")
                    st.caption(f"{r['data_inicio_str']} · {r.get('notas') or ''}")
                with col2:
                    st.caption(
                        f"Produzidos: **{int(r['qtde_produzida'])}** · "
                        f"Vendidos: **{int(r['qtde_vendida'])}** · "
                        f"Cortesia: **{int(r['qtde_cortesia'])}**"
                    )
                    if pd.notna(r["preco_venda_unit"]):
                        st.caption(
                            f"Preço unit.: {brl_md(r['preco_venda_unit'])} · "
                            f"Receita: {brl_md(r['receita_total'])}"
                        )
                with col3:
                    if pd.notna(r["lucro"]):
                        compact_kpi("Lucro", brl(r["lucro"]))
