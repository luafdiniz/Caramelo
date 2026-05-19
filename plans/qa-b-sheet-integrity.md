# QA Sheet Integrity — 2026-05-19

Auditoria read-only da planilha de produção (`SPREADSHEET_ID=1hV9zTIMyX3wlULkWAYN_-nBeNeM6adfL0Zz6MIvwFXE`).

## 🛑 BLOCK

Nenhum bloqueio crítico. As migrações estruturais (Produtos A-H, Compras A-M, novas abas, CLI-000) foram aplicadas corretamente. Os problemas encontrados são de **dados** (refs quebradas), não de schema.

## ⚠️ FLAG

1. **9 refs órfãs em `Embalagens_Por_Tamanho` + `Compras` apontando para produtos migrados/inexistentes** — A migração EMB→GRA não atualizou as referências downstream. Detalhes em "Orphan references".
2. **`Aliases` A-018 e `Compras` C-054 referenciam `FOR-007` que não existe** (max FOR é FOR-006). Bug provável de cadastro via bot — produto "SACOLA KRAFT 14x9x21.5" deveria resolver para `EMB-025` (cadastrado no mesmo dia, mesmo tamanho).
3. **`Aliases` A-011 com `resolved_id=SKIP`** — convenção válida (alias intencionalmente ignorado) mas não está em nenhum ID set. Confirmar se "SKIP" é o sentinel oficial.
4. **8 linhas vazias em `Produtos`** (rows 18,19,20,21,28,35,36,40) — sobras das migrações (EMB-008/009/010/011→GRA, EMB-018→GRA-005, EMB-021/022/023 consolidados em FOR-006). Não quebram nada, mas poluem leitura.
5. **Todos os 4 `Tamanhos` têm `receita_id` vazio** — fallback para REC-001 (padrão) funciona, mas vale explicitar para clareza futura.
6. **TAM-004 ausente** (sequência TAM-001/002/003/005). Não é orphan, mas é um gap intencional? Vale confirmar.
7. **`Receitas` e `Receita_Ingredientes`**: apenas REC-001 cadastrada com 4 ingredientes (correto), mas vale lembrar que com só 1 receita não dá pra exercitar o sistema multi-receita.
8. **0 Compras com frete>0 ou desconto>0** — colunas L/M existem mas ainda não foram usadas. Esperado nesse estágio.

## ✅ PASS

- Headers de `Produtos`, `Compras`, `Clientes`, `Vendas`, `Precos`, `Receitas`, `Receita_Ingredientes` corretos.
- Todas as abas esperadas existem: `Clientes`, `Vendas`, `Precos`, `Receitas`, `Receita_Ingredientes`, `_Receita_old`.
- `CLI-000 Cliente Avulso` presente e ativo.
- Migração EMB→GRA: 5 novos produtos (GRA-001..005) com nomes e marcas plausíveis. IDs antigos (EMB-008/009/010/011/018) realmente sumiram.
- 0 produtos com prefixo inválido (todos em ALI/FOR/EMB/GRA/EQP/OPR).
- 0 IDs duplicados em Produtos, Fornecedores, Tamanhos, Receitas, Clientes.
- 0 orphans em `Receita_Ingredientes` (todos os 4 ingredientes apontam para REC-001 e produtos válidos; todos têm `componente` definido).
- 0 orphans em Vendas (vazia).
- 0 produtos com `Preco_manual` preenchido (cols G/H zeradas — esperado, override ainda não acionado).
- 0 Compras com `data` vazia, `produto_id` vazio ou `preco_unitario=0`+`total_unidades>0`.
- Exatamente 1 receita marcada como `padrao=TRUE` (REC-001 Tradicional).

## 📋 Detalhes por área

### Migrations

