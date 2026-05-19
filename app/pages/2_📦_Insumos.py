"""Insumos page: list, filter, drill into price history, edit/delete, create new.

In the spreadsheet this tab is called 'Produtos' (legacy), but the UI says
'Insumos' to match the business vocabulary — these are raw materials, not the
final sold products (which are Tamanhos).

The page exposes TWO complementary views of the same catalog, side by side:

1. **📋 Tabela** — one big editable `st.data_editor` with ALL produtos in a
   single grid (no per-categoria sub-tabs inside). Search + sort apply to
   the whole catalog. Bulk save via one Salvar button at the bottom. Bulk
   delete via the Excluir checkbox column. The "Excluir agora" mini-form
   was removed — Luiza found it ugly.

2. **📇 Lista** — sub-tabs per categoria (🍯 Alimentos / 🥣 Formas /
   📦 Embalagens / 🔧 Equipamentos / 🧻 Operacionais). Each sub-tab
   renders a vertical list of cards (one card per produto), each with a
   "🔎 Mais detalhes" expander showing price history, per-fornecedor
   analysis, outliers, an inline edit form (1 card = 1 Salvar), and a
   safe delete button (disabled when the produto still has Compras).

3. **➕ Novo insumo** — unchanged. Form to register a new produto.

Editor behaviors (Tabela tab):
- The category emoji lives in its own narrow column (no longer mashed into
  the Insumo name cell).
- "Preço atual" is itself editable: typing a new value creates a Compra of
  manual adjustment when the user clicks "Salvar" (fornecedor = the
  produto's most-recent fornecedor, notas = "Ajuste manual de preço").
- "Categoria" is intentionally disabled. Changing categoria changes the ID
  prefix and requires migrating references in Compras / Tamanhos / Receitas
  — that lives in scripts/migrate_categoria.py.

Lista cards expose the SAME editable fields per produto (nome, unidade,
marca padrão, notas) and the same Compra-on-price-change behavior, but
scoped to a single produto with its own Salvar button. The two views
share data layer writers but each has its own UX — no shared state.
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
    card_title,
    CARAMEL_LIGHT,
    CREAM,
    PURPLE_DARK,
    BEIGE,
)


setup_page("Insumos", icon="📦")
require_auth()

st.title("📦 Insumos")
st.caption("Catálogo de matérias-primas, preço atual e histórico por fornecedor.")


CAT_EMOJI = {"ALI": "🍯", "FOR": "🥣", "EMB": "📦", "GRA": "🖨️", "EQP": "🔧", "OPR": "🧻"}
CAT_LABEL = {
    "ALI": "Alimentos (ingredientes da receita)",
    "FOR": "Formas",
    "EMB": "Embalagens (físicas)",
    "GRA": "Gráfica (adesivos, etiquetas, impressos)",
    "EQP": "Equipamentos duráveis",
    "OPR": "Operacionais (consumíveis)",
}
# Order of inner category tabs (matches the home page / Tamanhos page).
CAT_TAB_ORDER = ["ALI", "FOR", "EMB", "GRA", "EQP", "OPR"]
CAT_TAB_TITLE = {
    "ALI": "🍯 Alimentos",
    "FOR": "🥣 Formas",
    "EMB": "📦 Embalagens",
    "GRA": "🖨️ Gráfica",
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


# ---------------------------------------------------------------------------
# Shared data load — both Tabela and Lista views read from the same enriched
# DataFrame. We compute it once at the top of the page so the two tabs stay
# in sync and we avoid re-aggregating per tab render.
# ---------------------------------------------------------------------------
produtos = data.get_produtos()
compras = data.get_compras()
fornecedores = data.get_fornecedores()

# Fornecedor id -> nome lookup, used by Lista cards to label rows in the
# per-fornecedor breakdown.
fornecedores_map: dict[str, str] = (
    dict(zip(fornecedores["id"], fornecedores["nome"]))
    if not fornecedores.empty
    else {}
)


def _stats_for(produto_id: str) -> dict:
    """Aggregate Compras stats + the resolved current price.

    `preco_atual` is the price the rest of the app uses for cost calc — the
    manual override if still active, else the weighted average of the last 3
    compras. `origem` carries the source label ("manual", "wac", "none").
    The min/max/mean/count stats remain purely about the Compras history.
    """
    sub = compras[compras["produto_id"] == produto_id].dropna(subset=["data"])
    resolved = data.current_unit_price(produto_id, compras=compras, produtos=produtos)
    origem = data.price_origin(produto_id, compras=compras, produtos=produtos)
    if sub.empty:
        return {
            "preco_atual": resolved if resolved > 0 else None,
            "origem": origem,
            "menor": None, "maior": None,
            "media": None, "n_compras": 0, "ultima_data": None,
            "fornecedor_atual": None,
        }
    latest = sub.sort_values("data", ascending=False).iloc[0]
    return {
        "preco_atual": resolved if resolved > 0 else None,
        "origem": origem,
        "menor": float(sub["preco_unitario"].min()),
        "maior": float(sub["preco_unitario"].max()),
        "media": float(sub["preco_unitario"].mean()),
        "n_compras": len(sub),
        "ultima_data": latest["data"],
        "fornecedor_atual": latest["fornecedor_id"],
    }


if not produtos.empty:
    prods_enriched = produtos.copy()
    _stats_records = [_stats_for(p) for p in prods_enriched["id"]]
    for _k in ["preco_atual", "origem", "menor", "maior", "media", "n_compras", "ultima_data", "fornecedor_atual"]:
        prods_enriched[_k] = [s[_k] for s in _stats_records]
else:
    prods_enriched = produtos


tab_tabela, tab_ali, tab_for, tab_emb, tab_gra, tab_eqp, tab_opr = st.tabs([
    "📋 Tabela",
    CAT_TAB_TITLE["ALI"],
    CAT_TAB_TITLE["FOR"],
    CAT_TAB_TITLE["EMB"],
    CAT_TAB_TITLE["GRA"],
    CAT_TAB_TITLE["EQP"],
    CAT_TAB_TITLE["OPR"],
])
_cat_tabs = {"ALI": tab_ali, "FOR": tab_for, "EMB": tab_emb, "GRA": tab_gra, "EQP": tab_eqp, "OPR": tab_opr}


# ============================================================================
# Tabela — one big editable grid with ALL produtos.
# Plus an expandable "Novo insumo" form at the top (used to be its own tab).
# ============================================================================
with tab_tabela:
    st.markdown(_EDITOR_STYLE, unsafe_allow_html=True)

    # --- Create-new-insumo form, collapsed by default ---
    with st.expander("➕ Novo insumo", expanded=False):
        st.caption(
            "Cadastrar um insumo sem ter comprado ainda — vai aparecer no catálogo."
        )
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
                    # C8: Soft duplicate-name check. We don't enforce uniqueness
                    # (the catalog legitimately has variants of the same thing —
                    # "OVO BRANCO" vs "OVO VERMELHO" once started as the same
                    # product, but they're now separate produtos to keep the
                    # WAC distinct). So this is a warning, not a block.
                    nome_norm = new_nome.strip().casefold()
                    if not produtos.empty:
                        clashes = produtos[
                            produtos["nome"].fillna("").str.casefold() == nome_norm
                        ]
                        if not clashes.empty:
                            existing_list = ", ".join(
                                f"`{r['id']}`" for _, r in clashes.iterrows()
                            )
                            st.warning(
                                f"⚠️ Já existe insumo com esse nome: {existing_list}. "
                                "Vou criar mesmo assim — confirma se é um produto "
                                "diferente (marca, tamanho, fornecedor)."
                            )
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

    if produtos.empty:
        st.info("Nenhum insumo cadastrado.")
    else:
        # --- Search filter (acts on the whole catalog) ---
        search = st.text_input("Buscar", placeholder="Nome ou ID", key="ins_tabela_search")

        # --- Sort controls ---
        sort_col, dir_col = st.columns([3, 1])
        with sort_col:
            sort_by = st.selectbox(
                "Ordenar por",
                ["Nome (A-Z)", "ID", "Categoria", "Marca", "Preço atual",
                 "Menor preço", "Maior preço", "Nº compras", "Última compra"],
                index=0,
                key="ins_tabela_sort_by",
            )
        with dir_col:
            asc = st.selectbox(
                "Direção", ["Crescente ↑", "Decrescente ↓"], index=0,
                key="ins_tabela_dir",
            ) == "Crescente ↑"

        sort_map = {
            "Nome (A-Z)": "nome",
            "ID": "id",
            "Categoria": "categoria",
            "Marca": "marca_padrao",
            "Preço atual": "preco_atual",
            "Menor preço": "menor",
            "Maior preço": "maior",
            "Nº compras": "n_compras",
            "Última compra": "ultima_data",
        }

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

        if base_filtered.empty:
            if search:
                st.info("Nenhum insumo encontrado com esses filtros.")
            else:
                st.info("Nenhum insumo cadastrado.")
        else:
            st.caption(f"{len(base_filtered)} insumo(s)")

            _ORIGEM_LABEL = {"manual": "✋ Manual", "wac": "📊 Média", "none": "—"}

            # Toggle: default view = brand-styled st.table. Edit mode = data_editor.
            ins_edit_key = "ins_tabela_edit_mode"
            if ins_edit_key not in st.session_state:
                st.session_state[ins_edit_key] = False
            ins_edit_active = st.session_state[ins_edit_key]

            if not ins_edit_active:
                # --- VIEW MODE (st.table, brand-styled like Ingredientes da receita) ---
                disp = pd.DataFrame({
                    "ID": base_filtered["id"].values,
                    "🍯": [CAT_EMOJI.get(c, "•") for c in base_filtered["categoria"].values],
                    "Insumo": [(n or "") for n in base_filtered["nome"].values],
                    "Categoria": base_filtered["categoria"].values,
                    "Unidade": [(u or "UN") for u in base_filtered["unidade"].values],
                    "Marca padrão": [(m or "") for m in base_filtered["marca_padrao"].values],
                    "Preço atual": [
                        brl(float(p)) if p is not None and pd.notna(p) else "—"
                        for p in base_filtered["preco_atual"].values
                    ],
                    "Origem": [_ORIGEM_LABEL.get(o, "—") for o in base_filtered["origem"].values],
                    "Compras": [str(int(n)) for n in base_filtered["n_compras"].values],
                    "Última": [
                        pd.Timestamp(d).strftime("%d/%m/%Y") if d is not None and pd.notna(d) else "—"
                        for d in base_filtered["ultima_data"].values
                    ],
                    "Notas": [(n or "") for n in base_filtered["notas"].values],
                })
                st.table(disp.set_index("ID"))
                if st.button("✏️ Editar tabela", key="ins_tabela_edit_btn"):
                    st.session_state[ins_edit_key] = True
                    st.rerun()
            else:
                # --- EDIT MODE ---
                st.info(
                    "✏️ Modo de edição **ativo**. Clique em Salvar pra confirmar, "
                    "ou Cancelar pra desistir. ⚠️ Se você trocar de aba sem salvar, "
                    "as alterações não vão persistir."
                )
                if st.button("✖ Cancelar edição", key="ins_tabela_cancel_btn"):
                    st.session_state[ins_edit_key] = False
                    st.rerun()

                editor_df = pd.DataFrame({
                    "ID": base_filtered["id"].values,
                    "🍯": [CAT_EMOJI.get(c, "•") for c in base_filtered["categoria"].values],
                    "Insumo": [(n or "") for n in base_filtered["nome"].values],
                    "Categoria": base_filtered["categoria"].values,
                    "Unidade": [(u or "UN") for u in base_filtered["unidade"].values],
                    "Marca padrão": [(m or "") for m in base_filtered["marca_padrao"].values],
                    "Preço atual": [
                        (float(p) if p is not None and pd.notna(p) else None)
                        for p in base_filtered["preco_atual"].values
                    ],
                    "Origem": [_ORIGEM_LABEL.get(o, "—") for o in base_filtered["origem"].values],
                    "Compras": [int(n) for n in base_filtered["n_compras"].values],
                    "Última": [
                        (pd.Timestamp(d).date() if d is not None and pd.notna(d) else None)
                        for d in base_filtered["ultima_data"].values
                    ],
                    "Notas": [(n or "") for n in base_filtered["notas"].values],
                    "Excluir": [False] * len(base_filtered),
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
                    key="insumos_editor_all",
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
                                "Editar grava um override manual direto no insumo — "
                                "não cria Compra. O override expira sozinho quando "
                                "uma Compra mais nova entrar."
                            ),
                        ),
                        "Origem": st.column_config.TextColumn(
                            "Origem", disabled=True, width="small",
                            help=(
                                "De onde vem o Preço atual: 📊 Média = média ponderada "
                                "das últimas 3 compras; ✋ Manual = override que você "
                                "definiu; — = sem dados."
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

                # --- Diff editor_df vs edited and build the save plan ---
                name_changes: list[dict] = []
                unit_changes: list[dict] = []
                price_updates: list[dict] = []
                deletions: list[dict] = []

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
                        unit_changes.append({
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
                        name_changes.append({
                            "produto_id": produto_id,
                            "nome": new_nome,
                            "unidade": new_unidade,
                            "marca": new_marca,
                            "notas": new_notas,
                        })

                    # Track price updates — typing a different positive value sets
                    # a manual override on the produto (Produtos.G/H). Clearing the
                    # cell removes the override. Either way: no Compra is created.
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
                    orig_origem = str(base_filtered.iloc[i].get("origem") or "")
                    if new_preco is not None and new_preco > 0:
                        price_changed = (
                            orig_preco is None or abs(new_preco - orig_preco) > 0.005
                        )
                        if price_changed:
                            price_updates.append({
                                "produto_id": produto_id,
                                "action": "set",
                                "preco": float(new_preco),
                            })
                    elif new_preco is None and orig_preco is not None and orig_origem == "manual":
                        # Cleared the cell on a row that had an active override —
                        # interpret as "remove override". Clearing on a WAC row
                        # is a no-op (nothing to remove).
                        price_updates.append({
                            "produto_id": produto_id,
                            "action": "clear",
                        })

                    # Track deletions (bulk path).
                    if bool(row["Excluir"]):
                        deletions.append({
                            "produto_id": produto_id,
                            "nome": new_nome,
                            "n_compras": int(orig["Compras"]),
                        })

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
                    key="ins_tabela_save",
                )

                if save_clicked and has_changes:
                    try:
                        service = data.get_service()
                        spreadsheet_id = data._spreadsheet_id()

                        # Snapshot original names so we can detect which
                        # name_changes actually changed the Nome (vs just
                        # editing unidade / marca / notas). We only want to
                        # propagate the cached nome on Receita_Ingredientes
                        # when the produto's Nome itself moved.
                        orig_name_by_id = dict(
                            zip(base_filtered["id"], base_filtered["nome"].fillna(""))
                        )

                        # 1) Field edits — update Produtos columns B (Nome),
                        #    C (Unidade), D (Notas), F (Marca_padrao). Column E
                        #    (Relacionados) stays.
                        renamed_produto_ids: list[tuple[str, str]] = []  # (produto_id, new_nome)
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
                            # Track actual name changes (not just unit/marca/notas
                            # edits that share the same path).
                            if (nc["nome"] or "").strip() != (orig_name_by_id.get(nc["produto_id"]) or "").strip():
                                renamed_produto_ids.append((nc["produto_id"], nc["nome"]))

                        # 1b) Propagate name changes to Receita_Ingredientes
                        # (col C = cached `nome`). Receitas joins by produto_id,
                        # but the cached name is what `_build_component_df`
                        # falls back to when produtos_df is unavailable — so
                        # leaving it stale produces UI drift.
                        if renamed_produto_ids and data._has_sheet("Receita_Ingredientes"):
                            ri_rows = service.spreadsheets().values().get(
                                spreadsheetId=spreadsheet_id,
                                range="Receita_Ingredientes!A:F",
                                valueRenderOption="UNFORMATTED_VALUE",
                            ).execute().get("values", [])
                            # Build {produto_id: new_nome} for quick lookup, then
                            # walk the tab and patch C{row} where col B matches.
                            new_name_by_pid = dict(renamed_produto_ids)
                            for i, r in enumerate(ri_rows[1:], start=2):  # skip header, 1-indexed
                                if not r or len(r) < 2:
                                    continue
                                pid = r[1]
                                if pid in new_name_by_pid:
                                    service.spreadsheets().values().update(
                                        spreadsheetId=spreadsheet_id,
                                        range=f"Receita_Ingredientes!C{i}",
                                        valueInputOption="USER_ENTERED",
                                        body={"values": [[new_name_by_pid[pid]]]},
                                    ).execute()

                        # 2) Price updates — write directly to Produtos.G/H.
                        #    No Compra is created. The override expires when a
                        #    newer Compra for this produto is registered.
                        today_iso = date.today().isoformat()
                        for pu in price_updates:
                            row_num = data.find_row_by_id("Produtos", pu["produto_id"])
                            if pu["action"] == "set":
                                values = [[pu["preco"], today_iso]]
                            else:  # "clear"
                                values = [["", ""]]
                            service.spreadsheets().values().update(
                                spreadsheetId=spreadsheet_id,
                                range=f"Produtos!G{row_num}:H{row_num}",
                                valueInputOption="USER_ENTERED",
                                body={"values": values},
                            ).execute()

                        # 3) Deletions — done last so row numbers for earlier
                        #    writes stay correct. We re-resolve the row each
                        #    time because deleting shifts row numbers.
                        for d in deletions:
                            row_num = data.find_row_by_id("Produtos", d["produto_id"])
                            data.delete_row("Produtos", row_num)

                        data.invalidate_cache()
                        # Drop back to view mode after a successful save, the
                        # same way the other pages do — staying in edit mode
                        # while the data underneath has changed makes the
                        # diff feel stale on the next interaction.
                        st.session_state[ins_edit_key] = False
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


    # ============================================================================
# Lista — sub-tabs per categoria, vertical list of cards with expanders.
# ============================================================================

def _render_produto_card(
    p: pd.Series,
    fornecedores_map: dict[str, str],
    compras_df: pd.DataFrame,
    service_getter,
    spreadsheet_id_getter,
) -> None:
    """
    Render one produto as a card with:
      - Top row: title (emoji + nome + ID badge + meta), Preço atual KPI, Compras KPI
      - 🔎 Mais detalhes expander: min/avg/max KPIs, per-fornecedor table,
        price history chart, outlier warning, inline edit form, delete button

    `p` is one row from `prods_enriched`. The expander's edit form and
    delete button use the same data layer writers as the Tabela tab —
    `service_getter` / `spreadsheet_id_getter` are passed lazily so we
    don't instantiate the Sheets service unless the user actually saves
    or deletes.
    """
    produto_id = p["id"]
    nome = p["nome"] or ""
    categoria = p["categoria"]
    unidade = (p["unidade"] or "UN").strip()
    marca = (p["marca_padrao"] or "").strip()
    notas = p["notas"] or ""
    emoji = CAT_EMOJI.get(categoria, "•")
    preco_atual = p["preco_atual"]
    origem = str(p.get("origem") or "")
    preco_manual_data = p.get("preco_manual_data") if "preco_manual_data" in p.index else None
    n_compras = int(p["n_compras"])
    ultima_data = p["ultima_data"]
    ultima_str = (
        pd.Timestamp(ultima_data).strftime("%d/%m/%Y")
        if ultima_data is not None and pd.notna(ultima_data)
        else "—"
    )
    # Bot-created produtos carry "via bot" in their notas (see
    # bot/lib/sheets.py — `notas: str = "Cadastrado via bot"`).
    is_from_bot = "via bot" in (notas or "").lower()

    # Meta line: categoria · unidade · 🤖 (if bot) · marca padrão (if any)
    meta_parts = [f"{CAT_LABEL.get(categoria, categoria)} · {unidade}"]
    if is_from_bot:
        meta_parts.append('<span title="Criado pelo bot">🤖</span>')
    if marca:
        meta_parts.append(f"Marca padrão: <strong>{marca}</strong>")
    meta = " · ".join(meta_parts)

    with st.container(border=True):
        # --- Top row: title (left) + Preço atual (middle) + Compras (right) ---
        col_title, col_preco, col_n = st.columns([3, 1, 1])
        with col_title:
            card_title(
                f"{emoji} {nome}",
                badge=produto_id,
                meta=meta,
                meta_is_html=True,
                meta_below=True,
            )
        with col_preco:
            if origem == "manual":
                manual_str = (
                    pd.Timestamp(preco_manual_data).strftime("%d/%m/%Y")
                    if preco_manual_data is not None and pd.notna(preco_manual_data)
                    else ""
                )
                kpi_help = (
                    f"✋ Override manual"
                    + (f" desde {manual_str}" if manual_str else "")
                    + " — expira na próxima Compra deste insumo."
                )
            elif origem == "wac":
                kpi_help = f"📊 Média ponderada das últimas 3 compras. Última: {ultima_str}"
            else:
                kpi_help = "Sem compras nem override registrados."
            compact_kpi(
                "Preço atual",
                brl(preco_atual) if preco_atual is not None else "—",
                help=kpi_help,
            )
        with col_n:
            compact_kpi("Compras", str(n_compras))

        # Inline action: clear the override when one is active. Sits right
        # under the KPI strip so the affordance is visible without opening
        # the expander.
        if origem == "manual":
            if st.button(
                "✋ Limpar override manual",
                key=f"clr_override_{produto_id}",
                help="Volta a calcular Preço atual pela média ponderada das últimas compras.",
            ):
                try:
                    row_num = data.find_row_by_id("Produtos", produto_id)
                    data.get_service().spreadsheets().values().update(
                        spreadsheetId=data._spreadsheet_id(),
                        range=f"Produtos!G{row_num}:H{row_num}",
                        valueInputOption="USER_ENTERED",
                        body={"values": [["", ""]]},
                    ).execute()
                    data.invalidate_cache()
                    st.success(f"✅ Override de `{produto_id}` removido.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Erro ao limpar override: {e}")

        # --- Mais detalhes expander ---
        with st.expander("🔎 Mais detalhes"):
            if n_compras == 0:
                st.info("Esse insumo ainda não tem compras registradas.")
            else:
                sub = compras_df[compras_df["produto_id"] == produto_id].dropna(subset=["data"]).copy()
                sub = sub.sort_values("data")

                # Small KPI strip — menor / médio / maior price.
                k1, k2, k3 = st.columns(3)
                with k1:
                    compact_kpi("Menor preço", brl(p["menor"]))
                with k2:
                    compact_kpi("Preço médio", brl(p["media"]))
                with k3:
                    compact_kpi("Maior preço", brl(p["maior"]))

                # Per-fornecedor breakdown (mirrors the old Mais detalhes panel).
                st.markdown("**Por fornecedor**")
                by_supplier = sub.groupby("fornecedor_id").agg(
                    n_compras=("id", "count"),
                    preco_medio=("preco_unitario", "mean"),
                    preco_min=("preco_unitario", "min"),
                    preco_max=("preco_unitario", "max"),
                    ultima_data=("data", "max"),
                ).reset_index()
                by_supplier["fornecedor_nome"] = by_supplier["fornecedor_id"].map(
                    lambda fid: fornecedores_map.get(fid, fid)
                )
                # Star the cheapest reliable (>= 2 compras) fornecedor.
                reliable = by_supplier[by_supplier["n_compras"] >= 2]
                cheapest_id = (
                    reliable.loc[reliable["preco_medio"].idxmin(), "fornecedor_id"]
                    if not reliable.empty else None
                )
                disp = by_supplier.copy()
                disp["fornecedor"] = disp.apply(
                    lambda r: f"{'⭐ ' if r['fornecedor_id'] == cheapest_id else ''}"
                              f"{r['fornecedor_nome'] or r['fornecedor_id']}",
                    axis=1,
                )
                disp["ultima_data"] = disp["ultima_data"].dt.strftime("%d/%m/%Y")
                disp["preco_medio"] = disp["preco_medio"].apply(brl)
                disp["preco_min"] = disp["preco_min"].apply(brl)
                disp["preco_max"] = disp["preco_max"].apply(brl)
                disp = disp[["fornecedor", "n_compras", "preco_medio", "preco_min", "preco_max", "ultima_data"]]
                disp.columns = ["Fornecedor", "Nº compras", "Preço médio", "Menor", "Maior", "Última compra"]
                st.table(disp.set_index("Fornecedor"))

                # Price history chart — only meaningful with more than one point.
                if len(sub) > 1:
                    st.markdown("**Evolução do preço unitário**")
                    chart_df = sub[["data", "preco_unitario"]].copy()
                    st.line_chart(chart_df.set_index("data"), height=200)

                # Outlier warning — last price >40% above the median.
                median_price = sub["preco_unitario"].median()
                if median_price and median_price > 0 and preco_atual is not None:
                    if preco_atual > median_price * 1.4:
                        st.warning(
                            f"⚠️ Preço atual ({brl_md(preco_atual)}) está mais de "
                            f"40% acima da mediana histórica ({brl_md(median_price)}). "
                            "Confere se faz sentido — pode ser emergência ou erro."
                        )

            st.divider()

            # --- Inline edit form (one Salvar per card) ---
            st.markdown("**✏️ Editar este insumo**")

            unit_options = list(STANDARD_UNITS)
            if unidade and unidade not in unit_options:
                unit_options.append(unidade)

            with st.form(f"edit_form_{produto_id}", clear_on_submit=False):
                ec1, ec2 = st.columns([2, 1])
                with ec1:
                    new_nome = st.text_input(
                        "Nome", value=nome, key=f"edit_nome_{produto_id}",
                    )
                with ec2:
                    new_unidade = st.selectbox(
                        "Unidade",
                        unit_options,
                        index=unit_options.index(unidade) if unidade in unit_options else 0,
                        key=f"edit_unidade_{produto_id}",
                    )
                new_marca = st.text_input(
                    "Marca padrão", value=marca,
                    key=f"edit_marca_{produto_id}",
                )
                new_notas = st.text_input(
                    "Notas", value=notas,
                    key=f"edit_notas_{produto_id}",
                )

                save_card = st.form_submit_button(
                    "💾 Salvar", type="primary", use_container_width=False,
                )

                if save_card:
                    new_nome_s = (new_nome or "").strip()
                    new_unidade_s = (new_unidade or "UN").strip()
                    new_marca_s = (new_marca or "").strip()
                    new_notas_s = (new_notas or "").strip()
                    changed_any = (
                        new_nome_s != nome
                        or new_unidade_s != unidade
                        or new_marca_s != marca
                        or new_notas_s != notas
                    )
                    if not new_nome_s:
                        st.error("Nome não pode ficar vazio.")
                    elif not changed_any:
                        st.info("Nada para salvar — nenhum campo mudou.")
                    else:
                        # Unit change retroactively reinterprets every past
                        # Compra of this produto. Flag it loudly. The Tabela
                        # view enforces a confirm-checkbox before unlocking
                        # save; here we warn after-the-fact and rely on the
                        # user understanding the implication (cards are
                        # per-produto so the blast radius is local).
                        try:
                            service = service_getter()
                            spreadsheet_id = spreadsheet_id_getter()
                            row_num = data.find_row_by_id("Produtos", produto_id)
                            service.spreadsheets().values().update(
                                spreadsheetId=spreadsheet_id,
                                range=f"Produtos!B{row_num}:D{row_num}",
                                valueInputOption="USER_ENTERED",
                                body={"values": [[new_nome_s, new_unidade_s, new_notas_s]]},
                            ).execute()
                            service.spreadsheets().values().update(
                                spreadsheetId=spreadsheet_id,
                                range=f"Produtos!F{row_num}",
                                valueInputOption="USER_ENTERED",
                                body={"values": [[new_marca_s]]},
                            ).execute()
                            data.invalidate_cache()
                            if new_unidade_s != unidade:
                                st.warning(
                                    f"⚠️ Unidade mudou de **{unidade} → {new_unidade_s}**. "
                                    "O preço unitário de Compras anteriores foi recalculado "
                                    "ao reler o catálogo."
                                )
                            st.success(f"✅ `{produto_id}` atualizado.")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Erro ao salvar: {e}")
                            import traceback
                            st.code(traceback.format_exc())

            st.divider()

            # --- Delete button (two-step confirm) ---
            #
            # Disabled when the produto still has Compras (we don't want to
            # orphan rows by accident from a single click). The Tabela tab
            # still allows it behind the critical-changes checkbox — power
            # users who really need to delete with refs can go there.
            if n_compras > 0:
                st.button(
                    f"🗑️ Deletar este insumo",
                    disabled=True,
                    key=f"del_disabled_{produto_id}",
                    help=(
                        f"Tem {n_compras} compra(s) registradas — vão ficar órfãs. "
                        "Para excluir mesmo assim, use a aba Tabela (com confirmação)."
                    ),
                )
                st.caption(
                    f"Deletar bloqueado — `{produto_id}` tem **{n_compras}** "
                    "compra(s). Use a aba Tabela se realmente quiser."
                )
            else:
                # Two-step: first click flags pending, second click actually
                # deletes. Keyed by produto_id so each card has its own
                # confirm state, independent of the others.
                confirm_key = f"del_confirm_{produto_id}"
                if confirm_key not in st.session_state:
                    st.session_state[confirm_key] = False

                if not st.session_state[confirm_key]:
                    if st.button(
                        "🗑️ Deletar este insumo",
                        key=f"del_btn_{produto_id}",
                    ):
                        st.session_state[confirm_key] = True
                        st.rerun()
                else:
                    st.warning(
                        f"⚠️ Confirma a exclusão de `{produto_id}` ({nome})? "
                        "Essa ação não pode ser desfeita."
                    )
                    dc1, dc2 = st.columns([1, 1])
                    with dc1:
                        if st.button(
                            "Sim, deletar",
                            type="primary",
                            key=f"del_yes_{produto_id}",
                        ):
                            try:
                                row_num = data.find_row_by_id("Produtos", produto_id)
                                data.delete_row("Produtos", row_num)
                                data.invalidate_cache()
                                st.session_state[confirm_key] = False
                                st.success(f"✅ `{produto_id}` excluído.")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Erro ao excluir: {e}")
                                import traceback
                                st.code(traceback.format_exc())
                    with dc2:
                        if st.button(
                            "Cancelar",
                            key=f"del_no_{produto_id}",
                        ):
                            st.session_state[confirm_key] = False
                            st.rerun()


# ============================================================================
# One root tab per categoria — each shows a list of cards with a "Mais
# detalhes" expander per insumo.
# ============================================================================
for _cat in CAT_TAB_ORDER:
    with _cat_tabs[_cat]:
        if produtos.empty:
            st.info("Nenhum insumo cadastrado.")
            continue

        cat_produtos = prods_enriched[prods_enriched["categoria"] == _cat]

        search_lista = st.text_input(
            "Buscar nesta categoria",
            placeholder="Nome ou ID",
            key=f"search_lista_{_cat}",
        )
        if search_lista:
            s = search_lista.lower()
            cat_produtos = cat_produtos[
                cat_produtos["id"].str.lower().str.contains(s)
                | cat_produtos["nome"].str.lower().str.contains(s)
            ]

        # Order: nome A-Z for stable visual scan. Power-user sorting lives
        # on the Tabela tab — keep the cards view simple.
        cat_produtos = cat_produtos.sort_values("nome", na_position="last")

        if cat_produtos.empty:
            if search_lista:
                st.info("Nenhum insumo encontrado nesta categoria com esse filtro.")
            else:
                st.info("Nenhum insumo nesta categoria.")
        else:
            st.caption(f"{len(cat_produtos)} insumo(s)")
            for _, prod_row in cat_produtos.iterrows():
                _render_produto_card(
                    prod_row,
                    fornecedores_map,
                    compras,
                    data.get_service,
                    data._spreadsheet_id,
                )


