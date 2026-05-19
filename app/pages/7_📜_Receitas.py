"""Receitas page: cadastro e edição das receitas do pudim.

Each receita = a list of ingredientes split between two componentes
("calda" and "massa"). One receita is marked `padrao=TRUE` and is the
fallback for tamanhos that haven't picked a specific recipe.

The page guards against running before the migration: if the Receitas tab
does not exist, it shows a warning and stops.

Editing model (post-refactor):
- Each component renders as an inline `st.data_editor` so Qtde / Unidade /
  Remover can be edited directly in the visible table.
- A `st.popover("⚙️ Configurar")` next to the title holds nome + padrao.
- Delete is an expander at the bottom (rare destructive action).
- A single `💾 Salvar alterações` button per receita commits all changes.
"""

import os
import sys

import streamlit as st
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.auth import require_auth
from lib import data
from lib.ui import setup_page, brl, compact_kpi, card_title, qty_input_params


COMPONENTES = ["calda", "massa"]
COMPONENTE_LABEL = {"calda": "🍯 Calda", "massa": "🥚 Massa"}

# Unit options shown in the Unidade column. Matches what Insumos uses; the
# data_editor's selectbox auto-extends with any non-standard current value
# (computed per-receita below) so legacy units aren't lost.
UNIDADE_OPTIONS = ["UN", "KG", "L", "M", "DZ", "PENTE", "G", "ML"]


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


