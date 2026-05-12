"""Tamanhos page: view with live costs, add new, edit packaging."""

import os
import sys

import streamlit as st
import pandas as pd

# Path for lib imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.auth import require_auth
from lib import data
from lib.ui import setup_page, brl, pct


setup_page("Tamanhos")
require_auth()

st.title("🍮 Tamanhos")
st.caption("Cada formato de pudim e seu custo unitário ao vivo.")

# ---------------------------------------------------------------------------
# List view
# ---------------------------------------------------------------------------
tab_list, tab_new = st.tabs(["📋 Tamanhos cadastrados", "➕ Novo tamanho"])


with tab_list:
    if st.button("🔄 Atualizar", help="Buscar dados mais recentes da planilha"):
        data.invalidate_cache()
        st.rerun()

    df = data.get_tamanho_costs()
    if df.empty:
        st.info("Nenhum tamanho cadastrado ainda.")
    else:
        # Render as expandable cards
        for _, row in df.iterrows():
            with st.container(border=True):
                col1, col2 = st.columns([3, 2])

                with col1:
                    st.markdown(f"### {row['nome']}")
                    st.caption(f"`{row['id']}` · {row['canal']}")
                    info_bits = []
                    if pd.notna(row.get("peso_kg")):
                        info_bits.append(f"{row['peso_kg']:.2f} kg")
                    if pd.notna(row.get("volume_ml")):
                        info_bits.append(f"{int(row['volume_ml'])} ml")
                    if pd.notna(row.get("rendimento")):
                        info_bits.append(f"Rendimento {int(row['rendimento'])}/receita")
                    if info_bits:
                        st.caption(" · ".join(info_bits))

                with col2:
                    m1, m2 = st.columns(2)
                    with m1:
                        st.metric("Custo unitário", brl(row["custo_total"]))
                        st.caption(
                            f"Alimento {brl(row['custo_alimento'])} + Embalagem {brl(row['custo_embalagem'])}"
                        )
                    with m2:
                        st.metric("Preço de venda", brl(row["preco_venda"]))
                        if row["lucro"] is not None:
                            st.caption(f"Lucro {brl(row['lucro'])} · Margem {pct(row['margem'])}")
                        else:
                            st.caption("⚠️ Preço a definir")

                with st.expander("Ver composição completa"):
                    st.markdown("**🍯 Ingredientes** (mesma receita base pra todos os tamanhos)")
                    custo_ali, brk_ali = data.calc_custo_alimento_unid(row["id"])
                    if not brk_ali.empty:
                        disp_ali = brk_ali[["produto_id", "produto_nome", "qtde", "preco_unit_atual", "custo_na_receita"]].copy()
                        disp_ali["preco_unit_atual"] = disp_ali["preco_unit_atual"].apply(brl)
                        disp_ali["custo_na_receita"] = disp_ali["custo_na_receita"].apply(brl)
                        disp_ali.columns = ["Produto", "Nome", "Qtde", "Preço unit.", "Custo na receita"]
                        st.dataframe(disp_ali, hide_index=True, use_container_width=True)
                        st.caption(
                            f"Total da receita: **{brl(brk_ali['custo_na_receita'].sum())}** ÷ "
                            f"rendimento {int(row['rendimento']) if pd.notna(row['rendimento']) else '?'} = "
                            f"**{brl(custo_ali)} por unidade**"
                        )

                    st.markdown("**📦 Embalagens deste tamanho**")
                    custo_emb, brk_emb = data.calc_custo_embalagem_unid(row["id"])
                    if not brk_emb.empty:
                        disp_emb = brk_emb[["produto_id", "produto_nome", "qtde_por_unidade", "preco_unit_atual", "custo_por_unidade"]].copy()
                        disp_emb["preco_unit_atual"] = disp_emb["preco_unit_atual"].apply(brl)
                        disp_emb["custo_por_unidade"] = disp_emb["custo_por_unidade"].apply(brl)
                        disp_emb.columns = ["Produto", "Nome", "Qtde/unid", "Preço unit.", "Custo por pudim"]
                        st.dataframe(disp_emb, hide_index=True, use_container_width=True)
                    else:
                        st.info("Nenhuma embalagem associada a este tamanho.")


