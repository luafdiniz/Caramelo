# Sessão 2026-05-19 PM — Roadmap Phil

Sessão de 4 temas baseados no feedback que o Phil deu olhando o site. Os
planos detalhados ficaram em `plans/tema-{a,c,d,e}-*.md`. Aqui o resumo do
que foi implementado, o que precisa rodar pra subir, e o que ficou aberto.

## Tema B (custo operacional / kWh) — adiado

Backlog explícito. Não mexer agora.

## Tema A — Custo dinâmico de insumo + edição manual sem Compra fantasma

**Estratégia:** Moving Weighted Average com janela de **N=3 compras**
(`WAC_WINDOW_N` em `app/lib/data.py`) + override manual opcional em duas
colunas novas de `Produtos`. O override **expira sozinho** assim que entra
uma Compra mais nova daquele produto.

**Arquivos:**
- `scripts/migrate_produtos_preco_manual.py` — adiciona colunas G=`Preco_manual`
  + H=`Preco_manual_data` na aba Produtos. Dry-run + `--apply`.
- `bot/lib/sheets.py::get_produtos` — agora lê A:H, devolve `preco_manual` e
  `preco_manual_data`.
- `app/lib/data.py`:
  - `get_produtos` parseia as duas colunas novas.
  - `current_unit_price(produto_id, compras, produtos)` — função pública nova.
    Resolução em ordem: override válido → WAC últimas 3 → 0.
  - `price_origin(produto_id, ...)` retorna `"manual" | "wac" | "none"`.
  - `latest_unit_price` continua existindo como alias deprecado pra
    `current_unit_price`. Pode ser deletada quando todas as chamadas
    migrarem.
  - `calc_custo_alimento_unid` + `calc_custo_embalagem_unid` passam a usar
    `current_unit_price`.
- `app/pages/2_📦_Insumos.py`:
  - `_stats_for` agora devolve também `origem`.
  - Coluna nova **`Origem`** na Tabela (📊 Média / ✋ Manual / —).
  - Editar "Preço atual" passa a gravar `Produtos.G/H` (não cria mais Compra
    "Ajuste manual de preço"). Apagar a célula em produto com override
    ativo = limpa o override.
  - Help text atualizado.
  - Cards na Lista mostram tooltip explicando origem do preço. Quando o
    override está ativo, aparece botão **"✋ Limpar override manual"** abaixo
    do KPI.

**Pra subir:**
1. `python scripts/migrate_produtos_preco_manual.py --apply`
2. Push o código (deploy automático Vercel + Streamlit Cloud).

## Tema C — Frete/desconto rateado + Categoria GRA-

**Arquivos:**
- `scripts/migrate_compras_frete.py` — adiciona L=`frete` + M=`desconto`
  na aba Compras.
- `bot/lib/sheets.py`:
  - `append_compra` aceita `frete=0` e `desconto=0` (escreve em L/M).
  - Whitelist de categorias inclui `"GRA"`.
  - **`distribute_frete_desconto(items, frete, desconto)`** — função pura
    que devolve os `preco_total` efetivos com rateio proporcional. Levanta
    `ValueError` se desconto deixaria algum item negativo.
- `bot/lib/gemini.py`:
  - Ambos os prompts (`SYSTEM_PROMPT` e `TEXT_PROMPT`) descrevem GRA como
    categoria, mandam adesivo/etiqueta pra GRA explicitamente, e pedem
    `"frete"` e `"desconto"` como campos estruturados.
- `bot/lib/orchestrator.py`:
  - `_finalize` calcula o rateio antes de chamar `append_compra` N vezes —
    cada item entra com `preco_total` efetivo, `frete` e `desconto` cravados
    nas colunas L/M de toda linha do batch.
  - `_ask_final` mostra **Frete · Desconto** e ganha botão
    **"🚚 Editar frete/desconto"**.
  - Novo callback `editfd:{state_id}` + state `awaiting_frete_desconto` +
    `_handle_frete_desconto_text` (parse `"8 / 0"`, `"15,50 / 5"`, etc).
- `app/lib/data.py::get_compras` — range estendido `A2:M`, colunas `frete` e
  `desconto` coerce-numéricas.
- `scripts/migrate_categoria.py::VALID_CATEGORIAS` inclui GRA.
- `app/pages/2_📦_Insumos.py` — sexta tab "🖨️ Gráfica" + CAT_LABEL com
  "Embalagens (físicas)" pra explicitar a distinção.
- `app/pages/1_🍮_Tamanhos.py::_cat_order` inclui GRA com ordem 2 (depois
  de FOR/EMB).

**Pra subir:**
1. `python scripts/migrate_compras_frete.py --apply`
2. Push o código.
3. Migrar 5 produtos EMB→GRA (1 comando por produto, com `--apply`):
   ```bash
   python scripts/migrate_categoria.py --from EMB-008 --to-categoria GRA --apply
   python scripts/migrate_categoria.py --from EMB-009 --to-categoria GRA --apply
   python scripts/migrate_categoria.py --from EMB-010 --to-categoria GRA --apply
   python scripts/migrate_categoria.py --from EMB-011 --to-categoria GRA --apply
   python scripts/migrate_categoria.py --from EMB-018 --to-categoria GRA --apply
   ```
   Conferir antes se a lista do Sheet bate com a do plano (`plans/tema-c-*.md`).
4. EMB-005 "FITA PRODUTO ARTESANAL": **decidir** se tem impressão → vai
   GRA, ou se é fita lisa → fica EMB.

## Tema E — Calculadora multi-direcional + polimento