def _build_component_df(
    sub: pd.DataFrame,
    compras_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Build the DataFrame shown by `st.data_editor` for one component.

    Columns: ID, Nome, Qtde, Unidade, Custo, Remover.
    `Custo` is recomputed from qtde × latest_unit_price, so it stays
    accurate even when the user changes Qtde inline (after rerun).
    """
    if sub.empty:
        return pd.DataFrame(
            columns=["ID", "Nome", "Qtde", "Unidade", "Custo", "Remover"],
        )
    rows = []
    for _, r in sub.iterrows():
        pid = r["produto_id"]
        qtde = float(r["qtde"]) if pd.notna(r.get("qtde")) else 0.0
        preco = data.latest_unit_price(pid, compras_df)
        rows.append({
            "ID": pid,
            "Nome": r.get("produto_nome") or r.get("nome") or pid,
            "Qtde": qtde,
            "Unidade": (r.get("unidade") or "").strip().upper(),
            "Custo": qtde * preco,
            "Remover": False,
        })
    return pd.DataFrame(rows)


def _unit_options_for(df: pd.DataFrame) -> list[str]:
    """
    Standard UNIDADE_OPTIONS extended with any non-standard unit already
    present in `df["Unidade"]` (so legacy values aren't silently dropped).
    """
    extras: list[str] = []
    if not df.empty and "Unidade" in df.columns:
        for u in df["Unidade"].dropna().astype(str).str.strip().str.upper().unique():
            if u and u not in UNIDADE_OPTIONS and u not in extras:
                extras.append(u)
    return UNIDADE_OPTIONS + extras


def _column_config(unit_options: list[str]) -> dict:
    """Column config shared by both component data_editors."""
    return {
        "ID": st.column_config.TextColumn("ID", disabled=True, width="small"),
        "Nome": st.column_config.TextColumn("Nome", disabled=True),
        "Qtde": st.column_config.NumberColumn(
            "Qtde",
            min_value=0.0,
            step=0.05,
            format="%.3g",
            required=True,
        ),
        "Unidade": st.column_config.SelectboxColumn(
            "Unidade",
            options=unit_options,
            required=True,
        ),
        "Custo": st.column_config.TextColumn(
            "Custo",
            disabled=True,
            help="Qtde × preço unitário mais recente. Atualiza ao salvar.",
        ),
        "Remover": st.column_config.CheckboxColumn(
            "Remover",
            help="Marque pra remover esse ingrediente ao salvar.",
            default=False,
        ),
    }


def _format_custo_column(df: pd.DataFrame) -> pd.DataFrame:
    """Render the Custo column as BRL strings for display only."""
    out = df.copy()
    if "Custo" in out.columns:
        out["Custo"] = out["Custo"].apply(brl)
    return out


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

        # ALI produtos pool (used by the "Adicionar ingrediente" selectbox).
        ali_options = (
            produtos_df[produtos_df["categoria"] == "ALI"].sort_values("nome")
            if not produtos_df.empty else pd.DataFrame()
        )

        for _, receita in receitas.iterrows():
            receita_id = str(receita["receita_id"])
            is_padrao = bool(receita["padrao"])

            with st.container(border=True):
                # ---- Title row with inline name + padrão toggle (no popover) ----
                nome_key = f"cfg_nome_{receita_id}"
                padrao_key = f"cfg_padrao_{receita_id}"
                if nome_key not in st.session_state:
                    st.session_state[nome_key] = receita["nome"] or ""
                if padrao_key not in st.session_state:
                    st.session_state[padrao_key] = is_padrao

                badge_col, name_col, padrao_col = st.columns([1, 4, 2])
                with badge_col:
                    st.markdown(
                        f'<div style="padding-top: 0.5rem;"><code>{receita_id}</code></div>',
                        unsafe_allow_html=True,
                    )
                with name_col:
                    st.text_input(
                        "Nome",
                        key=nome_key,
                        label_visibility="collapsed",
                        placeholder="Nome da receita",
                    )
                with padrao_col:
                    st.markdown(
                        '<div style="height: 0.45rem;"></div>',
                        unsafe_allow_html=True,
                    )
                    st.checkbox(
                        "Receita padrão",
                        key=padrao_key,
                        help=(
                            "Tamanhos sem receita explícita usam a padrão. "
                            "Marcar essa desmarca as outras."
                        ),
                    )

                # ---- Pre-compute ingredients (with cost columns) ----
                ing = all_ing[all_ing["receita_id"] == receita_id].copy()
                if not ing.empty:
                    ing["preco_unit_atual"] = ing["produto_id"].apply(
                        lambda p: data.latest_unit_price(p, compras_df)
                    )
                    ing["custo"] = ing["qtde"] * ing["preco_unit_atual"]
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

                # Toggle: view (st.table brand-styled) vs edit (data_editor).
                rec_edit_key = f"rec_edit_mode_{receita_id}"
                if rec_edit_key not in st.session_state:
                    st.session_state[rec_edit_key] = False
                rec_edit_active = st.session_state[rec_edit_key]

                # ---- Two columns side by side (Calda | Massa) ----
                col_calda, col_massa = st.columns([1, 1])
                edited_by_comp: dict[str, pd.DataFrame] = {}

                for comp, col in (("calda", col_calda), ("massa", col_massa)):
                    with col:
                        st.markdown(f"**{COMPONENTE_LABEL[comp]}**")

                        sub = ing[ing["componente"] == comp]
                        comp_df = _build_component_df(sub, compras_df)

                        # Merge any pending-add rows (staged on previous reruns)
                        # BEFORE computing the pool — otherwise just-added
                        # ingredients would still show up as selectable.
                        pending_key = f"pending_add_{receita_id}_{comp}"
                        pending_rows = st.session_state.get(pending_key, [])
                        if pending_rows:
                            comp_df = pd.concat(
                                [comp_df, pd.DataFrame(pending_rows)],
                                ignore_index=True,
                            )

                        if not rec_edit_active:
                            # --- VIEW MODE (st.table brand-styled) ---
                            if comp_df.empty:
                                st.caption("_Sem ingredientes nesse componente._")
                            else:
                                disp = comp_df[["ID", "Nome", "Qtde", "Unidade", "Custo"]].copy()
                                disp["Qtde"] = disp["Qtde"].apply(
                                    lambda v: f"{v:.3g}".replace(".", ",")
                                )
                                disp["Custo"] = disp["Custo"].apply(brl)
                                st.table(disp.set_index("ID"))
                            compact_kpi(f"Custo {comp}", brl(float(comp_df["Custo"].sum()) if not comp_df.empty else 0))
                            edited_by_comp[comp] = comp_df
                        else:
                            # --- EDIT MODE (data_editor + Adicionar ingrediente) ---
                            already_in = set(comp_df["ID"].tolist()) if not comp_df.empty else set()
                            if not ali_options.empty:
                                pool = ali_options[~ali_options["id"].isin(already_in)].copy()
                            else:
                                pool = pd.DataFrame()
                            if not pool.empty:
                                pool["label"] = pool["id"] + " — " + pool["nome"]
                                add_col_sel, add_col_btn = st.columns([3, 1])
                                with add_col_sel:
                                    sel_key = f"add_sel_{receita_id}_{comp}"
                                    st.selectbox(
                                        f"Adicionar ingrediente à {comp}",
                                        options=[""] + pool["id"].tolist(),
                                        format_func=lambda x: (
                                            pool[pool["id"] == x]["label"].iloc[0]
                                            if x else "— escolha um ingrediente —"
                                        ),
                                        key=sel_key,
                                        label_visibility="collapsed",
                                    )
                                with add_col_btn:
                                    if st.button(
                                        "➕ Adicionar",
                                        key=f"add_btn_{receita_id}_{comp}",
                                        use_container_width=True,
                                    ):
                                        pid = st.session_state.get(sel_key, "")
                                        if pid:
                                            prod_row = produtos_df[produtos_df["id"] == pid].iloc[0]
                                            default_unit = (
                                                (prod_row.get("unidade") or "").strip().upper() or "G"
                                            )
                                            pending = st.session_state.setdefault(pending_key, [])
                                            if not any(p["ID"] == pid for p in pending):
                                                pending.append({
                                                    "ID": pid,
                                                    "Nome": prod_row.get("nome") or pid,
                                                    "Qtde": 1.0,
                                                    "Unidade": default_unit,
                                                    "Custo": 1.0 * data.latest_unit_price(pid, compras_df),
                                                    "Remover": False,
                                                })
                                            st.session_state[sel_key] = ""
                                            st.rerun()

                            editor_key = f"editor_{receita_id}_{comp}"

                            if comp_df.empty:
                                st.caption("_Sem ingredientes nesse componente._")
                                compact_kpi(f"Custo {comp}", brl(0))
                                edited_by_comp[comp] = comp_df
                            else:
                                display_df = _format_custo_column(comp_df)
                                unit_opts = _unit_options_for(comp_df)
                                edited_display = st.data_editor(
                                    display_df,
                                    column_config=_column_config(unit_opts),
                                    hide_index=True,
                                    use_container_width=True,
                                    num_rows="fixed",
                                    key=editor_key,
                                )
                                edited_numeric = edited_display.copy()
                                edited_numeric["Custo"] = comp_df.set_index("ID")["Custo"].reindex(
                                    edited_numeric["ID"]
                                ).values
                                edited_by_comp[comp] = edited_numeric
                                compact_kpi(
                                    f"Custo {comp}",
                                    brl(float(comp_df["Custo"].sum())),
                                )

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

                # --- Critical-change gate: switching the padrão affects every
                # tamanho that doesn't have an explicit receita_id ---
                staged_padrao = bool(
                    st.session_state.get(f"cfg_padrao_{receita_id}", is_padrao)
                )
                becoming_padrao = staged_padrao and not is_padrao
                save_disabled = False
                if becoming_padrao:
                    with st.container(border=True):
                        st.markdown(
                            f"**⚠️ Marcar como padrão**: "
                            f"Todos os tamanhos que não têm receita específica "
                            f"vão passar a usar **{(st.session_state.get(f'cfg_nome_{receita_id}') or receita['nome'])}** no cálculo de custo."
                        )
                        confirm_padrao = st.checkbox(
                            "Confirmo trocar a receita padrão",
                            key=f"confirm_padrao_{receita_id}",
                        )
                    save_disabled = not confirm_padrao

                # --- Edit toggle ------------------------------------------------
                if not rec_edit_active:
                    if st.button(
                        "✏️ Editar receita",
                        key=f"rec_edit_btn_{receita_id}",
                        use_container_width=True,
                    ):
                        st.session_state[rec_edit_key] = True
                        st.rerun()
                    # In view mode there's nothing to save, so we skip the rest.
                    continue

                cancel_col, _ = st.columns([1, 3])
                with cancel_col:
                    if st.button(
                        "✖ Cancelar edição",
                        key=f"rec_cancel_btn_{receita_id}",
                    ):
                        st.session_state[rec_edit_key] = False
                        # Drop any unsaved staged ingredient additions for this receita.
                        for c in COMPONENTES:
                            st.session_state.pop(f"pending_add_{receita_id}_{c}", None)
                        st.rerun()

                # --- Save button -----------------------------------------------
                if st.button(
                    "💾 Salvar alterações",
                    key=f"save_{receita_id}",
                    use_container_width=True,
                    type="primary",
                    disabled=save_disabled,
                ):
                    try:
                        service = data.get_service()
                        ssid = data._spreadsheet_id()

                        # 1. Read staged config (nome + padrao) from the popover.
                        new_nome = (
                            st.session_state.get(f"cfg_nome_{receita_id}", receita["nome"] or "")
                            or ""
                        ).strip()
                        new_padrao = bool(
                            st.session_state.get(f"cfg_padrao_{receita_id}", is_padrao)
                        )
                        if not new_nome:
                            st.error("Dá um nome pra receita.")
                            st.stop()
                        if is_padrao and not new_padrao:
                            st.error(
                                "Não dá pra desmarcar a padrão sem marcar outra. "
                                "Abre outra receita e marca-a como padrão primeiro."
                            )
                            st.stop()

                        # 2. Apply nome + padrao to the Receitas row.
                        rn = _find_receita_row_num(receita_id)
                        service.spreadsheets().values().update(
                            spreadsheetId=ssid,
                            range=f"Receitas!B{rn}:C{rn}",
                            valueInputOption="USER_ENTERED",
                            body={"values": [[new_nome, bool(new_padrao)]]},
                        ).execute()
                        if new_padrao:
                            _ensure_single_padrao(service, ssid, receita_id)

                        # 3. Build the new ingredient list from each
                        # data_editor's returned (edited) DataFrame. Rows with
                        # Remover=True or Qtde<=0 are dropped on save.
                        new_ing_rows: list[list] = []
                        for comp in COMPONENTES:
                            edited = edited_by_comp.get(comp, pd.DataFrame())
                            if edited.empty:
                                continue
                            for _, r in edited.iterrows():
                                if bool(r.get("Remover")):
                                    continue
                                try:
                                    qtde = float(r.get("Qtde") or 0)
                                except (TypeError, ValueError):
                                    qtde = 0.0
                                if qtde <= 0:
                                    continue
                                pid = r["ID"]
                                unidade = (str(r.get("Unidade") or "").strip().upper())
                                # Prefer produto's canonical name.
                                nome_prod = r.get("Nome") or ""
                                if not produtos_df.empty:
                                    pr = produtos_df[produtos_df["id"] == pid]
                                    if not pr.empty:
                                        nome_prod = pr.iloc[0]["nome"] or nome_prod
                                new_ing_rows.append(
                                    [receita_id, pid, nome_prod, qtde, unidade, comp]
                                )

                        # 4. Rewrite Receita_Ingredientes: keep other receitas,
                        # replace this one's block.
                        ing_all = service.spreadsheets().values().get(
                            spreadsheetId=ssid, range="Receita_Ingredientes!A2:F",
                            valueRenderOption="UNFORMATTED_VALUE",
                        ).execute().get("values", [])
                        kept = [r for r in ing_all if r and (r + [""])[0] != receita_id]
                        kept.extend(new_ing_rows)
                        _rewrite_receita_ingredientes(service, ssid, kept)

                        # 5. Clear pending-add staging for this receita.
                        for comp in COMPONENTES:
                            st.session_state.pop(f"pending_add_{receita_id}_{comp}", None)

                        data.invalidate_cache()
                        # Reset edit mode + clear staged adds for this receita.
                        st.session_state[rec_edit_key] = False
                        for c in COMPONENTES:
                            st.session_state.pop(f"pending_add_{receita_id}_{c}", None)
                        st.success(f"✅ {receita_id} atualizado!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erro: {e}")
                        import traceback
                        st.code(traceback.format_exc())

                # --- Delete (tucked away at the bottom) ------------------------
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
