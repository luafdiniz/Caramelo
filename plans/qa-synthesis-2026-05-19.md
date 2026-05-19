# QA Synthesis — 2026-05-19

Síntese dos 4 sub-agents (A: code static, B: live Sheet, C: app UX, D: bot).
Relatórios individuais em `qa-{a,b,c,d}-*.md`.

---

## 🛑 BLOCKERS — fixar antes de uso intenso

### B1. Órfãs em `Embalagens_Por_Tamanho` (5 rows com #N/A)
**Confirmado via query live:**
| row | tamanho_id | produto_id (órfão) | deveria ser |
|-----|------------|--------------------|-------------|
| 6 | TAM-002 | EMB-018 | GRA-005 |
| 13 | TAM-003 | EMB-018 | GRA-005 |
| 21 | TAM-001 | EMB-018 | GRA-005 |
| 16 | TAM-003 | EMB-011 | GRA-004 |
| 24 | TAM-001 | EMB-011 | GRA-004 |

**Causa raiz:** `scripts/migrate_categoria.py` tem bug de off-by-one (ou similar) ao calcular os índices de Embalagens_Por_Tamanho. O log da migração mostrou "row 17" e "row 22", mas as refs reais ficaram em row 16 e 21.

**Impacto:** custo de embalagem desses 3 tamanhos calculado errado (linhas órfãs entram com preco=0, somam nada — então embalagem está subestimada).

**Fix:** script `cleanup_emb_por_tamanho_orphans.py` (one-off) que mapeia EMB-018→GRA-005 e EMB-011→GRA-004 nessas 5 rows. Trivial.

### B2. Bot não tem GRA na UI (4 lugares)
**Reportado por agents A e D.** Backend aceita criar GRA (`bot/lib/sheets.py::create_produto`), Gemini reconhece GRA no prompt — mas a UI do bot tem 4 lugares hard-coded sem GRA:
- `bot/lib/orchestrator.py:364` `_cat_order` em `_ipicklist`
- `bot/lib/orchestrator.py:435` whitelist do `icreate`
- `bot/lib/orchestrator.py:685-691` `CATEGORIA_LABEL` no `/novo`
- `bot/lib/orchestrator.py:1249-1255` `CATEGORIA_PICK_BUTTONS` no `/compra`

**Impacto:** se o Gemini classificar errado um adesivo como EMB e ela tentar corrigir manualmente, ela NÃO consegue selecionar GRA. Cria como ALI/FOR/EMB/EQP/OPR.

**Fix:** ~5 linhas em cada um dos 4 lugares. Trivial.

### A1. `migrate_categoria.py` corrompe `Preco_manual` em re-runs
**Reportado por agent A.** Script lê `Produtos!A:F` (6 colunas). Quando ele recria a row do produto migrado, escreve só 6 colunas — **apaga G (Preco_manual) e H (Preco_manual_data) se houver override**.

**Impacto:** ZERO agora (nenhum produto tem override hoje, agent B confirmou 0 manuais). Mas é tempo bomba: se a Luiza ajustar preço de algum insumo e depois migrar categoria, perde o override silenciosamente.

**Fix:** mudar `A:F` → `A:H` no script. 1 linha.

### A2. `consolidate_compras.py` mesmo problema + range stale
Mesmo bug do A1, mais: clear de Compras usa `A:K` (deveria ser `A:M` agora que tem frete/desconto). Risco: rodar consolidate apagaria frete/desconto.

**Impacto:** dormente até a próxima consolidação de compras.

**Fix:** mudar `A:F` → `A:H` e `A:K` → `A:M`. 2 linhas.

---

## ⚠️ FLAGS — não bloqueia mas vale arrumar

