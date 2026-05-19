"""Receitas page: cadastro e edição das receitas do pudim.

Each receita = a list of ingredientes split between two componentes
("calda" and "massa"). One receita is marked `padrao=TRUE` and is the
fallback for tamanhos that haven't picked a specific recipe.

The page guards against running before the migration: if the Receitas tab
does not exist, it shows a warning and stops.
"""

import os
import sys

import streamlit as st
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.auth import require_auth
from lib import data
from lib.ui import setup_page, brl, compact_kpi, card_title, qty_fmt, qty_input_params


COMPONENTES = ["calda", "massa"]
COMPONENTE_LABEL = {"calda": "🍯 Calda", "massa": "🥚 Massa"}

# Unit options for the ingredient editor — matches what Insumos uses.
UNIDADE_OPTIONS = ["KG", "G", "L", "ML", "UN", "DZ", "PENTE", "PAR", "JOGO", "M", "CM"]


setup_page("Receitas", icon="📜")
require_auth()

st.title("📜 Receitas")
st.caption(
    "Receitas cadastradas. A marcada como padrão é usada por tamanhos "
    "que não escolheram uma específica."
)


# ---------------------------------------------------------------------------
# Pre-migration guard
# ---------------------------------------------------------------------------
if not data._has_sheet("Receitas"):
    st.warning(
        "⚠️ Schema novo ainda não foi migrado. "
        "Rode `python scripts/migrate_receitas.py --apply` no terminal local."
    )
    st.stop()


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _find_receita_row_num(receita_id: str) -> int:
    """Return the 1-indexed Receitas sheet row for `receita_id`."""
    return data.find_row_by_id("Receitas", receita_id)


def _rewrite_receita_ingredientes(service, ssid: str, kept_rows: list[list]) -> None:
    """Clear Receita_Ingredientes!A2:F and rewrite with the given rows.

    Each row is expected to be [receita_id, produto_id, nome, qtde, unidade, componente].
    """
    service.spreadsheets().values().clear(
        spreadsheetId=ssid, range="Receita_Ingredientes!A2:F",
    ).execute()
    if kept_rows:
        service.spreadsheets().values().update(
            spreadsheetId=ssid,
            range="Receita_Ingredientes!A2",
            valueInputOption="USER_ENTERED",
            body={"values": kept_rows},
        ).execute()


def _ensure_single_padrao(service, ssid: str, padrao_receita_id: str) -> None:
    """
    Untick `padrao` for every other receita and tick it on the named one.

    Called when the user saves an edit with padrao=True (or a new receita
    with padrao=True) — exactly one row should remain marked.
    """
    receitas_rows = service.spreadsheets().values().get(
        spreadsheetId=ssid, range="Receitas!A2:D",
        valueRenderOption="UNFORMATTED_VALUE",
    ).execute().get("values", [])
    for i, r in enumerate(receitas_rows):
        if not r or not r[0]:
            continue
        sheet_row = i + 2  # 1-indexed + header
        new_padrao = (r[0] == padrao_receita_id)
        service.spreadsheets().values().update(
            spreadsheetId=ssid,
            range=f"Receitas!C{sheet_row}",
            valueInputOption="USER_ENTERED",
            body={"values": [[new_padrao]]},
        ).execute()


