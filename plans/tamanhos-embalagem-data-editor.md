# Tamanhos: embalagens como data_editor

Refactored the "Embalagens deste tamanho" section inside each tamanho edit form
to use `st.data_editor` instead of stacked rows of `number_input` + `🗑️`
checkbox.

Columns: `ID` (text, disabled), `Nome` (text, disabled), `Qtde` (NumberColumn,
min 0, step 0.05, format %.2f), `Remover` (CheckboxColumn).

Newly-picked packages from the "Adicionar novas embalagens" multiselect are
appended to the editor's dataframe with qtde=1.0. On save, integer-unit
produtos (UN, DZ, etc.) are rounded back to int. `bulk_rm` and `Remover=True`
both propagate as qty=0; the existing save handler drops rows with `q <= 0`.

Kept: bulk-remove checkbox, multiselect, save handler, delete section, "Novo
tamanho" wizard, Receita selectbox. No new imports.
