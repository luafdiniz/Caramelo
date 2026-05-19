# Insumos page — iteration 3 (2026-05-19)

Follow-up to `insumos-iteration-2.md`. Adds a second, complementary
view of the catalog.

## What changed

- **Outer tabs are now 3:** 📋 Tabela / 📇 Lista / ➕ Novo insumo.
- **📋 Tabela** is one big `st.data_editor` with ALL produtos — no more
  per-categoria sub-tabs inside the editor. Search + sort live above
  the grid and act on the whole catalog. Adds Categoria as a sort option.
  The "❌ Excluir agora" mini-form and the separate "📈 Mais detalhes"
  drill-down panel are gone — bulk delete via the Excluir checkbox is
  the only delete path here, and the per-produto drill-down moved into
  Lista cards.
- **📇 Lista** is new: 5 inner sub-tabs (one per categoria), each
  showing a vertical list of bordered cards. Each card has a top row
  (title + Preço atual + Compras KPIs) and a `🔎 Mais detalhes`
  expander with min/avg/max KPIs, per-fornecedor table, price history
  chart, outlier warning, an inline edit form (one Salvar per card),
  and a safe delete button (disabled with a hint when the produto has
  Compras — Tabela tab handles that case).
- **➕ Novo insumo** is unchanged.

Card rendering is factored into `_render_produto_card(...)` for reuse
across the 5 sub-tabs. Both views share data layer writers but each
has its own UX — no shared state.