# ---------------------------------------------------------------------------
# Edit form (defined up-front so the list loop below can call it)
# ---------------------------------------------------------------------------
def _render_edit_form(
    receita_id: str,
    receita: pd.Series,
    ing: pd.DataFrame,
    produtos_df: pd.DataFrame,
    is_padrao: bool,
) -> None:
    """Render the edit form for a single receita.

    The form lets the user rename the receita, toggle padrao, adjust each
    ingredient (qtde + unidade), remove ingredientes, and add new ones per
    componente.
    """
    with st.form(f"edit_receita_{receita_id}"):
        new_nome = st.text_input("Nome", value=receita["nome"] or "")
        new_padrao = st.checkbox(
            "Marcar como padrão",
            value=is_padrao,
            help="Tamanhos sem receita explícita usam a padrão. Marcar essa desmarca as outras.",
        )

        # Track edits keyed by (componente, produto_id).
        edited_qtys: dict[tuple[str, str], float] = {}
        edited_units: dict[tuple[str, str], str] = {}
        new_ingredientes: list[tuple[str, str, float, str]] = []  # (componente, produto_id, qtde, unidade)

        # Build a sorted list of ALI produtos for the "add" dropdowns.
        ali_options = (
            produtos_df[produtos_df["categoria"] == "ALI"].sort_values("nome")
            if not produtos_df.empty else pd.DataFrame()
        )

        for comp in COMPONENTES:
            st.markdown(f"#### {COMPONENTE_LABEL[comp]}")
            sub = ing[ing["componente"] == comp]

            # --- Add new ingredient row(s) for this componente ---
            already_in = set(sub["produto_id"].tolist()) if not sub.empty else set()
            add_pool = ali_options[~ali_options["id"].isin(already_in)] if not ali_options.empty else pd.DataFrame()
            if not add_pool.empty:
                add_pool = add_pool.copy()
                add_pool["label"] = add_pool["id"] + " — " + add_pool["nome"]
                added = st.multiselect(
                    f"Adicionar ingrediente à {comp}",
                    options=add_pool["id"].tolist(),
                    format_func=lambda x: add_pool[add_pool["id"] == x]["label"].iloc[0],
                    key=f"add_ing_{receita_id}_{comp}",
                )
                for pid in added:
                    prod_row = produtos_df[produtos_df["id"] == pid].iloc[0]
                    default_unit = (prod_row.get("unidade") or "").strip().upper() or "G"
                    if default_unit not in UNIDADE_OPTIONS:
                        unit_options = UNIDADE_OPTIONS + [default_unit]
                    else:
                        unit_options = UNIDADE_OPTIONS
                    min_v, step_v, fmt_v, is_int = qty_input_params(pid, produtos_df)
                    qcol, ucol = st.columns([2, 1])
                    with qcol:
                        qty = st.number_input(
                            f"{pid} — {prod_row['nome']} (qtde)",
                            min_value=min_v,
                            value=(1 if is_int else 1.0),
                            step=step_v, format=fmt_v,
                            key=f"new_ing_qty_{receita_id}_{comp}_{pid}",
                        )
                    with ucol:
                        unit = st.selectbox(
                            "Unidade",
                            unit_options,
                            index=unit_options.index(default_unit),
                            key=f"new_ing_unit_{receita_id}_{comp}_{pid}",
                        )
                    new_ingredientes.append((comp, pid, float(qty), unit))

            # --- Existing rows ---
            if sub.empty:
                st.caption("_Nenhum ingrediente._")
            else:
                for _, ing_row in sub.iterrows():
                    pid = ing_row["produto_id"]
                    min_v, step_v, fmt_v, is_int = qty_input_params(pid, produtos_df)
                    raw_val = ing_row.get("qtde")
                    if pd.notna(raw_val):
                        val_v = int(round(float(raw_val))) if is_int else float(raw_val)
                    else:
                        val_v = 1 if is_int else 1.0
                    current_unit = (ing_row.get("unidade") or "").strip().upper() or "G"
                    if current_unit not in UNIDADE_OPTIONS:
                        unit_options = UNIDADE_OPTIONS + [current_unit]
                    else:
                        unit_options = UNIDADE_OPTIONS

                    qcol, ucol, rcol = st.columns([3, 1, 1])
                    with qcol:
                        nome_disp = ing_row.get("produto_nome") or ing_row.get("nome") or pid
                        qty = st.number_input(
                            f"{pid} — {nome_disp}",
                            min_value=min_v,
                            value=val_v,
                            step=step_v, format=fmt_v,
                            key=f"edit_qty_{receita_id}_{comp}_{pid}",
                        )
                    with ucol:
                        unit = st.selectbox(
                            "Unidade",
                            unit_options,
                            index=unit_options.index(current_unit),
                            key=f"edit_unit_{receita_id}_{comp}_{pid}",
                            label_visibility="collapsed",
                        )
                    with rcol:
                        st.markdown('<div style="height: 1.8rem;"></div>', unsafe_allow_html=True)
                        remove = st.checkbox(
                            "🗑️",
                            key=f"rm_{receita_id}_{comp}_{pid}",
                            help="Remover esse ingrediente",
                        )
                    edited_qtys[(comp, pid)] = 0 if remove else float(qty)
                    edited_units[(comp, pid)] = unit

        if st.form_submit_button("💾 Salvar alterações", use_container_width=True, type="primary"):
            try:
                service = data.get_service()
                ssid = data._spreadsheet_id()

                # 1. Update Receitas (nome + padrao). Notas left as-is.
                if not new_nome.strip():
                    st.error("Dá um nome pra receita.")
                    st.stop()
                if is_padrao and not new_padrao:
                    st.error(
                        "Não dá pra desmarcar a padrão sem marcar outra. "
                        "Abre outra receita e marca-a como padrão primeiro."
                    )
                    st.stop()

                rn = _find_receita_row_num(receita_id)
                service.spreadsheets().values().update(
                    spreadsheetId=ssid,
                    range=f"Receitas!B{rn}:C{rn}",
                    valueInputOption="USER_ENTERED",
                    body={"values": [[new_nome.strip(), bool(new_padrao)]]},
                ).execute()
                if new_padrao:
                    _ensure_single_padrao(service, ssid, receita_id)

                # 2. Rewrite Receita_Ingredientes. The cleanest approach is:
                #    - read all rows
                #    - drop everything matching this receita_id
                #    - append the new computed set
                #    - clear + rewrite the whole block
                ing_all = service.spreadsheets().values().get(
                    spreadsheetId=ssid, range="Receita_Ingredientes!A2:F",
                    valueRenderOption="UNFORMATTED_VALUE",
                ).execute().get("values", [])
                kept = [r for r in ing_all if r and (r + [""])[0] != receita_id]

                # Add edited existing rows (skip removed = qty 0).
                for (comp, pid), q in edited_qtys.items():
                    if q <= 0:
                        continue
                    unidade = edited_units.get((comp, pid), "")
                    nome_prod = ""
                    if not produtos_df.empty:
                        pr = produtos_df[produtos_df["id"] == pid]
                        if not pr.empty:
                            nome_prod = pr.iloc[0]["nome"] or ""
                    kept.append([receita_id, pid, nome_prod, q, unidade, comp])

                # Add brand-new rows.
                for comp, pid, q, unidade in new_ingredientes:
                    if q <= 0:
                        continue
                    nome_prod = ""
                    if not produtos_df.empty:
                        pr = produtos_df[produtos_df["id"] == pid]
                        if not pr.empty:
                            nome_prod = pr.iloc[0]["nome"] or ""
                    kept.append([receita_id, pid, nome_prod, q, unidade, comp])

                _rewrite_receita_ingredientes(service, ssid, kept)

                data.invalidate_cache()
                st.success(f"✅ {receita_id} atualizado!")
                st.rerun()
            except Exception as e:
                st.error(f"Erro: {e}")
                import traceback
                st.code(traceback.format_exc())


# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------
tab_list, tab_new = st.tabs(["📋 Receitas cadastradas", "➕ Nova receita"])


# ============================================================================
# List
# ============================================================================
with tab_list:
    if st.button("🔄 Atualizar", help="Buscar dados mais recentes da planilha"):
        data.invalidate_cache()
        st.rerun()

    receitas = data.get_receitas()
    produtos_df = data.get_produtos()
    compras_df = data.get_compras()

    if receitas.empty:
        st.info("Nenhuma receita cadastrada ainda. Use a aba ➕ Nova receita.")
    else:
        # Pre-fetch all ingredients once so we don't hit the API per receita.
        all_ing = data.get_receita_ingredientes()

        for _, receita in receitas.iterrows():
            receita_id = str(receita["receita_id"])
            is_padrao = bool(receita["padrao"])

            with st.container(border=True):
                meta_text = "padrão" if is_padrao else ""
                card_title(
                    receita["nome"] or "(sem nome)",
                    badge=receita_id,
                    meta=meta_text,
                    meta_below=True,
                )

                # --- Ingredients by componente ---------------------------------
                ing = all_ing[all_ing["receita_id"] == receita_id].copy()
                if not ing.empty:
                    # Add live cost columns for display.
                    ing["preco_unit_atual"] = ing["produto_id"].apply(
                        lambda p: data.latest_unit_price(p, compras_df)
                    )
                    ing["custo"] = ing["qtde"] * ing["preco_unit_atual"]
                    # Prefer the produto's canonical name if available.
                    if not produtos_df.empty:
                        ing = ing.merge(
                            produtos_df[["id", "nome"]].rename(
                                columns={"id": "produto_id", "nome": "_produto_nome"}
                            ),
                            on="produto_id", how="left",
                        )
                        ing["produto_nome"] = ing["_produto_nome"].fillna(ing["nome"])
                    else:
                        ing["produto_nome"] = ing["nome"]

                col_calda, col_massa = st.columns([1, 1])
                for comp, col in (("calda", col_calda), ("massa", col_massa)):
                    with col:
                        st.markdown(f"**{COMPONENTE_LABEL[comp]}**")
                        sub = ing[ing["componente"] == comp]
                        if sub.empty:
                            st.caption("_Sem ingredientes nesse componente._")
                            compact_kpi(f"Custo {comp}", brl(0))
                            continue
                        disp = sub[["produto_id", "produto_nome", "qtde", "unidade", "custo"]].copy()
                        disp["qtde"] = disp["qtde"].apply(qty_fmt)
                        disp["custo"] = disp["custo"].apply(brl)
                        disp.columns = ["Produto", "Nome", "Qtde", "Unidade", "Custo"]
                        st.table(disp.set_index("Produto"))
                        compact_kpi(f"Custo {comp}", brl(sub["custo"].sum()))

                # Ingredients with no componente (shouldn't normally happen,
                # but the migration shim leaves them empty pre-apply).
                sem_comp = ing[~ing["componente"].isin(COMPONENTES)] if not ing.empty else pd.DataFrame()
                if not sem_comp.empty:
                    st.caption(
                        f"_{len(sem_comp)} ingrediente(s) sem componente atribuído — "
                        "edita a receita pra classificar como calda ou massa._"
                    )

                # --- Total da receita ------------------------------------------
                custo_total = float(ing["custo"].sum()) if not ing.empty else 0.0
                st.markdown('<div style="height: 0.4rem;"></div>', unsafe_allow_html=True)
                compact_kpi("Custo total da receita", brl(custo_total))

                # --- Edit ------------------------------------------------------
                with st.expander("✏️ Editar receita"):
                    _render_edit_form(receita_id, receita, ing, produtos_df, is_padrao)

                # --- Delete ----------------------------------------------------
                with st.expander("🗑️ Deletar receita"):
                    if is_padrao:
                        st.warning(
                            "⚠️ Essa é a receita padrão. Marca outra como padrão "
                            "antes de deletar essa."
                        )
                    else:
                        confirm_key = f"confirm_del_rec_{receita_id}"
                        if st.session_state.get(confirm_key):
                            st.error(
                                f"Confirma deletar **{receita_id} — {receita['nome']}**? "
                                "Todos os ingredientes vinculados também serão removidos. "
                                "Esta ação é irreversível."
                            )
                            cdc1, cdc2 = st.columns(2)
                            with cdc1:
                                if st.button(
                                    "✅ Sim, deletar",
                                    key=f"do_del_rec_{receita_id}",
                                    type="primary",
                                ):
                                    try:
                                        service = data.get_service()
                                        ssid = data._spreadsheet_id()
                                        # 1. Drop Receitas row
                                        rn = _find_receita_row_num(receita_id)
                                        data.delete_row("Receitas", rn)
                                        # 2. Drop all matching ingredient rows
                                        ing_all = service.spreadsheets().values().get(
                                            spreadsheetId=ssid,
                                            range="Receita_Ingredientes!A2:F",
                                            valueRenderOption="UNFORMATTED_VALUE",
                                        ).execute().get("values", [])
                                        kept = [
                                            r for r in ing_all
                                            if r and (r + [""])[0] != receita_id
                                        ]
                                        _rewrite_receita_ingredientes(service, ssid, kept)
                                        data.invalidate_cache()
                                        del st.session_state[confirm_key]
                                        st.success(f"✅ {receita_id} removido.")
                                        st.rerun()
                                    except Exception as e:
                                        st.error(f"Erro: {e}")
                            with cdc2:
                                if st.button("❌ Cancelar", key=f"cancel_del_rec_{receita_id}"):
                                    del st.session_state[confirm_key]
                                    st.rerun()
                        else:
                            if st.button(
                                f"🗑️ Deletar {receita_id}",
                                key=f"req_del_rec_{receita_id}",
                            ):
                                st.session_state[confirm_key] = True
                                st.rerun()