### Schema/dados
- **B5.** 8 linhas vazias em Produtos (rows 18-21, 28, 35-36, 40) — sobras das migrações EMB→GRA. Coluna A vazia. Não atrapalha funcionalmente, mas polui visualmente quem abre o Sheet.
- **B6.** 4 órfãos em Compras: C-027 (EMB-008), C-029 (EMB-010), C-037 (EMB-018) com nota "Migrado da planilha original"; **C-054 referencia FOR-007 que não existe** (bug antigo de confusão FOR/FORN). Recomendação: editar C-054 → EMB-025 (era SACOLA KRAFT). Os outros 3 já foram migrados pra GRA-001/003/005 — atualizar refs.
- **B7.** Aliases A-018 referencia FOR-007 (mesmo bug). Texto "14x9x21.5" sugere EMB-025.
- **B8.** Aliases A-011 com `resolved_id=SKIP` (sentinel pra ignorar) — confirmar se é convenção válida.
- **B9.** 4 Tamanhos com `receita_id` vazio (fallback funciona). Explícito seria mais robusto.
- **B10.** TAM-004 ausente (gap intencional?).

### Code dead/inconsistencies
- **A3.** `latest_unit_price` deprecated ainda usado em 5 lugares (Receitas + Tamanhos pages). Não usa override manual. Sugestão: migrar pra `current_unit_price`.
- **A4.** `scripts/create_spreadsheet.py` cria Produtos com 4 colunas só — stale, não reflete schema atual com G/H.
- **A5.** Coluna `Produtos.E` (relacionados) sem UI de edição em lugar nenhum — só usada no auto-include em Tamanhos.
- **A6.** Race do session_state em Insumos: `ins_tabela_edit_mode` não reseta ao salvar via Tabela (ao contrário de Tamanhos/Receitas/Clientes/Preços que resetam).
- **A7.** `Precos.py:148` usa `disp.iloc[i].name + 2` — quebra se houver linhas em branco no meio do range.

### App UX
- **C1.** **CLI-000 sem proteção contra exclusão** (Cliente Avulso). Se a Luiza deletar, vendas balcão ficam órfãs.
- **C2.** Renomear produto na Insumos/Tabela NÃO propaga pro nome cacheado em `Receita_Ingredientes`. Não corrompe — só confunde (nome antigo aparece em receita).
- **C3.** Vendas: quando `resolve_preco_unit=0` (B2B sem faixa cadastrada), input fica desabilitado SEM aviso explicativo.
- **C4.** Produção permite salvar fornada com `vendidos > produzidos` (mostra `st.error` mas não bloqueia submit).
- **C5.** Preços: editar `qtde_min` pra valor já existente cria duplicação (só valida no fluxo "Nova faixa").
- **C6.** Preços: NÃO detecta B2B mais caro que B2C (deveria alertar).
- **C7.** Receitas: cadastrar receita com 0 ingredientes é aceito sem aviso.
- **C8.** Insumos: nomes duplicados aceitos no cadastro.
- **C9.** Fornecedores: não segue o padrão view/edit toggle (edit direto no expander). Vale alinhar.
- **C10.** Compras, Produção (histórico), Home ainda usam `st.dataframe` em vez de `st.table`. Vale alinhar pro brand.

### Bot
- **D1.** Zero testes pra `distribute_frete_desconto` — função nova, edge cases não cobertos.
- **D2.** Rateio retorna floats sem snap a centavo (`2.6666...` na célula).
- **D3.** `test_parser.py` referencia `orchestrator.format_receipt_summary` que foi renomeado pra `_format_overview` — teste quebrado.
- **D4.** Múltiplos receipts em paralelo: `find_latest_active_state_id` pega só o último; `handle_photo/document` não limpam state anterior como `/novo` e `/compra` fazem.
- **D5.** Frete/desconto aparecem em Compras na planilha mas a página `5_Compras.py` não exibe essas colunas.
- **D6.** NF-e XML parser não extrai `vFrete` / `vDesc` do XML (deveria — está no schema NF-e).

---

## ✅ PASS — verificado e OK

