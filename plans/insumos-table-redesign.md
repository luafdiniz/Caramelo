# Insumos — table-like redesign

## Problem
The old list view used a bordered `st.container` card per produto with 3 large
KPI columns and an expander labeled "📊 Histórico, edição e gestão". Each card
took ~6-8 vertical inches; scanning 30+ insumos felt "muito travado".

## What changed
- List view is now a **table-like layout**: a header strip with column captions
  (`Insumo · Marca · Preço atual · Compras · Última`) and one compact row per
  produto using `st.columns([4, 2, 2, 1, 2, 1])`. No per-row border — rows are
  separated by a thin styled `<hr>`. Each row is ~2-3 inches tall.
- Inline price update via `st.popover` (`✏️` button next to the price cell):
  a small selectbox to choose the fornecedor (pre-filled with the most recent
  one for that produto), a number_input for the new unit price, and a "Salvar"
  button. Saving writes a new Compra via `bot.lib.sheets.append_compra` with
  `qtde_embalagens=1`, `unidades_por_embalagem=1`, `preco_total=novo_preco`,
  and `notas="Ajuste manual de preço (sem compra)"`. This flows naturally
  through the existing `latest_unit_price` pipeline without touching the data
  layer.
- Existing expander renamed `✏️ Editar` and now hosts the full edit form, price
  history, per-supplier analysis, outlier detector, and delete — unchanged
  internally, just hidden until clicked.
- Sort options expanded with "Marca" so the new column is also sortable.

## Why writing a Compra (vs. a separate "manual price" field)
Adding a price-only column would require a data-layer change and a new
priority rule in `latest_unit_price`. Writing a Compra with a tagged note keeps
the pipeline single-source-of-truth and makes the price update visible in the
history table. The user explicitly understands this is a "price record", not a
real purchase — the notes column carries that context.

## Punted
- No special highlight in the monthly Compras report for "Ajuste manual" rows.
  If they pollute analytics later, filter by `notas` upstream.
- Fornecedor in the popover defaults to most-recent; if a produto has no
  prior compra, the popover shows an empty selectbox and the save button is
  disabled with a hint to add a regular Compra first.