| Aba | Cols esperados | Cols reais | OK? |
|---|---|---|---|
| Produtos | A-H (Preco_manual G, Preco_manual_data H) | 8 cols, headers batem | ✅ |
| Compras | A-M (frete L, desconto M) | 13 cols, headers batem | ✅ |
| Clientes | nova aba | 10 cols, 1 row (CLI-000) | ✅ |
| Vendas | nova aba | 12 cols, 0 rows | ✅ |
| Precos | nova aba | 5 cols, 0 rows | ✅ |
| Receitas | já existia | 4 cols, 1 row (REC-001) | ✅ |
| Receita_Ingredientes | já existia | 6 cols, 4 rows | ✅ |
| _Receita_old | preservado | 4 cols | ✅ |

### Orphan references

**`Embalagens_Por_Tamanho` (5 órfãs)** — produtos referenciados foram migrados para GRA mas estas linhas não foram atualizadas. Coluna C `Nome_Produto` mostra `#N/A` (sinal de que tinha VLOOKUP que quebrou):

| Row | Tamanho_ID | Produto_ID (órfão) | Nome | Sugestão |
|---|---|---|---|---|
| 6 | TAM-002 | EMB-018 | #N/A | trocar por GRA-005 (PAPEL) |
| 13 | TAM-003 | EMB-018 | #N/A | trocar por GRA-005 (PAPEL) |
| 16 | TAM-003 | EMB-011 | #N/A | EMB-011 também foi migrado — verificar para qual GRA |
| 21 | TAM-001 | EMB-018 | #N/A | trocar por GRA-005 (PAPEL) |
| 24 | TAM-001 | EMB-011 | #N/A | idem 16 |

Observação: EMB-011 não estava na lista oficial de migrações (008→GRA-001, 009→GRA-002, 010→GRA-003, 011→GRA-004, 018→GRA-005). EMB-011 estaria no mapa: **EMB-011 → GRA-004 (ADESIVO ME VÊ 2 FATIAS)**. Confirmar.

**`Compras` (4 órfãs)**:

| Row | ID | Produto_ID | Fornecedor | Marca | Total | Observação |
|---|---|---|---|---|---|---|
| 28 | C-027 | EMB-008 | FORN-008 | VINIL BRILHO | R$ 20 | Migrado da planilha original — trocar por GRA-001 |
| 30 | C-029 | EMB-010 | FORN-008 | VINIL FOSCO | R$ 22 | trocar por GRA-003 |
| 38 | C-037 | EMB-018 | FORN-008 | PAPEL | R$ 16 | trocar por GRA-005 |
| 55 | C-054 | **FOR-007** | FORN-011 | (vazio) | R$ 43 | Cadastro via bot OCR de nota manuscrita — FOR-007 não existe; provavelmente deveria ser **EMB-025** |

**`Aliases` (2 refs problemáticas)**:

| Row | ID | tipo | texto_original | resolved_id | Status |
|---|---|---|---|---|---|
| 10 | A-011 | PRODUTO | BEB ENERG RED BULL 250ML | `SKIP` | sentinel "skip" — OK se for convenção |
| 17 | A-018 | PRODUTO | 14x9x21.5 | `FOR-007` | **bug** — texto bate com EMB-025; provavelmente deveria ser EMB-025 |

**`Receita_Ingredientes`**: 0 órfãs. Todos os 4 ingredientes apontam para REC-001 e para produtos válidos (ALI-001..004), todos com `componente` definido (1 calda + 3 massa).

**`Vendas`**: vazia, 0 órfãs.

### IDs

| Prefixo | Count | Range | Faltando | Comentário |
|---|---|---|---|---|
| ALI | 5 | 1..5 | — | OK |
| FOR | 6 | 1..6 | — | OK (FOR-007 referenciado em Aliases/Compras é **inexistente** — bug, não gap) |
| EMB | 17 | 1..25 | 8,9,10,11,18,21,22,23 | 8/9/10/11/18 migrados para GRA ✅; 21/22/23 consolidados em FOR-006 (notas confirmam) ✅ |
| GRA | 5 | 1..5 | — | OK (novos) |
| EQP | 4 | 1..4 | — | OK |
| OPR | 1 | 1..1 | — | OK |