### Migrations & schema
- Headers de Produtos (A:H), Compras (A:M), Clientes (A:J), Vendas (A:L), Precos (A:E): consistentes entre migrations, `data.py` getters, `bot/lib/sheets.py`.
- CLI-000 seed criado corretamente em Clientes.
- 5 GRA-001..005 criados; EMB-008/009/010/011/018 ausentes (esperado).
- Receitas: 1 receita REC-001 (Tradicional) com `padrao=TRUE` único, 4 ingredientes (1 calda + 3 massa), todos com componente.

### Funcionalidade
- `distribute_frete_desconto` bem implementado (rateio + ValueError em desconto > total).
- `handle_text_hint` dispatches todos os states `awaiting_*` (pack_size, text_for_item, frete_desconto).
- HTML escaping consistente em `_esc` (bot) e nos pages.
- `cancel:state_id` funciona em qualquer ponto do fluxo do bot.
- View/edit toggle pattern OK em 4 de 5 tabelas (todas exceto Insumos que tem o flag A6).
- Cache invalidation chamado em todos os writes do app.
- State keys prefixados por ID em Tamanhos e Receitas (não vazam entre items).
- Two-step confirm em todas as deletions destrutivas (exceto CLI-000 — flag C1).
- CSS mobile cobre páginas novas (8/9/10).

### Segurança
- Webhook valida `chat_id` antes de processar payload.
- Todos messages do bot usam `parse_mode="HTML"` (sem risco de Markdown `_` unbalanced).
- `get_service` usa `startswith("{")` + `open()`, não `Path.is_file()` — proteção contra OSError leak do CLAUDE.md honrada.

### Tests
- `bot/tests/test_nfe_xml.py`: **25/25 PASS**.

### Métricas atuais da planilha
- Produtos: 38 IDs únicos (+ 8 rows vazias)
- Fornecedores: 12 (gap em FORN-012)
- Compras: 56
- Tamanhos: 4 (gap em TAM-004)
- Embalagens_Por_Tamanho: 25 (5 órfãs)
- Aliases: 18
- Receitas: 1, Ingredientes: 4
- Clientes: 1 (CLI-000), Vendas: 0, Precos: 0

---

## 🎯 Recomendação de ordem de fix

**Fila 1 (correção de dados — fazer ASAP):**
1. **B1**: cleanup script pra 5 órfãs em Embalagens_Por_Tamanho. ~10 min.
2. **B6**: cleanup das 4 Compras órfãs. ~5 min.

**Fila 2 (UI gaps — fazer no próximo merge):**
3. **B2**: GRA nos 4 lugares do orchestrator. ~15 min.
4. **C1**: proteger CLI-000 contra exclusão. ~5 min.
5. **C3**: aviso quando `resolve_preco_unit=0` em Vendas. ~5 min.

**Fila 3 (cleanup tempo bomba):**
6. **A1+A2**: fix `migrate_categoria.py` + `consolidate_compras.py` ranges. ~5 min.
7. **A6**: reset `ins_tabela_edit_mode` ao salvar. ~3 min.

**Fila 4 (polimento):**
8. **D1**: testes pra `distribute_frete_desconto`. ~30 min.
9. **D2**: snap a centavo no rateio. ~5 min.
10. **D5**: exibir frete/desconto em Compras. ~10 min.
11. **C9**: Fornecedores view/edit toggle. ~30 min.
12. **C10**: convert Compras/Produção/Home `st.dataframe` → `st.table`. ~15 min.

**Adiar/decisões pendentes:**
- C4: aceita salvar fornada com vendidos > produzidos? (talvez seja útil se "perda" virar concept)
- C7: receita sem ingredientes — deveria bloquear ou só warning?
- C8: nomes duplicados — bloquear ou warning?
- B10: TAM-004 gap intencional?
- B8: A-011 com SKIP — convenção?

**Total fila 1+2+3:** ~50 min de trabalho. Volume controlado.
