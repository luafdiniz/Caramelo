"""Insumos page: list, filter, drill into price history, edit/delete, create new.

In the spreadsheet this tab is called 'Produtos' (legacy), but the UI says
'Insumos' to match the business vocabulary — these are raw materials, not the
final sold products (which are Tamanhos).

The list view is split into per-categoria sub-tabs (Alimentos / Formas /
Embalagens / Equipamentos / Operacionais). Each tab renders its own editable
spreadsheet (st.data_editor). Every cell the user is allowed to change is
editable inline — no pencil buttons, no per-row expanders.

Key editor behaviors:
- The category emoji lives in its own narrow column (no longer mashed into the
  Insumo name cell — Luiza found that ugly).
- "Preço atual" is itself editable: typing a new value creates a Compra of
  manual adjustment when the user clicks "Salvar" (fornecedor = the produto's
  most-recent fornecedor, notas = "Ajuste manual de preço"). There is no
  separate "Novo preço" column.
- "Categoria" is intentionally disabled. Changing categoria changes the ID
  prefix and requires migrating references in Compras / Tamanhos / Receitas
  — that lives in scripts/migrate_categoria.py.

For one-off deletions the user can use the inline "Excluir agora" mini-form
below the table (it wipes the produto immediately without going through
Salvar). The Excluir checkbox column still exists for bulk deletes via
Salvar — both paths work.

A "Mais detalhes" panel below the grids drills into ONE selected insumo
(across all categories) showing price history / per-fornecedor analysis /
outliers.
"""

import os
import sys
from datetime import date
import streamlit as st
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.auth import require_auth
from lib import data
from lib.ui import (
    setup_page,
    brl,
    brl_md,
    compact_kpi,
    CARAMEL_LIGHT,
    CREAM,
    PURPLE_DARK,
    BEIGE,
)


setup_page("Insumos", icon="📦")
require_auth()

st.title("📦 Insumos")
st.caption("Catálogo de matérias-primas, preço atual e histórico por fornecedor.")


CAT_EMOJI = {"ALI": "🍯", "FOR": "🥣", "EMB": "📦", "EQP": "🔧", "OPR": "🧻"}
CAT_LABEL = {
    "ALI": "Alimentos (ingredientes da receita)",
    "FOR": "Formas",
    "EMB": "Embalagens",
    "EQP": "Equipamentos duráveis",
    "OPR": "Operacionais (consumíveis)",
}
# Order of inner category tabs (matches the home page / Tamanhos page).
CAT_TAB_ORDER = ["ALI", "FOR", "EMB", "EQP", "OPR"]
CAT_TAB_TITLE = {
    "ALI": "🍯 Alimentos",
    "FOR": "🥣 Formas",
    "EMB": "📦 Embalagens",
    "EQP": "🔧 Equipamentos",
    "OPR": "🧻 Operacionais",
}

# Standard unit options offered in the editor. If a produto already has a
# unit outside this list (legacy data), we include it dynamically so the
# selectbox doesn't reject the existing value.
STANDARD_UNITS = ["UN", "KG", "L", "M", "Dz", "Pente"]


# ---------------------------------------------------------------------------
# Inline data_editor styling — match the "Ingredientes da receita" st.table
# from the Tamanhos page (cream background, brand border, purple headings).
#
# Caveat: st.data_editor renders its grid on an HTML <canvas> via the Glide
# Data Editor library, so the cell text/headers themselves can't be styled
# with CSS. We can only style the wrapper (background, border, radius) and
# the toolbar. That's what's done here — see plans/insumos-iteration-2.md
# for details on what didn't work.
# ---------------------------------------------------------------------------
_EDITOR_STYLE = f"""
<style>
[data-testid="stDataEditor"] {{
    background-color: {CREAM} !important;
    border: 1px solid {CARAMEL_LIGHT} !important;
    border-radius: 12px !important;
    overflow: hidden !important;
    padding: 4px !important;
}}
[data-testid="stDataEditor"] [data-testid="stDataFrameResizable"] {{
    background-color: {CREAM} !important;
}}
/* Toolbar (search / fullscreen / download icons above the grid) */
[data-testid="stDataEditor"] [data-testid="stElementToolbar"] {{
    background-color: {BEIGE} !important;
    border-radius: 8px 8px 0 0 !important;
}}
[data-testid="stDataEditor"] [data-testid="stElementToolbar"] button,
[data-testid="stDataEditor"] [data-testid="stElementToolbar"] svg {{
    color: {PURPLE_DARK} !important;
    fill: {PURPLE_DARK} !important;
}}
</style>
"""