- 0 prefixos inválidos.
- 0 IDs duplicados em qualquer aba.
- Fornecedores usa prefixo **`FORN-`** (FORN-001..011, FORN-013 — falta FORN-012, vale confirmar se gap intencional). 12 fornecedores.
- Esse "FORN-" diferente de "FOR-" (Produto) é fonte potencial de confusão — bot já cometeu o erro em C-054/A-018.

### Receitas

- 1 receita: `REC-001 Tradicional` com `padrao=TRUE`.
- 4 ingredientes em REC-001:
  - ALI-001 (Leite condensado 395g) — 1 UN — massa
  - ALI-002 (Açúcar refinado 1kg) — 0,1 KG — calda
  - ALI-003 (Leite integral 1L) — 0,4 L — massa
  - ALI-004 (Ovo) — 4 UN — massa
- 0 ingredientes sem `componente`.
- 0 receitas órfãs (só existe REC-001 e ela tem ingredientes).

### Compras

- 56 linhas totais. 4 com produto_id órfão (ver acima). 0 sem data. 0 sem produto. 0 com preco=0 e qtde>0.
- **0 linhas com `frete>0`**.
- **0 linhas com `desconto>0`**.
- Consequência: não foi possível auditar consistência intra-grupo (mesma data+fornecedor) de frete/desconto porque ninguém usou ainda. Quando a primeira compra com rateio for cadastrada, vale re-rodar essa parte.

### Tamanhos

| ID | Nome | Peso | receita_id |
|---|---|---|---|
| TAM-001 | Médio 500g | 0,5 kg | (vazio → fallback REC-001) |
| TAM-002 | Grande 1Kg | 1 kg | (vazio → fallback REC-001) |
| TAM-003 | Quadrado 200g | 0,22 kg | (vazio → fallback REC-001) |
| TAM-005 | Potinho 40g | 0,04 kg | (vazio → fallback REC-001) |

- 4 tamanhos cadastrados, **TAM-004 ausente** (gap na sequência).
- 0 com `receita_id` explícito → todos caem no fallback.
- 0 com receita_id órfão.

### Preço manual

- 0 produtos com `Preco_manual` (col G) preenchido.
- 0 produtos com `Preco_manual_data` (col H) preenchida.
- 0 inconsistências (G sem H ou vice-versa).
- Sistema de override está dormindo — vai exercitar quando alguém setar manualmente.

---

## Resumo executivo

| Categoria | Status | Counts |
|---|---|---|
| Schema/migrations | ✅ | 100% aplicado |
| Orphan refs (Embalagens) | ⚠️ | 5 rows |
| Orphan refs (Compras) | ⚠️ | 4 rows |
| Orphan refs (Aliases) | ⚠️ | 1 row crítico (A-018) + 1 sentinel (A-011) |
| Orphans (Receita_Ing, Vendas) | ✅ | 0 |
| IDs (prefixos, duplicados) | ✅ | 0 problemas |
| Receitas integrity | ✅ | 1 padrão, 4 ingredientes, 100% componente |
| Linhas vazias em Produtos | ⚠️ | 8 rows (sobras de migração) |
| Frete/desconto consistency | ✅ | nada usado ainda |
| Preco_manual consistency | ✅ | nada usado ainda |

**Próximas ações sugeridas** (não executadas — read-only):
1. Atualizar `Embalagens_Por_Tamanho` rows 6, 13, 21 (EMB-018→GRA-005) e rows 16, 24 (EMB-011→GRA-004).
2. Atualizar `Compras` C-027 (EMB-008→GRA-001), C-029 (EMB-010→GRA-003), C-037 (EMB-018→GRA-005).
3. Corrigir `Compras` C-054 e `Aliases` A-018 — investigar se `FOR-007` deveria ser `EMB-025`.
4. Limpar (ou consolidar) as 8 linhas vazias em `Produtos`.
5. Considerar preencher `receita_id` explicitamente nos 4 Tamanhos para evitar depender do fallback.
