"""Tamanhos page: view with live costs, add new, edit packaging."""

import os
import sys

import streamlit as st
import pandas as pd

# Path for lib imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.auth import require_auth
from lib import data
from lib.ui import setup_page, brl, brl_md, pct, compact_kpi, card_title


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
    produtos_df = data.get_produtos()
    if df.empty:
        st.info("Nenhum tamanho cadastrado ainda.")
    else:
        # Sort controls
        sort_col, dir_col = st.columns([3, 1])
        with sort_col:
            sort_by = st.selectbox(
                "Ordenar por",
                ["Nome (A-Z)", "Peso (kg)", "Custo unitário", "Preço de venda", "Margem", "Lucro/unid"],
                index=0,
            )
        with dir_col:
            asc = st.selectbox("Direção", ["Crescente ↑", "Decrescente ↓"], index=0) == "Crescente ↑"

        sort_map = {
            "Nome (A-Z)": "nome",
            "Peso (kg)": "peso_kg",
            "Custo unitário": "custo_total",
            "Preço de venda": "preco_venda",
            "Margem": "margem",
            "Lucro/unid": "lucro",
        }
        df = df.sort_values(sort_map[sort_by], ascending=asc, na_position="last")
        # Render as expandable cards
        for _, row in df.iterrows():
            # Surface auto-added relacionados from the previous save, if any.
            _auto_key = f"_auto_added_{row['id']}"
            if _auto_key in st.session_state:
                st.info(f"💡 {row['id']}: auto-incluí {st.session_state[_auto_key]} (relacionados).")
                del st.session_state[_auto_key]
            with st.container(border=True):
                col1, col2 = st.columns([3, 2])

                with col1:
                    info_bits = [row["canal"]]
                    if pd.notna(row.get("peso_kg")):
                        info_bits.append(f"{row['peso_kg']:.2f} kg")
                    if pd.notna(row.get("volume_ml")):
                        info_bits.append(f"{int(row['volume_ml'])} ml")
                    if pd.notna(row.get("rendimento")):
                        info_bits.append(f"Rendimento {int(row['rendimento'])}/receita")
                    card_title(row["nome"], badge=row["id"], meta=" · ".join(info_bits))

                with col2:
                    m1, m2 = st.columns(2)
                    with m1:
                        compact_kpi("Custo unitário", brl(row["custo_total"]))
                        st.caption(
                            f"Alimento {brl_md(row['custo_alimento'])} + Embalagem {brl_md(row['custo_embalagem'])}"
                        )
                    with m2:
                        compact_kpi("Preço de venda", brl(row["preco_venda"]))
                        if pd.notna(row.get("preco_venda")) and pd.notna(row.get("lucro")):
                            st.caption(f"Lucro {brl_md(row['lucro'])} · Margem {pct(row['margem'])}")
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
                        st.table(disp_ali.set_index("Produto"))
                        st.caption(
                            f"Total da receita: **{brl_md(brk_ali['custo_na_receita'].sum())}** ÷ "
                            f"rendimento {int(row['rendimento']) if pd.notna(row['rendimento']) else '?'} = "
                            f"**{brl_md(custo_ali)} por unidade**"
                        )

                    st.markdown("**📦 Embalagens deste tamanho**")
                    custo_emb, brk_emb = data.calc_custo_embalagem_unid(row["id"])
                    if not brk_emb.empty:
                        disp_emb = brk_emb[["produto_id", "produto_nome", "qtde_por_unidade", "preco_unit_atual", "custo_por_unidade"]].copy()
                        disp_emb["preco_unit_atual"] = disp_emb["preco_unit_atual"].apply(brl)
                        disp_emb["custo_por_unidade"] = disp_emb["custo_por_unidade"].apply(brl)
                        disp_emb.columns = ["Produto", "Nome", "Qtde/unid", "Preço unit.", "Custo por pudim"]
                        st.table(disp_emb.set_index("Produto"))
                    else:
                        st.info("Nenhuma embalagem associada a este tamanho.")

                    # --- Edit section ---
                    st.divider()
                    st.markdown("**✏️ Editar este tamanho**")
                    with st.form(f"edit_{row['id']}"):
                        ec1, ec2 = st.columns(2)
                        with ec1:
                            new_preco = st.number_input(
                                "Preço de venda (R$)",
                                min_value=0.0,
                                value=float(row["preco_venda"]) if pd.notna(row.get("preco_venda")) else 0.0,
                                step=1.0,
                            )
                            new_rendimento = st.number_input(
                                "Rendimento (unidades por receita)",
                                min_value=1,
                                value=int(row["rendimento"]) if pd.notna(row.get("rendimento")) else 1,
                            )
                        with ec2:
                            canais = ["Fornada", "Pronta Entrega", "Ambos"]
                            current_canal = row.get("canal") or "Fornada"
                            new_canal = st.selectbox(
                                "Canal",
                                canais,
                                index=canais.index(current_canal) if current_canal in canais else 0,
                            )

                        # Edit packaging: show current + allow add/remove
                        st.markdown("**Embalagens deste tamanho**")
                        st.caption("Ajuste qtde de cada uma. Pra remover, deixe a qtde em 0.")
                        current_pkgs = brk_emb[["produto_id", "produto_nome", "qtde_por_unidade"]].copy() if not brk_emb.empty else pd.DataFrame(columns=["produto_id", "produto_nome", "qtde_por_unidade"])

                        edited_qtys = {}
                        for _, pkg in current_pkgs.iterrows():
                            edited_qtys[pkg["produto_id"]] = st.number_input(
                                f"{pkg['produto_id']} — {pkg['produto_nome']}",
                                min_value=0.0,
                                value=float(pkg["qtde_por_unidade"]) if pd.notna(pkg.get("qtde_por_unidade")) else 1.0,
                                step=0.05, format="%.2f",
                                key=f"edit_qty_{row['id']}_{pkg['produto_id']}",
                            )

                        # Add new packaging
                        all_pkg_opts = produtos_df[produtos_df["categoria"].isin(["FOR", "EMB"])].copy() if not produtos_df.empty else pd.DataFrame()
                        already_in = set(current_pkgs["produto_id"].tolist())
                        new_pkg_opts = all_pkg_opts[~all_pkg_opts["id"].isin(already_in)]
                        new_pkg_opts["label"] = new_pkg_opts["id"] + " — " + new_pkg_opts["nome"]
                        added_pkgs = st.multiselect(
                            "Adicionar novas embalagens",
                            options=new_pkg_opts["id"].tolist(),
                            format_func=lambda x: new_pkg_opts[new_pkg_opts["id"] == x]["label"].iloc[0],
                            key=f"add_pkg_{row['id']}",
                        )
                        for npkg in added_pkgs:
                            edited_qtys[npkg] = st.number_input(
                                f"Qtde de {npkg}",
                                min_value=0.0, value=1.0, step=0.05, format="%.2f",
                                key=f"new_qty_{row['id']}_{npkg}",
                            )

                        if st.form_submit_button("💾 Salvar alterações", use_container_width=True, type="primary"):
                            try:
                                service = data.get_service()
                                ssid = data._spreadsheet_id()

                                # Auto-include relacionados: if any selected produto has related
                                # IDs configured in the Produtos.Relacionados column, add them
                                # too (default qty 1) before saving.
                                auto_added = []
                                if not produtos_df.empty:
                                    for pid in list(edited_qtys.keys()):
                                        prod_row = produtos_df[produtos_df["id"] == pid]
                                        if prod_row.empty:
                                            continue
                                        rels = prod_row.iloc[0].get("relacionados") or []
                                        if not isinstance(rels, list):
                                            rels = []
                                        for rel_id in rels:
                                            if rel_id not in edited_qtys:
                                                edited_qtys[rel_id] = 1.0
                                                auto_added.append(rel_id)

                                # Find tamanho row number
                                all_ids = service.spreadsheets().values().get(
                                    spreadsheetId=ssid, range="Tamanhos!A:A"
                                ).execute().get("values", [])
                                row_num = next(
                                    i + 1 for i, r in enumerate(all_ids)
                                    if r and r[0] == row["id"]
                                )

                                # Update Tamanhos row (E=rendimento, F=canal, G=preco_venda)
                                service.spreadsheets().values().update(
                                    spreadsheetId=ssid,
                                    range=f"Tamanhos!E{row_num}:G{row_num}",
                                    valueInputOption="USER_ENTERED",
                                    body={"values": [[int(new_rendimento), new_canal, new_preco if new_preco > 0 else ""]]},
                                ).execute()

                                # Replace Embalagens_Por_Tamanho rows: delete old, insert new
                                emb_all = service.spreadsheets().values().get(
                                    spreadsheetId=ssid, range="Embalagens_Por_Tamanho!A2:D"
                                ).execute().get("values", [])
                                kept = [r for r in emb_all if r and r[0] != row["id"]]

                                # Append new packaging rows for this tamanho
                                final_pkgs = [(pid, q) for pid, q in edited_qtys.items() if q > 0]
                                for pid, q in final_pkgs:
                                    kept.append([row["id"], pid, "", q])

                                # Clear and rewrite the entire block
                                service.spreadsheets().values().clear(
                                    spreadsheetId=ssid, range="Embalagens_Por_Tamanho!A2:D"
                                ).execute()
                                if kept:
                                    # Re-render VLOOKUP for column C
                                    rewritten = []
                                    for i, r in enumerate(kept):
                                        rn = i + 2
                                        rewritten.append([
                                            r[0], r[1],
                                            f"=VLOOKUP(B{rn};Produtos!A:B;2;FALSE)",
                                            r[3],
                                        ])
                                    service.spreadsheets().values().update(
                                        spreadsheetId=ssid,
                                        range="Embalagens_Por_Tamanho!A2",
                                        valueInputOption="USER_ENTERED",
                                        body={"values": rewritten},
                                    ).execute()

                                data.invalidate_cache()
                                if auto_added:
                                    st.session_state[f"_auto_added_{row['id']}"] = ", ".join(auto_added)
                                st.success(f"✅ {row['id']} atualizado!")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Erro: {e}")
                                import traceback
                                st.code(traceback.format_exc())

                    # --- Delete section (outside the edit form) ---
                    st.divider()
                    st.markdown("**🗑️ Deletar este tamanho**")
                    confirm_key = f"confirm_del_tam_{row['id']}"
                    if st.session_state.get(confirm_key):
                        st.error(
                            f"Confirma deletar **{row['id']} — {row['nome']}**? "
                            "As embalagens vinculadas também serão removidas. Esta ação é irreversível."
                        )
                        cdc1, cdc2 = st.columns(2)
                        with cdc1:
                            if st.button("✅ Sim, deletar", key=f"do_del_tam_{row['id']}", type="primary"):
                                try:
                                    service = data.get_service()
                                    ssid = data._spreadsheet_id()
                                    # 1. Remove Tamanho row
                                    row_num = data.find_row_by_id("Tamanhos", row["id"])
                                    data.delete_row("Tamanhos", row_num)
                                    # 2. Remove all Embalagens_Por_Tamanho rows for this tamanho
                                    emb_all = service.spreadsheets().values().get(
                                        spreadsheetId=ssid, range="Embalagens_Por_Tamanho!A2:D"
                                    ).execute().get("values", [])
                                    kept = [r for r in emb_all if r and r[0] != row["id"]]
                                    service.spreadsheets().values().clear(
                                        spreadsheetId=ssid, range="Embalagens_Por_Tamanho!A2:D"
                                    ).execute()
                                    if kept:
                                        rewritten = []
                                        for i, r in enumerate(kept):
                                            rn = i + 2
                                            rewritten.append([
                                                r[0], r[1],
                                                f"=VLOOKUP(B{rn};Produtos!A:B;2;FALSE)",
                                                r[3] if len(r) > 3 else "",
                                            ])
                                        service.spreadsheets().values().update(
                                            spreadsheetId=ssid,
                                            range="Embalagens_Por_Tamanho!A2",
                                            valueInputOption="USER_ENTERED",
                                            body={"values": rewritten},
                                        ).execute()
                                    data.invalidate_cache()
                                    del st.session_state[confirm_key]
                                    st.success(f"✅ {row['id']} e suas embalagens foram removidos.")
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Erro: {e}")
                        with cdc2:
                            if st.button("❌ Cancelar", key=f"cancel_del_tam_{row['id']}"):
                                del st.session_state[confirm_key]
                                st.rerun()
                    else:
                        if st.button(f"🗑️ Deletar {row['id']}", key=f"req_del_tam_{row['id']}"):
                            st.session_state[confirm_key] = True
                            st.rerun()


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

        # Auto-include relacionados: any selected produto with related IDs in
        # Produtos.Relacionados gets its trio added (default qty 1).
        auto_added = []
        if not produtos.empty:
            for pid in list(pkg_quantities.keys()):
                prod_row = produtos[produtos["id"] == pid]
                if prod_row.empty:
                    continue
                rels = prod_row.iloc[0].get("relacionados") or []
                if not isinstance(rels, list):
                    rels = []
                for rel_id in rels:
                    if rel_id not in pkg_quantities:
                        pkg_quantities[rel_id] = 1.0
                        selected_pkgs = list(selected_pkgs) + [rel_id]
                        auto_added.append(rel_id)

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
            if auto_added:
                st.info(f"💡 Auto-incluí também: {', '.join(auto_added)} (relacionados aos que você selecionou).")
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
