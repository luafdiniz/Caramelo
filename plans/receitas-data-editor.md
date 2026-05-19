# Receitas page — data_editor refactor (2026-05-18)

Replaced the read-only `st.table` + hidden edit form with two inline
`st.data_editor` widgets (Calda / Massa) per receita. Columns:
`ID` (text, RO), `Nome` (text, RO), `Qtde` (NumberColumn, step=0.05,
format="%.3g"), `Unidade` (SelectboxColumn — UN/KG/L/M/Dz/Pente/G/ML plus
any legacy unit present), `Custo` (text BRL, RO), `Remover` (checkbox).

"➕ Adicionar ingrediente": per-component selectbox (produtos NOT yet in
the component) + Adicionar button. New rows enter with qtde=1 and the
produto's natural unit; staged in `st.session_state` until save.

Removed the `✏️ Editar receita` expander — nome + padrao moved to a
`⚙️ Configurar` popover next to the title. `🗑️ Deletar receita` kept as
an expander, tucked at the bottom. Single `💾 Salvar alterações` button
per receita commits popover edits + both editors atomically.
