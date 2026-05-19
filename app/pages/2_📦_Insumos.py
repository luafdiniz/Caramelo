"""Insumos page: list, filter, drill into price history, edit/delete, create new.

In the spreadsheet this tab is called 'Produtos' (legacy), but the UI says
'Insumos' to match the business vocabulary — these are raw materials, not the
final sold products (which are Tamanhos).

The list view is a single editable spreadsheet (st.data_editor). Every cell
the user is allowed to change is editable inline — no pencil buttons, no per
-row expanders. A "Novo preço" column lets her register a manual-adjustment
Compra by just typing the new price. A single "Mais detalhes" panel below
the grid shows price history / per-fornecedor analysis / outliers for the
selected insumo.
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

# Standard unit options offered in the editor. If a produto already has a
# unit outside this list (legacy data), we include it dynamically so the
# selectbox doesn't reject the existing value.
STANDARD_UNITS = ["UN", "KG", "L", "M", "Dz", "Pente"]


tab_list, tab_new = st.tabs(["📋 Insumos cadastrados", "➕ Novo insumo"])


# ============================================================================
# Lista de insumos
# ============================================================================
with tab_list:
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

    # --- Filters ---
    col_search, col_cat = st.columns([3, 2])
    with col_search:
        search = st.text_input("Buscar", placeholder="Nome ou ID")
    with col_cat:
        categorias_disponiveis = sorted(prods_enriched["categoria"].unique())
        cat_filter = st.multiselect(
            "Categoria",
            categorias_disponiveis,
            default=categorias_disponiveis,
        )

    # --- Sort controls ---
    sort_col, dir_col = st.columns([3, 1])
    with sort_col:
        sort_by = st.selectbox(
            "Ordenar por",
            ["Nome (A-Z)", "ID", "Categoria", "Marca", "Preço atual", "Menor preço", "Maior preço", "Nº compras", "Última compra"],
            index=0,
        )
    with dir_col:
        asc = st.selectbox("Direção", ["Crescente ↑", "Decrescente ↓"], index=0, key="ins_dir") == "Crescente ↑"

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

    filtered = prods_enriched[prods_enriched["categoria"].isin(cat_filter)]
    if search:
        s = search.lower()
        filtered = filtered[
            filtered["id"].str.lower().str.contains(s)
            | filtered["nome"].str.lower().str.contains(s)
        ]
    filtered = filtered.sort_values(sort_map[sort_by], ascending=asc, na_position="last").reset_index(drop=True)

    st.caption(f"{len(filtered)} de {len(prods_enriched)} insumos")

    # --- Build the editable view ---
    # Columns are ordered to read left-to-right: identity → editable fields →
    # price → action columns (Novo preço, Excluir).
    def _insumo_label(row) -> str:
        emoji = CAT_EMOJI.get(row["categoria"], "•")
        return f"{emoji} {row['nome']}"

    if filtered.empty:
        st.info("Nenhum insumo encontrado com esses filtros.")
        editor_df = pd.DataFrame()
        edited = pd.DataFrame()
    else:
        editor_df = pd.DataFrame({
            "ID": filtered["id"].values,
            "Insumo": [_insumo_label(r) for _, r in filtered.iterrows()],
            "Categoria": filtered["categoria"].values,
            "Unidade": [(u or "UN") for u in filtered["unidade"].values],
            "Marca padrão": [(m or "") for m in filtered["marca_padrao"].values],
            "Preço atual": [
                (float(p) if p is not None and pd.notna(p) else None)
                for p in filtered["preco_atual"].values
            ],
            "Novo preço": [None] * len(filtered),
            "Compras": [int(n) for n in filtered["n_compras"].values],
            "Última": [
                (d.date() if d is not None and pd.notna(d) else None)
                for d in filtered["ultima_data"].values
            ],
            "Notas": [(n or "") for n in filtered["notas"].values],
            "Excluir": [False] * len(filtered),
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
            key="insumos_editor",
            column_config={
                "ID": st.column_config.TextColumn(
                    "ID", disabled=True, width="small",
                    help="Identificador único do insumo (não editável).",
                ),
                "Insumo": st.column_config.TextColumn(
                    "Insumo", width="medium",
                    help="Emoji da categoria + nome. Você pode renomear aqui (o emoji é só visual).",
                ),
                "Categoria": st.column_config.TextColumn(
                    "Categoria", disabled=True, width="small",
                ),
                "Unidade": st.column_config.SelectboxColumn(
                    "Unidade", options=unit_options, width="small", required=True,
                ),
                "Marca padrão": st.column_config.TextColumn(
                    "Marca padrão", width="small",
                ),
                "Preço atual": st.column_config.NumberColumn(
                    "Preço atual", disabled=True, format="R$ %.2f", width="small",
                    help="Último preço unitário registrado em Compras.",
                ),
                "Novo preço": st.column_config.NumberColumn(
                    "Novo preço", format="R$ %.2f", width="small", min_value=0.0,
                    help=(
                        "Digite um valor para registrar uma Compra de ajuste manual "
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

    # --- Diff editor_df vs edited and produce a save plan ---
    name_changes: list[dict] = []   # produto edits (nome/unidade/marca/notas)
    price_updates: list[dict] = []  # new Compra to append
    deletions: list[dict] = []      # rows to delete

    if not edited.empty:
        # Keep a quick lookup of category emoji per produto so we can split
        # the "Insumo" cell back into a plain nome.
        for i, row in edited.iterrows():
            orig = editor_df.iloc[i]
            produto_id = row["ID"]
            categoria = orig["Categoria"]
            emoji = CAT_EMOJI.get(categoria, "•")

            # Strip the leading emoji + space if present, so the stored nome
            # is just the human name.
            raw_label = str(row["Insumo"]).strip()
            if raw_label.startswith(f"{emoji} "):
                new_nome = raw_label[len(f"{emoji} "):].strip()
            else:
                new_nome = raw_label

            orig_nome_raw = str(orig["Insumo"]).strip()
            orig_nome = (
                orig_nome_raw[len(f"{emoji} "):].strip()
                if orig_nome_raw.startswith(f"{emoji} ") else orig_nome_raw
            )

            new_unidade = (row["Unidade"] or "UN").strip()
            new_marca = (row["Marca padrão"] or "").strip()
            new_notas = (row["Notas"] or "").strip()

            # Track produto field edits (anything except price/excluir/new_preco).
            if (
                new_nome != orig_nome
                or new_unidade != (orig["Unidade"] or "").strip()
                or new_marca != (orig["Marca padrão"] or "").strip()
                or new_notas != (orig["Notas"] or "").strip()
            ):
                name_changes.append({
                    "produto_id": produto_id,
                    "nome": new_nome,
                    "unidade": new_unidade,
                    "marca": new_marca,
                    "notas": new_notas,
                })

            # Track price updates — only when the user typed a positive value.
            novo_preco = row["Novo preço"]
            if novo_preco is not None and not pd.isna(novo_preco) and float(novo_preco) > 0:
                # Pick the fornecedor from the produto's last Compra, fall
                # back to empty (the bot/sheets layer accepts blank strings).
                forn_id = filtered.iloc[i].get("fornecedor_atual") or ""
                price_updates.append({
                    "produto_id": produto_id,
                    "fornecedor_id": forn_id,
                    "marca": new_marca,
                    "preco": float(novo_preco),
                })

            # Track deletions.
            if bool(row["Excluir"]):
                deletions.append({
                    "produto_id": produto_id,
                    "nome": new_nome,
                    "n_compras": int(orig["Compras"]),
                })

    # --- Confirmation summary + save button ---
    has_changes = bool(name_changes or price_updates or deletions)

    if deletions:
        with_compras = [d for d in deletions if d["n_compras"] > 0]
        st.warning(
            "⚠️ Você marcou para excluir: "
            + ", ".join(f"`{d['produto_id']}` ({d['nome']})" for d in deletions)
            + (
                f". {len(with_compras)} desses têm compras registradas — elas vão ficar órfãs."
                if with_compras else "."
            )
        )

    if has_changes:
        bullets = []
        if name_changes:
            bullets.append(f"✏️ {len(name_changes)} edição(ões) de cadastro")
        if price_updates:
            bullets.append(f"💰 {len(price_updates)} atualização(ões) de preço")
        if deletions:
            bullets.append(f"🗑️ {len(deletions)} exclusão(ões)")
        st.caption("Alterações pendentes: " + " · ".join(bullets))

    save_clicked = st.button(
        "💾 Salvar alterações",
        type="primary",
        disabled=not has_changes,
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

            # 2) Price updates — one Compra per produto with a "Novo preço".
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
    # Mais detalhes — single panel that drills into ONE selected insumo.
    # ========================================================================
    if not filtered.empty:
        st.divider()
        st.markdown("### 📈 Mais detalhes")

        options = list(filtered["id"])
        id_to_label = {
            r["id"]: f"{CAT_EMOJI.get(r['categoria'], '•')} {r['nome']} ({r['id']})"
            for _, r in filtered.iterrows()
        }
        selected_id = st.selectbox(
            "Ver detalhes de:",
            options,
            format_func=lambda pid: id_to_label.get(pid, pid),
            index=0,
            key="ins_detail_select",
        )

        p = filtered[filtered["id"] == selected_id].iloc[0]
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