**Arquivos:**
- `app/lib/calc.py` (novo, ~200 linhas):
  - `CalcState` dataclass com 18 campos opcionais.
  - 6 solvers (cada um chama o subconjunto de equações relevantes):
    `solve_custo_e_margem`, `solve_preco_para_margem`,
    `solve_qtde_para_faturar`, `solve_kg_com_orcamento`,
    `solve_resultado_fornada`, `solve_preco_kg_unid`.
  - `PRESETS` / `PRESET_LABELS` / `SOLVERS` pra a UI consumir.
  - Sanity warnings: prejuízo, margem > 95%, sobras de massa, etc.
- `app/pages/3_🧮_Calculadora.py` reescrita:
  - Selectbox de Tamanho opcional (pré-popula inputs).
  - Radio "Resolver para:" com os 6 presets.
  - Por-preset: bloco de inputs + outputs em `compact_kpi`.
  - Botão "Salvar preço" só no preset 1 (com Tamanho selecionado).
  - Expander "🔍 Memória de cálculo".
- `app/pages/1_🍮_Tamanhos.py`:
  - **Total embalagem por unidade** mostrado como caption logo abaixo do
    data_editor de embalagens (item 12), filtrando linhas marcadas pra
    remover.
- Item 13b (filtro por coluna no data_editor): **descartado** — Streamlit
  não suporta nativo, e 3-6 embalagens por tamanho não justifica busca
  manual.

**Pra subir:** só push. Sem migração.

## Tema D — Clientes, Vendas e Preço B2B (com faixas)

**Arquivos:**
- `scripts/migrate_clientes_vendas.py` — cria 3 abas novas:
  - `Clientes` A:J (10 cols) + seed `CLI-000 — Cliente Avulso` (B2C)
  - `Vendas` A:L (12 cols)
  - `Precos` A:E (5 cols) — tamanho_id × tipo_cliente × qtde_min × preco_unit
- `app/lib/data.py`:
  - `get_clientes` / `get_vendas` / `get_precos` cached loaders, todos com
    fallback pra DataFrame vazio quando a tab não existe.
  - **`resolve_preco_unit(cliente_id, tamanho_id, qtde)`** — busca em
    Precos a faixa com maior `qtde_min ≤ qtde`; fallback pra
    `Tamanhos.preco_venda`; senão 0.
- `app/pages/8_👥_Clientes.py` — CRUD: form pra novo + data_editor pra
  editar/desativar/excluir. Filtro de inativos opcional.
- `app/pages/9_💰_Vendas.py`:
  - Tab "➕ Nova venda": cliente → tamanho → qtde → preço auto-resolvido
    mas editável → forma pagamento + status. Mostra Total, Custo
    estimado, Lucro estimado em KPIs antes de salvar.
  - Tab "📋 Histórico": tabela com filtros, agregados (vendas/faturamento/lucro).
  - Lucro snapshot é gravado na coluna K (`custo_unit_estimado`) — fiel ao
    custo no momento da venda, não recalculado depois.
- `app/pages/10_💸_Precos.py` — tabela editável de faixas por tamanho ×
  tipo × qtde_min. Adicionar nova com guard contra duplicata.

**Pra subir:**
1. `python scripts/migrate_clientes_vendas.py --apply`
2. Push o código.

**Decisões/defaults usados** (override original do plano):
- Tipo binário B2C/B2B (não segmentação fina) — confirmado.
- `canal` é coluna separada em Vendas (preserva histórico se cliente mudar
  de tipo).
- Lucro via snapshot.
- Cliente B2B comprando abaixo da menor faixa B2B: cai pra B2C (não bloqueia).
- Preço resolvido sempre **editável** na UI (override por venda, não muda
  Precos).

**Pendências conhecidas:**
- Dashboards (ranking por cliente, faturamento mensal): adiados.
- Bot `/venda`: schema suporta, mas comando ainda não existe.
- Edição de venda já gravada: só insere; pra editar/excluir tem que ir no
  Sheet ou via Tabela do app (não implementado).
- Reconciliação Fornadas.qtde_vendida vs Vendas: aceita estarem
  desconectados nesta fase.

## Ordem recomendada de migração (passo-a-passo)

1. **Backup**: snapshot do Sheet inteiro via Google Sheets > Arquivo > Histórico.
2. `python scripts/migrate_produtos_preco_manual.py --apply` (Tema A — colunas G/H em Produtos).
3. `python scripts/migrate_compras_frete.py --apply` (Tema C — colunas L/M em Compras).
4. `python scripts/migrate_clientes_vendas.py --apply` (Tema D — 3 abas novas).
5. Push código: `gh auth switch --user luafdiniz && gh auth setup-git --force --hostname github.com && git push`.
6. Aguardar Streamlit Cloud + Vercel redeploy (~1-2 min cada).
7. Smoke test: abrir Insumos (Origem aparece?), Calculadora (6 presets?),
   Clientes (CLI-000 seed?).
8. Migrar 5 produtos EMB → GRA (`migrate_categoria.py` 5×).
9. Smoke test: abrir Insumos > aba 🖨️ Gráfica.

## Open questions ainda em aberto

- **Tema A:** N=3 ou N=5? Default 3, dá pra trocar `WAC_WINDOW_N`.
- **Tema A:** mostrar banner "override acabou de expirar"? Não implementado, default sem.
- **Tema C:** EMB-005 (FITA) tem impressão ou não?
- **Tema D:** Cliente avulso CLI-000 — manter sempre, ou só criar sob demanda? Por ora criado.
- **Tema E:** margem é sobre preço (atual) ou sobre custo? Atual mantém sobre preço.

## Como retomar
1. `cd ~/ClaudeCode/Caramelo && git pull`
2. Conferir `git log` da branch main pra ver o que já foi mergeado.
3. Próxima sessão: dashboards de Vendas (gráfico, ranking), bot `/venda`,
   ou Tema B (custo operacional kWh).