tab_list, tab_new = st.tabs(["📋 Insumos cadastrados", "➕ Novo insumo"])


# ============================================================================
# Lista de insumos
# ============================================================================
with tab_list:
    st.markdown(_EDITOR_STYLE, unsafe_allow_html=True)

    produtos = data.get_produtos()
    compras = data.get_compras()
    fornecedores = data.get_fornecedores()

    if produtos.empty:
        st.info("Nenhum insumo cadastrado.")
        st.stop()

    # Compute stats per produto (latest price + last fornecedor + counts).
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
    for k in ["preco_atual", "menor", "maior", "media", "n_compras", "ultima_data", "fornecedor_atual"]:
        prods_enriched[k] = [s[k] for s in stats_records]

    # --- Search filter (categoria is now controlled by sub-tabs) ---
    search = st.text_input("Buscar", placeholder="Nome ou ID")

    # --- Sort controls ---
    sort_col, dir_col = st.columns([3, 1])
    with sort_col:
        sort_by = st.selectbox(
            "Ordenar por",
            ["Nome (A-Z)", "ID", "Marca", "Preço atual", "Menor preço", "Maior preço", "Nº compras", "Última compra"],
            index=0,
        )
    with dir_col:
        asc = st.selectbox("Direção", ["Crescente ↑", "Decrescente ↓"], index=0, key="ins_dir") == "Crescente ↑"

    sort_map = {
        "Nome (A-Z)": "nome",
        "ID": "id",
        "Marca": "marca_padrao",
        "Preço atual": "preco_atual",
        "Menor preço": "menor",
        "Maior preço": "maior",
        "Nº compras": "n_compras",
        "Última compra": "ultima_data",
    }

    # Apply search across the WHOLE catalog (across categories) so the user
    # can find an insumo without first guessing the right tab.
    base_filtered = prods_enriched.copy()
    if search:
        s = search.lower()
        base_filtered = base_filtered[
            base_filtered["id"].str.lower().str.contains(s)
            | base_filtered["nome"].str.lower().str.contains(s)
        ]
    base_filtered = base_filtered.sort_values(
        sort_map[sort_by], ascending=asc, na_position="last"
    ).reset_index(drop=True)

    # Accumulators across all category sub-tabs — we run the diff loop once
    # per tab but all changes are committed together by the single "Salvar"
    # button below.
    all_name_changes: list[dict] = []
    all_unit_changes: list[dict] = []
    all_price_updates: list[dict] = []
    all_deletions: list[dict] = []

    def _render_category_grid(cat_code: str, df_cat: pd.DataFrame) -> None:
        """Render the data_editor for one category and append diffs to the
        cross-category accumulators above. Keeps each category in its own
        Streamlit widget state (separate key) so editing one tab doesn't
        clobber the unsaved edits of another."""
        if df_cat.empty:
            if search:
                st.info("Nenhum insumo encontrado com esses filtros.")
            else:
                st.info("Nenhum insumo nesta categoria.")
            return

        st.caption(f"{len(df_cat)} insumo(s)")

        editor_df = pd.DataFrame({
            "ID": df_cat["id"].values,
            "🍯": [CAT_EMOJI.get(c, "•") for c in df_cat["categoria"].values],
            "Insumo": [(n or "") for n in df_cat["nome"].values],
            "Categoria": df_cat["categoria"].values,
            "Unidade": [(u or "UN") for u in df_cat["unidade"].values],
            "Marca padrão": [(m or "") for m in df_cat["marca_padrao"].values],
            "Preço atual": [
                (float(p) if p is not None and pd.notna(p) else None)
                for p in df_cat["preco_atual"].values
            ],
            "Compras": [int(n) for n in df_cat["n_compras"].values],
            "Última": [
                # df_cat["ultima_data"].values yields numpy.datetime64 — wrap
                # in pd.Timestamp so .date() works regardless of underlying dtype.
                (pd.Timestamp(d).date() if d is not None and pd.notna(d) else None)
                for d in df_cat["ultima_data"].values
            ],
            "Notas": [(n or "") for n in df_cat["notas"].values],
            "Excluir": [False] * len(df_cat),
        })

        # Build the unit selectbox options dynamically so that legacy/odd
        # units don't get rejected by the editor.
        unit_options = list(STANDARD_UNITS)
        for u in editor_df["Unidade"].unique():
            if u and u not in unit_options:
                unit_options.append(u)

        edited = st.data_editor(
            editor_df,
            hide_index=True,
            use_container_width=True,
            num_rows="fixed",
            key=f"insumos_editor_{cat_code}",
            column_config={
                "ID": st.column_config.TextColumn(
                    "ID", disabled=True, width="small",
                    help="Identificador único do insumo (não editável).",
                ),
                "🍯": st.column_config.TextColumn(
                    "🍯", disabled=True, width="small",
                    help="Emoji da categoria — só visual.",
                ),
                "Insumo": st.column_config.TextColumn(
                    "Insumo", width="medium",
                    help="Nome do insumo. Editável.",
                ),
                "Categoria": st.column_config.TextColumn(
                    "Categoria", disabled=True, width="small",
                    help=(
                        "Mudar a categoria de um insumo muda o prefixo do ID e "
                        "exige migrar referências. Use o script "
                        "scripts/migrate_categoria.py."
                    ),
                ),
                "Unidade": st.column_config.SelectboxColumn(
                    "Unidade", options=unit_options, width="small", required=True,
                ),
                "Marca padrão": st.column_config.TextColumn(
                    "Marca padrão", width="small",
                ),
                "Preço atual": st.column_config.NumberColumn(
                    "Preço atual", format="R$ %.2f", width="small", min_value=0.0,
                    help=(
                        "Edite para registrar uma Compra de ajuste manual "
                        "(qtde 1, fornecedor = o da última compra deste insumo)."
                    ),
                ),
                "Compras": st.column_config.NumberColumn(
                    "Compras", disabled=True, format="%d", width="small",
                ),
                "Última": st.column_config.DateColumn(
                    "Última", disabled=True, format="DD/MM/YYYY", width="small",
                ),
                "Notas": st.column_config.TextColumn(
                    "Notas", width="medium",
                ),
                "Excluir": st.column_config.CheckboxColumn(
                    "Excluir", width="small",
                    help="Marque para deletar este insumo ao salvar.",
                ),
            },
        )

        # --- Diff editor_df vs edited and accumulate the save plan ---
        if edited.empty:
            return

        for i, row in edited.iterrows():
            orig = editor_df.iloc[i]
            produto_id = row["ID"]

            new_nome = str(row["Insumo"] or "").strip()
            orig_nome = str(orig["Insumo"] or "").strip()
            new_unidade = (row["Unidade"] or "UN").strip()
            new_marca = str(row["Marca padrão"] or "").strip()
            new_notas = str(row["Notas"] or "").strip()
            old_unidade = (orig["Unidade"] or "").strip()

            # Unit changes are tracked separately because they retroactively
            # reinterpret every existing Compra's unit price.
            if new_unidade != old_unidade and not bool(row["Excluir"]):
                all_unit_changes.append({
                    "produto_id": produto_id,
                    "nome": new_nome,
                    "from": old_unidade or "?",
                    "to": new_unidade,
                })

            # Track produto field edits (anything except price/excluir).
            if (
                new_nome != orig_nome
                or new_unidade != old_unidade
                or new_marca != str(orig["Marca padrão"] or "").strip()
                or new_notas != str(orig["Notas"] or "").strip()
            ):
                all_name_changes.append({
                    "produto_id": produto_id,
                    "nome": new_nome,
                    "unidade": new_unidade,
                    "marca": new_marca,
                    "notas": new_notas,
                })

            # Track price updates — only when the user typed a different,
            # positive value into "Preço atual".
            new_preco_raw = row["Preço atual"]
            orig_preco_raw = orig["Preço atual"]
            new_preco = (
                float(new_preco_raw)
                if new_preco_raw is not None and not pd.isna(new_preco_raw)
                else None
            )
            orig_preco = (
                float(orig_preco_raw)
                if orig_preco_raw is not None and not pd.isna(orig_preco_raw)
                else None
            )
            # Compare with a tiny epsilon to avoid floating-point false
            # positives (the editor round-trips values as floats).
            price_changed = (
                new_preco is not None
                and new_preco > 0
                and (orig_preco is None or abs(new_preco - orig_preco) > 0.005)
            )
            if price_changed:
                # Pick the fornecedor from the produto's last Compra; the
                # original df_cat row gives us that value.
                forn_id = df_cat.iloc[i].get("fornecedor_atual") or ""
                all_price_updates.append({
                    "produto_id": produto_id,
                    "fornecedor_id": forn_id,
                    "marca": new_marca,
                    "preco": float(new_preco),
                })

            # Track deletions (bulk path).
            if bool(row["Excluir"]):
                all_deletions.append({
                    "produto_id": produto_id,
                    "nome": new_nome,
                    "n_compras": int(orig["Compras"]),
                })

    # --- Build the inner per-categoria tabs ---
    cat_tabs = st.tabs([CAT_TAB_TITLE[c] for c in CAT_TAB_ORDER])
    for cat_code, cat_tab in zip(CAT_TAB_ORDER, cat_tabs):
        with cat_tab:
            df_cat = base_filtered[base_filtered["categoria"] == cat_code].reset_index(drop=True)
            _render_category_grid(cat_code, df_cat)

    # --- Confirmation summary + save button (spans all category tabs) ---
    name_changes = all_name_changes
    unit_changes = all_unit_changes
    price_updates = all_price_updates
    deletions = all_deletions

    has_changes = bool(name_changes or price_updates or deletions)

    # Two classes of "critical" changes need an explicit checkbox to unlock save:
    # (1) Unit changes — retroactively reinterpret every past Compra of the produto
    # (2) Deletions of produtos that still have Compras
    deletions_with_refs = [d for d in deletions if d["n_compras"] > 0]
    critical_changes = bool(unit_changes or deletions_with_refs)

    if has_changes:
        bullets = []
        if name_changes:
            bullets.append(f"✏️ {len(name_changes)} edição(ões) de cadastro")
        if price_updates:
            bullets.append(f"💰 {len(price_updates)} atualização(ões) de preço")
        if deletions:
            bullets.append(f"🗑️ {len(deletions)} exclusão(ões)")
        st.caption("Alterações pendentes: " + " · ".join(bullets))

    if critical_changes:
        with st.container(border=True):
            st.markdown("**⚠️ Mudanças que impactam dados além desta linha:**")
            for u in unit_changes:
                st.write(
                    f"- **Unidade** de `{u['produto_id']}` ({u['nome']}): "
                    f"**{u['from']} → {u['to']}**. "
                    f"_Isso recalcula o preço unitário de todas as Compras anteriores desse insumo._"
                )
            for d in deletions_with_refs:
                st.write(
                    f"- **Excluir** `{d['produto_id']}` ({d['nome']}): "
                    f"tem **{d['n_compras']} compra(s)** registradas — vão ficar órfãs."
                )
            confirm_critical = st.checkbox(
                "Confirmo as mudanças críticas acima e quero salvar",
                key="insumos_confirm_critical",
            )
    else:
        confirm_critical = True
        # Soft warning for deletions without Compras (no checkbox needed)
        if deletions:
            st.warning(
                "Você marcou para excluir: "
                + ", ".join(f"`{d['produto_id']}` ({d['nome']})" for d in deletions)
                + "."
            )

    save_clicked = st.button(
        "💾 Salvar alterações",
        type="primary",
        disabled=(not has_changes) or (critical_changes and not confirm_critical),
        use_container_width=False,
    )

    if save_clicked and has_changes:
        try:
            service = data.get_service()
            spreadsheet_id = data._spreadsheet_id()

            # 1) Field edits — update Produtos columns B (Nome), C (Unidade),
            #    D (Notas), F (Marca_padrao). Column E (Relacionados) stays.
            for nc in name_changes:
                row_num = data.find_row_by_id("Produtos", nc["produto_id"])
                service.spreadsheets().values().update(
                    spreadsheetId=spreadsheet_id,
                    range=f"Produtos!B{row_num}:D{row_num}",
                    valueInputOption="USER_ENTERED",
                    body={"values": [[nc["nome"], nc["unidade"], nc["notas"]]]},
                ).execute()
                service.spreadsheets().values().update(
                    spreadsheetId=spreadsheet_id,
                    range=f"Produtos!F{row_num}",
                    valueInputOption="USER_ENTERED",
                    body={"values": [[nc["marca"]]]},
                ).execute()

            # 2) Price updates — one Compra per produto whose "Preço atual"
            #    was edited to a new value.
            for pu in price_updates:
                data._sheets.append_compra(
                    spreadsheet_id,
                    data=date.today().strftime("%Y-%m-%d"),
                    produto_id=pu["produto_id"],
                    fornecedor_id=pu["fornecedor_id"],
                    marca=pu["marca"],
                    qtde_embalagens=1,
                    unidades_por_embalagem=1,
                    preco_total=pu["preco"],
                    notas="Ajuste manual de preço",
                    service=service,
                )

            # 3) Deletions — done last so row numbers for earlier writes
            #    stay correct. Inside this block we re-resolve the row each
            #    time because deleting shifts row numbers.
            for d in deletions:
                row_num = data.find_row_by_id("Produtos", d["produto_id"])
                data.delete_row("Produtos", row_num)

            data.invalidate_cache()
            st.success(
                f"✅ Salvo: {len(name_changes)} edição(ões), "
                f"{len(price_updates)} atualização(ões) de preço, "
                f"{len(deletions)} exclusão(ões)."
            )
            st.rerun()
        except Exception as e:
            st.error(f"Erro ao salvar: {e}")
            import traceback
            st.code(traceback.format_exc())

    # ========================================================================
    # Excluir agora — one-off deletion path.
    #
    # Streamlit's data_editor doesn't support clickable buttons inside cells,
    # so for users who want to delete a single insumo without going through
    # the checkbox + Salvar flow this mini-form is the pragmatic compromise.
    # Picks one produto from a selectbox and wipes it immediately on click.
    # ========================================================================
    if not prods_enriched.empty:
        st.divider()
        st.markdown("### ❌ Excluir agora")
        st.caption(
            "Apaga um único insumo na hora, sem precisar marcar o checkbox da "
            "tabela. Use para exclusões pontuais."
        )

        del_opts = list(prods_enriched["id"])
        del_id_to_label = {
            r["id"]: f"{CAT_EMOJI.get(r['categoria'], '•')} {r['nome']} ({r['id']})"
            for _, r in prods_enriched.iterrows()
        }

        col_pick, col_btn = st.columns([4, 1])
        with col_pick:
            del_target = st.selectbox(
                "Insumo a excluir",
                del_opts,
                format_func=lambda pid: del_id_to_label.get(pid, pid),
                index=0,
                key="ins_quick_delete_target",
                label_visibility="collapsed",
            )
        with col_btn:
            del_clicked = st.button(
                "Excluir",
                type="primary",
                key="ins_quick_delete_btn",
                use_container_width=True,
            )

        # Show a flag if the target still has Compras so the user knows
        # what they're about to orphan.
        target_row = prods_enriched[prods_enriched["id"] == del_target]
        if not target_row.empty:
            n_c = int(target_row.iloc[0]["n_compras"])
            if n_c > 0:
                st.warning(
                    f"⚠️ `{del_target}` tem **{n_c} compra(s)** registradas — "
                    "vão ficar órfãs se você excluir."
                )

        if del_clicked:
            try:
                row_num = data.find_row_by_id("Produtos", del_target)
                data.delete_row("Produtos", row_num)
                data.invalidate_cache()
                st.success(f"✅ Insumo `{del_target}` excluído.")
                st.rerun()
            except Exception as e:
                st.error(f"Erro ao excluir: {e}")
                import traceback
                st.code(traceback.format_exc())

    # ========================================================================
    # Mais detalhes — single panel that drills into ONE selected insumo.
    # ========================================================================
    if not prods_enriched.empty:
        st.divider()
        st.markdown("### 📈 Mais detalhes")

        options = list(prods_enriched["id"])
        id_to_label = {
            r["id"]: f"{CAT_EMOJI.get(r['categoria'], '•')} {r['nome']} ({r['id']})"
            for _, r in prods_enriched.iterrows()
        }
        selected_id = st.selectbox(
            "Ver detalhes de:",
            options,
            format_func=lambda pid: id_to_label.get(pid, pid),
            index=0,
            key="ins_detail_select",
        )

        p = prods_enriched[prods_enriched["id"] == selected_id].iloc[0]
        n_compras_sel = int(p["n_compras"])

        if n_compras_sel == 0:
            st.info("Esse insumo ainda não tem compras registradas.")
        else:
            sub = compras[compras["produto_id"] == selected_id].dropna(subset=["data"]).copy()
            sub = sub.sort_values("data")

            k1, k2, k3 = st.columns(3)
            with k1:
                compact_kpi("Menor preço", brl(p["menor"]))
            with k2:
                compact_kpi("Preço médio", brl(p["media"]))
            with k3:
                compact_kpi("Maior preço", brl(p["maior"]))

            if len(sub) > 1:
                st.markdown("**Evolução do preço unitário**")
                chart_df = sub[["data", "preco_unitario"]].copy()
                st.line_chart(chart_df.set_index("data"), height=240)

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
            reliable = by_supplier[by_supplier["n_compras"] >= 2]
            cheapest_id = None
            if not reliable.empty:
                cheapest_id = reliable.loc[reliable["preco_medio"].idxmin(), "fornecedor_id"]

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
            st.table(disp.set_index("Fornecedor"))

            median_price = sub["preco_unitario"].median()
            outliers = sub[sub["preco_unitario"] > median_price * 1.5]
            if not outliers.empty and median_price > 0:
                st.warning(
                    f"⚠️ {len(outliers)} compra(s) ficaram >50% acima da mediana ({brl_md(median_price)}). "
                    "Pode ser emergência ou erro — confere se faz sentido."
                )