# ============================================================================
# Nova receita
# ============================================================================
with tab_new:
    st.markdown("### Cadastrar uma nova receita")
    st.caption(
        "Defina o nome e adicione os ingredientes em cada componente. "
        "Marcar como padrão desmarca a receita padrão atual."
    )

    produtos_df = data.get_produtos()
    receitas_atuais = data.get_receitas()

    ali_options = (
        produtos_df[produtos_df["categoria"] == "ALI"].sort_values("nome")
        if not produtos_df.empty else pd.DataFrame()
    )

    with st.form("new_receita", clear_on_submit=False):
        n_nome = st.text_input("Nome", placeholder="ex: Doce de leite")
        n_padrao = st.checkbox(
            "Marcar como padrão",
            value=receitas_atuais.empty,  # default ON only if no receitas exist
            help="Se ligado, vira a padrão e desmarca a atual.",
        )
        n_notas = st.text_input("Observações (opcional)", placeholder="ex: receita do verão")

        new_ingredientes: list[tuple[str, str, float, str]] = []
        for comp in COMPONENTES:
            st.markdown(f"#### {COMPONENTE_LABEL[comp]}")
            if ali_options.empty:
                st.caption("_Cadastre insumos primeiro._")
                continue
            pool = ali_options.copy()
            pool["label"] = pool["id"] + " — " + pool["nome"]
            picked = st.multiselect(
                f"Ingredientes da {comp}",
                options=pool["id"].tolist(),
                format_func=lambda x: pool[pool["id"] == x]["label"].iloc[0],
                key=f"new_pick_{comp}",
            )
            for pid in picked:
                prod_row = produtos_df[produtos_df["id"] == pid].iloc[0]
                default_unit = (prod_row.get("unidade") or "").strip().upper() or "G"
                if default_unit not in UNIDADE_OPTIONS:
                    unit_options = UNIDADE_OPTIONS + [default_unit]
                else:
                    unit_options = UNIDADE_OPTIONS
                min_v, step_v, fmt_v, is_int = qty_input_params(pid, produtos_df)
                qcol, ucol = st.columns([2, 1])
                with qcol:
                    qty = st.number_input(
                        f"{pid} — {prod_row['nome']} (qtde)",
                        min_value=min_v,
                        value=(1 if is_int else 1.0),
                        step=step_v, format=fmt_v,
                        key=f"new_rec_qty_{comp}_{pid}",
                    )
                with ucol:
                    unit = st.selectbox(
                        "Unidade",
                        unit_options,
                        index=unit_options.index(default_unit),
                        key=f"new_rec_unit_{comp}_{pid}",
                    )
                new_ingredientes.append((comp, pid, float(qty), unit))

        if st.form_submit_button("➕ Criar receita", use_container_width=True, type="primary"):
            if not n_nome.strip():
                st.error("Dá um nome pra receita.")
                st.stop()
            try:
                service = data.get_service()
                ssid = data._spreadsheet_id()

                # 1. Pick the next REC-NNN id.
                new_id = data._sheets._next_id_for_prefix(
                    ssid, "Receitas!A:A", "REC", service=service,
                )

                # 2. Append a row to Receitas.
                existing = service.spreadsheets().values().get(
                    spreadsheetId=ssid, range="Receitas!A:A",
                ).execute().get("values", [])
                next_row = len(existing) + 1
                service.spreadsheets().values().update(
                    spreadsheetId=ssid,
                    range=f"Receitas!A{next_row}",
                    valueInputOption="USER_ENTERED",
                    body={"values": [[new_id, n_nome.strip(), bool(n_padrao), n_notas.strip()]]},
                ).execute()
                if n_padrao:
                    _ensure_single_padrao(service, ssid, new_id)

                # 3. Append ingredient rows.
                if new_ingredientes:
                    ing_existing = service.spreadsheets().values().get(
                        spreadsheetId=ssid, range="Receita_Ingredientes!A:A",
                    ).execute().get("values", [])
                    ing_next = len(ing_existing) + 1
                    rows_to_write = []
                    for comp, pid, q, unidade in new_ingredientes:
                        if q <= 0:
                            continue
                        nome_prod = ""
                        if not produtos_df.empty:
                            pr = produtos_df[produtos_df["id"] == pid]
                            if not pr.empty:
                                nome_prod = pr.iloc[0]["nome"] or ""
                        rows_to_write.append([new_id, pid, nome_prod, q, unidade, comp])
                    if rows_to_write:
                        service.spreadsheets().values().update(
                            spreadsheetId=ssid,
                            range=f"Receita_Ingredientes!A{ing_next}",
                            valueInputOption="USER_ENTERED",
                            body={"values": rows_to_write},
                        ).execute()

                data.invalidate_cache()
                st.success(f"✅ Receita criada: **{new_id} — {n_nome}**")
                st.balloons()
            except Exception as e:
                st.error(f"Erro criando: {e}")
                import traceback
                st.code(traceback.format_exc())
