# Insumos page — data_editor refactor

Replaces the row-by-row layout (6-column strip + per-row `✏️` popover + per-row
"✏️ Editar" expander + a duplicate edit form inside that expander) with a single
`st.data_editor`.

## Layout

- Filtros (busca + categoria) + ordenação (mesma UX de antes) acima da grade.
- `st.data_editor` editável com as colunas:
  ID (ro) · Insumo (rw, emoji+nome) · Categoria (ro) · Unidade (selectbox) ·
  Marca padrão (rw) · Preço atual (ro, R$) · Novo preço (rw, R$) · Compras (ro) ·
  Última (ro, DD/MM/YYYY) · Notas (rw) · Excluir (checkbox).
- Resumo de pendências + botão `💾 Salvar alterações` (desabilitado quando nada mudou).
- Painel **Mais detalhes** ÚNICO abaixo da grade, com `selectbox` "Ver detalhes de:".
  Mostra KPIs (menor/médio/maior), evolução de preço, tabela por fornecedor
  (com ⭐ no mais barato confiável) e alerta de outliers.

## Workflow do "Novo preço"

Preenchendo qualquer valor > 0 e clicando Salvar, append em Compras com
`fornecedor` = o da última compra (vazio se nenhuma), `marca` = marca_padrao,
`qtde=1`, `unidades_por_embalagem=1`, `preco_total = novo preço`,
`notas="Ajuste manual de preço"`. A coluna reseta no próximo rerun.

## Punted

- Sem opção de escolher fornecedor diferente do último ao atualizar preço
  (caso raro — a aba Compras cobre isso).