# ---------------------------------------------------------------------------
# New tamanho wizard
# ---------------------------------------------------------------------------
with tab_new:
    st.markdown("### Criar um novo tamanho")
    st.caption(
        "Configure peso/volume, defina o rendimento e selecione as embalagens. "
        "O custo é calculado ao vivo."
    )

    produtos = data.get_produtos()
    tamanhos_existentes = data.get_tamanhos()

    # Suggest a default rendimento based on existing tamanhos
    # Logic: rendimento = base_yield / peso_g
    # base_yield is approximated from existing tamanhos: peso × rendimento
    base_yield_g = None
    if not tamanhos_existentes.empty:
        valid = tamanhos_existentes.dropna(subset=["peso_kg", "rendimento"])
        if not valid.empty:
            base_yield_g = float((valid["peso_kg"] * valid["rendimento"]).mean() * 1000)

    with st.form("new_tamanho", clear_on_submit=False):
        col1, col2 = st.columns(2)
        with col1:
            nome = st.text_input(
                "Nome do tamanho",
                placeholder="ex: Lata Vela 350g",
                help="Como aparece no menu de venda",
            )
            peso_kg = st.number_input(
                "Peso por unidade (kg)",
                min_value=0.0, value=0.5, step=0.05, format="%.3f",
            )
            volume_ml = st.number_input(
                "Volume da forma (ml)",
                min_value=0, value=500, step=50,
            )

        with col2:
            canal = st.selectbox("Canal de venda", ["Fornada", "Pronta Entrega", "Ambos"])
            preco_venda = st.number_input(
                "Preço de venda sugerido (R$, opcional)",
                min_value=0.0, value=0.0, step=1.0,
            )

            suggested_rendimento = max(1, int(base_yield_g / (peso_kg * 1000))) if base_yield_g and peso_kg > 0 else 2
            rendimento = st.number_input(
                "Rendimento por receita base",
                min_value=1, value=suggested_rendimento,
                help=(
                    f"Quantas unidades de {peso_kg:.2f}kg uma receita base gera. "
                    f"Sugestão calculada a partir dos tamanhos atuais: {suggested_rendimento}."
                ),
            )

        notas = st.text_input("Observações (opcional)", placeholder="ex: edição limitada de Natal")

        st.markdown("**📦 Embalagens deste tamanho**")
        st.caption("Quais formas/embalagens cada unidade usa. Adicione tudo que entra no produto final.")

        # Pre-filter to packaging-relevant categorias
        pkg_options = produtos[produtos["categoria"].isin(["FOR", "EMB"])].copy() if not produtos.empty else pd.DataFrame()
        pkg_options["label"] = pkg_options["id"] + " — " + pkg_options["nome"]

        selected_pkgs = st.multiselect(
            "Selecione as embalagens",
            options=pkg_options["id"].tolist() if not pkg_options.empty else [],
            format_func=lambda x: pkg_options[pkg_options["id"] == x]["label"].iloc[0] if not pkg_options.empty else x,
            help="Pode ajustar as quantidades após confirmar",
        )

        # Show input for qty for each selected
        pkg_quantities = {}
        if selected_pkgs:
            st.caption("Quantidade de cada embalagem por unidade de pudim:")
            qty_cols = st.columns(min(3, len(selected_pkgs)))
            for i, pkg_id in enumerate(selected_pkgs):
                with qty_cols[i % len(qty_cols)]:
                    pkg_name = pkg_options[pkg_options["id"] == pkg_id]["nome"].iloc[0]
                    pkg_quantities[pkg_id] = st.number_input(
                        f"{pkg_id} ({pkg_name[:25]}…)" if len(pkg_name) > 25 else f"{pkg_id} ({pkg_name})",
                        min_value=0.0, value=1.0, step=0.05, format="%.2f",
                        key=f"qty_{pkg_id}",
                    )

        submitted = st.form_submit_button("Cadastrar tamanho", use_container_width=True, type="primary")

    if submitted:
        if not nome.strip():
            st.error("Dá um nome pro tamanho.")
            st.stop()
        if not selected_pkgs:
            st.warning("Você não selecionou nenhuma embalagem. O custo de embalagem ficará zero.")

        # Generate next TAM-NNN ID
        try:
            service = data.get_service()
            new_id = data._sheets._next_id_for_prefix(
                data._spreadsheet_id(), "Tamanhos!A:A", "TAM", service=service
            )

            # Append to Tamanhos
            tamanhos_row = [[
                new_id,
                nome.strip(),
                peso_kg,
                volume_ml,
                int(rendimento),
                canal,
                preco_venda if preco_venda > 0 else "",
                notas.strip(),
            ]]
            # Find next empty row
            existing = service.spreadsheets().values().get(
                spreadsheetId=data._spreadsheet_id(), range="Tamanhos!A:A"
            ).execute().get("values", [])
            next_row = len(existing) + 1
            service.spreadsheets().values().update(
                spreadsheetId=data._spreadsheet_id(),
                range=f"Tamanhos!A{next_row}",
                valueInputOption="USER_ENTERED",
                body={"values": tamanhos_row},
            ).execute()

            # Append to Embalagens_Por_Tamanho
            if selected_pkgs:
                emb_rows = []
                for pkg_id, qty in pkg_quantities.items():
                    emb_rows.append([
                        new_id,
                        pkg_id,
                        f"=VLOOKUP(B{{ROW}};Produtos!A:B;2;FALSE)",  # filled per-row below
                        qty,
                    ])
                # Replace placeholder with actual row numbers
                existing_emb = service.spreadsheets().values().get(
                    spreadsheetId=data._spreadsheet_id(), range="Embalagens_Por_Tamanho!A:A"
                ).execute().get("values", [])
                emb_next_row = len(existing_emb) + 1
                rendered = []
                for i, r in enumerate(emb_rows):
                    row_num = emb_next_row + i
                    rendered.append([
                        r[0], r[1],
                        f"=VLOOKUP(B{row_num};Produtos!A:B;2;FALSE)",
                        r[3],
                    ])
                service.spreadsheets().values().update(
                    spreadsheetId=data._spreadsheet_id(),
                    range=f"Embalagens_Por_Tamanho!A{emb_next_row}",
                    valueInputOption="USER_ENTERED",
                    body={"values": rendered},
                ).execute()

            data.invalidate_cache()
            st.success(f"✅ Tamanho **{new_id} — {nome}** criado!")
            st.balloons()

            # Show preview of the cost
            try:
                custo_ali, _ = data.calc_custo_alimento_unid(new_id)
                custo_emb, _ = data.calc_custo_embalagem_unid(new_id)
                st.markdown(
                    f"**Custo unitário inicial:** {brl(custo_ali + custo_emb)} "
                    f"(alimento {brl(custo_ali)} + embalagem {brl(custo_emb)})"
                )
            except Exception:
                pass

        except Exception as e:
            st.error(f"Erro cadastrando: {e}")
            import traceback
            st.code(traceback.format_exc())