# ============================================================================
# Criar novo insumo
# ============================================================================
with tab_new:
    st.markdown("### Cadastrar um novo insumo")
    st.caption("Útil quando você precisa adicionar um insumo sem ter ainda comprado (vai aparecer no catálogo).")

    with st.form("new_produto", clear_on_submit=True):
        cat_options = list(CAT_LABEL.keys())
        new_cat = st.radio(
            "Categoria",
            cat_options,
            format_func=lambda c: f"{CAT_EMOJI[c]} {c} — {CAT_LABEL[c]}",
            horizontal=False,
        )

        c1, c2 = st.columns([2, 1])
        with c1:
            new_nome = st.text_input("Nome do insumo", placeholder="ex: AÇÚCAR REFINADO 1KG")
        with c2:
            new_unidade = st.selectbox(
                "Unidade",
                ["UN", "KG", "L", "M", "FOLHA", "Pente", "Dz"],
                index=0,
            )
        new_notas = st.text_input("Notas (opcional)", placeholder="ex: comprado em pente de 30")

        if st.form_submit_button("➕ Criar insumo", use_container_width=True, type="primary"):
            if not new_nome.strip():
                st.error("Dá um nome pro insumo.")
            else:
                try:
                    new_id = data._sheets.create_produto(
                        data._spreadsheet_id(),
                        new_nome.strip(),
                        new_cat,
                        unidade=new_unidade,
                        notas=new_notas.strip() or "Criado pelo app",
                        service=data.get_service(),
                    )
                    data.invalidate_cache()
                    st.success(f"✅ Insumo criado: **{new_id} — {new_nome}**")
                    st.balloons()
                except Exception as e:
                    st.error(f"Erro criando: {e}")
                    import traceback
                    st.code(traceback.format_exc())
