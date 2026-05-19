# Insumos page — iteration 2 (2026-05-18)

Follow-up to `insumos-data-editor.md` based on Luiza's feedback.

## What changed

- **Inner category tabs** replaced the categoria multiselect. Inside
  "📋 Insumos cadastrados" there are now 5 sub-tabs (Alimentos / Formas /
  Embalagens / Equipamentos / Operacionais), each with its own
  `st.data_editor`. The search box still works across all categories
  (the produto stays in its category tab; the search just filters within).
- **Emoji moved to its own column** (`🍯`, narrow, disabled). The Insumo
  column now holds just the plain nome — no more emoji prefix to strip
  when diffing.
- **`Preço atual` is editable inline.** The separate "Novo preço" column
  was removed. Typing a new value (different from the current one) and
  clicking Salvar creates a Compra with `notas = "Ajuste manual de preço"`,
  fornecedor = the produto's last fornecedor.
- **`Categoria` stays disabled** with a tooltip pointing to
  `scripts/migrate_categoria.py` (changing categoria changes the ID
  prefix and requires migrating references — not a single-cell edit).
- **"❌ Excluir agora" mini-form** added below the table for one-off
  deletions (selectbox + Excluir button, immediate). The Excluir
  checkbox column was kept for bulk deletes via Salvar.
- **Editor wrapper styling**: cream background, caramel-light border,
  12px radius, and the toolbar gets BEIGE bg + purple icons — matches
  the brand feel of the "Ingredientes da receita" `st.table` on the
  Tamanhos page.

## What didn't / couldn't change (visual)

`st.data_editor` renders its grid on an HTML `<canvas>` via the Glide
Data Editor library, so the cell text and column headers themselves
can't be styled with CSS. We can only style the wrapper. The grid
interior (cell text color, header strip color, alternating row tint)
stays Streamlit-default. Acceptable per the spec — the FUNCTIONAL
parts (editable cells) are what mattered.

## Save path

All four category grids feed the same accumulators (`name_changes`,
`unit_changes`, `price_updates`, `deletions`), so one "Salvar
alterações" button commits the cross-category changes in one shot.
Critical-changes gate (unit changes + deletions with Compras) still
applies.
