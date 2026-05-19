# Tema D — Clientes, Vendas e Preço B2B (com faixas por volume)

> **Status:** plano detalhado, NÃO implementado.
> **Backlog originais:** itens 14 (Clientes), 15 (Preço B2B), 16 (Faixas por volume).
> **Tamanho:** maior tema do backlog — quebrado em 4 fases.

---

## 1. Resumo

Hoje o sistema (Sheets + Streamlit + bot) modela só o lado da **produção**: insumos,
receitas, tamanhos, fornadas, compras. Não tem ideia do que é "cliente" nem de
"venda" como evento individual — Fornadas guarda `qtde_vendida` agregada e o
preço sai de `Tamanhos.preco_venda`, um único valor por SKU.

O Tema D introduz três conceitos novos, que andam juntos:

1. **Clientes** — quem compra. Maior valor está em B2B (mercados, cafés,
   eventos), mas vale catalogar B2C fiel também.
2. **Vendas** — cada transação individual: cliente × tamanho × qtde × preço.
   Isso destrava faturamento por cliente, ranking, e separar caixa de
   produção (Fornadas) do caixa de vendas reais.
3. **Preço B2B com faixas por volume** — atacado paga menos; volumes maiores
   pagam ainda menos. Hoje o `preco_venda` em Tamanhos é único e não suporta
   essa variação.

O sistema vai precisar **resolver** o preço de cada venda dinamicamente
(cliente + tamanho + qtde → preço unitário), mas **gravar** o preço resolvido
no momento da venda (pra preservar histórico mesmo se a tabela mudar depois).

---

## 2. Decisões de schema

### 2.1 Aba `Clientes` (nova)

| Col | Campo | Tipo | Exemplo | Notas |
|-----|-------|------|---------|-------|
| A | `id` | text | `CLI-001` | Prefixo CLI, numeração independente |
| B | `nome` | text | `Padaria do Sô José` | Para B2C, nome da pessoa |
| C | `tipo` | enum | `B2B` ou `B2C` | Ver discussão de granularidade abaixo |
| D | `contato` | text | `31 99999-0000` | WhatsApp/telefone |
| E | `endereco` | text | `Av Cristiano Machado, 1234 - Cidade Nova` | Texto livre, sem geocoding |
| F | `dia_entrega_preferido` | text | `Quinta` | Opcional. Texto livre (não dia da semana fixo) — facilita "fim de mês" ou "quando me ligar" |
| G | `periodicidade` | text | `Semanal` / `Quinzenal` / `Esporádico` | Opcional. Ajuda planejamento de fornadas — não é regra dura |
| H | `observacoes` | text | `Prefere lata, paga no Pix` | Texto livre |
| I | `data_cadastro` | date | `2026-05-19` | Auto-preenchido pelo app |
| J | `ativo` | bool | `TRUE` | Soft-delete: clientes inativos somem dos selectboxes mas histórico permanece |

**Decisão sobre granularidade de `tipo`:** **binário (B2B / B2C), não 4 valores.**

Justificativa:
- Subdivisões tipo "B2B-mercado / B2B-cafe / B2C-fiel / B2C-pontual" são
  classificações que **ela vai querer mudar de ideia depois** (todo cliente
  começa "pontual" e vira "fiel"). Codificar isso em enum congela cedo.
- O caso real onde a divisão importa é **decisão de preço**: B2B paga
  diferente de B2C. Só isso justifica enum.
- Tudo o que é "tipo de B2B" (mercado vs café vs evento) cabe em
  `observacoes` ou numa coluna `segmento` opcional adicionada depois — não
  ataca o problema central, e dá pra refinar quando ela tiver 10+ clientes
  B2B reais e enxergar o padrão.
- Recomendação: ficar binário **mesmo sabendo que vai querer
  refinar**. Adicionar segmentação numa fase futura, quando ela já tiver
  dados pra validar quais segmentos importam.

### 2.2 Aba `Vendas` (nova)

| Col | Campo | Tipo | Exemplo | Notas |
|-----|-------|------|---------|-------|
| A | `id` | text | `VEN-001` | Prefixo VEN |
| B | `data` | date | `2026-05-19` | Data da venda (não da entrega — pode ser igual) |
| C | `cliente_id` | text | `CLI-005` | FK pra Clientes |
| D | `tamanho_id` | text | `TAM-002` | FK pra Tamanhos |
| E | `qtde` | int | `12` | Unidades vendidas nessa transação |
| F | `preco_unit_efetivo` | currency | `28.00` | **Gravado no momento da venda.** Resultado da resolução de preço (B2C, B2B, ou faixa). Não recalcular nunca depois. |
| G | `preco_total` | currency | `336.00` | `qtde × preco_unit_efetivo`. Redundante mas evita 100 fórmulas |
| H | `canal` | text | `B2B` | Cópia do `cliente.tipo` no momento da venda. **Justificativa abaixo.** |
| I | `forma_pagamento` | enum | `Pix` / `Dinheiro` / `Cartão` / `Boleto` / `Fiado` | Texto livre na v1, vira enum depois |
| J | `status` | enum | `entregue` / `pendente` / `cancelada` | Default `entregue` |
| K | `custo_unit_estimado` | currency | `12.50` | **Snapshot do custo unitário no dia da venda.** Ver discussão abaixo |
| L | `notas` | text | `Sem caramelo, alérgica` | Opcional |

**Por que `canal` é coluna separada e não calcula do `cliente_id`:**
- Filtros de dashboard ficam mais simples (`WHERE canal='B2B'` sem JOIN).
- Se a cliente mudar de tipo no futuro (B2C virou B2B), as vendas antigas
  **preservam o canal que tinham na hora**. Mesma lógica de gravar
  `preco_unit_efetivo`.
- Custo: 1 coluna redundante. Aceitável.

**Como rastrear lucro da venda — `custo_unit_estimado` snapshot vs recompute on-the-fly?**

Opção A (snapshot): gravar o `custo_unit` calculado de
`get_tamanho_costs()` na hora da venda, na coluna K.

Opção B (recompute): só guardar `preco_unit_efetivo`, e recalcular custo
on-the-fly quando o dashboard pedir lucro.

**Recomendo Opção A (snapshot).** Razões:
- O custo unitário **muda quando os preços de insumos sobem** (uma compra
  nova faz `latest_unit_price` retornar valor diferente). Se recalcula
  on-the-fly em maio, uma venda de janeiro vai mostrar lucro calculado com
  preço de ovos de maio — historicamente errado.
- Snapshot é fiel ao que ela teve de lucro **naquele dia**.
- Custo: 1 coluna extra, mas só ler nada complica.
- Fornadas já segue esse padrão (`custo_unit` é coluna gravada, não
  derivada).

### 2.3 Preço B2B / faixas por volume

**Opções avaliadas:**

| Opção | Onde mora | Suporta faixas por volume? | Complexidade |
|-------|-----------|----------------------------|--------------|
| 1 — Coluna `preco_b2b` em Tamanhos | Tamanhos!I (ou nova col) | ❌ Só 2 preços por SKU | Trivial |
| 2 — Aba nova `Precos` (tamanho_id, tipo_cliente, qtde_min, preco_unit) | Aba dedicada | ✅ Faixas naturais | Média |
| 3 — Coluna `desconto_padrao_b2b` em Clientes (%) | Clientes!K | ❌ Desconto por cliente, não por SKU nem volume | Média (negocia por cliente) |

**Recomendação: Opção 2 — aba `Precos`.**

Justificativa:
- O item 16 (faixas por volume) **inviabiliza Opção 1**. Não dá pra
  representar "10+ → R$25, 20+ → R$23" com 2 colunas fixas.
- Opção 3 (desconto por cliente) parece atraente mas tem 2 problemas:
  (a) não suporta faixas, (b) força negociar caso a caso — o atacado dela é
  pré-tabelado, não negociado a quente.
- Opção 2 é a única que cobre o caso completo. O custo extra é uma aba a
  mais e uma função de lookup — pouco código.

**Schema da aba `Precos`:**

| Col | Campo | Tipo | Exemplo |
|-----|-------|------|---------|
| A | `tamanho_id` | text | `TAM-002` |
| B | `tipo_cliente` | enum | `B2C` / `B2B` |
| C | `qtde_min` | int | `1` (B2C), `10` (B2B faixa 1), `20` (B2B faixa 2) |
| D | `preco_unit` | currency | `28.00` |
| E | `notas` | text | Opcional |

Regra de leitura: dado `tamanho_id + tipo_cliente + qtde`, escolher a linha
com **maior `qtde_min` que ainda seja ≤ `qtde`**.

Exemplo prático pra TAM-002 (Pudim 500g):
```
TAM-002  B2C   1   30.00       (preço cheio, qualquer qtde)
TAM-002  B2B  10   25.00       (10-19 unidades)
TAM-002  B2B  20   22.00       (20+ unidades)
```

Compradora B2B levando 5 unidades? **Não tem faixa B2B aplicável (qtde_min mais
baixa é 10).** Decisão: cai pra B2C (R$ 30) ou bloqueia? Ver Open Question 3.

### 2.4 Como `Tamanhos.preco_venda` (existente) se encaixa

Hoje a coluna G de Tamanhos guarda **um** preço. Pós-Tema D:

- `Tamanhos.preco_venda` continua existindo **como preço B2C de 1 unidade
  (preço "de balcão")**. Mantém retrocompatibilidade — a Calculadora, a
  página de Tamanhos com KPI de margem, e Fornadas continuam funcionando
  sem mudança.
- A aba `Precos` é um **overlay**: se tem entrada `(tamanho_id, B2C, 1, X)`
  em Precos, ela **vence**. Se não tem, cai pra `Tamanhos.preco_venda`.
- Isso permite migração suave: na Fase 1 só Clientes existe e nada muda.
  Na Fase 2 (Vendas), o resolvedor de preço usa Tamanhos.preco_venda como
  fallback. Na Fase 3 (Precos), passa a usar Precos primeiro, Tamanhos
  como fallback.

---

## 3. Resolução de preço (pseudo-código)

```python
def resolve_preco_unit(cliente_id: str, tamanho_id: str, qtde: int) -> float:
    """
    Retorna o preço unitário efetivo pra uma venda hipotética.
    A regra final, depois das 3 fases, é:
      1. Olha o tipo do cliente (B2C ou B2B).
      2. Procura na aba Precos a faixa aplicável: maior qtde_min <= qtde
         pra esse tamanho + tipo.
      3. Se achou, retorna esse preço.
      4. Se não achou: fallback pra Tamanhos.preco_venda (preço B2C de balcão).
      5. Se nem isso (tamanho sem preço cadastrado), retorna 0 e a UI
         destaca em vermelho — exige preço manual.
    """
    cliente = get_clientes().query(f"id == '{cliente_id}'").iloc[0]
    tipo = cliente["tipo"]  # 'B2C' ou 'B2B'

    # 1. Tenta na aba Precos
    precos = get_precos()  # tamanho_id, tipo_cliente, qtde_min, preco_unit
    candidatos = precos[
        (precos["tamanho_id"] == tamanho_id) &
        (precos["tipo_cliente"] == tipo) &
        (precos["qtde_min"] <= qtde)
    ].sort_values("qtde_min", ascending=False)

    if not candidatos.empty:
        return float(candidatos.iloc[0]["preco_unit"])

    # 2. Fallback: preço B2C de balcão em Tamanhos
    tamanhos = get_tamanhos()
    t = tamanhos[tamanhos["id"] == tamanho_id]
    if not t.empty and pd.notna(t.iloc[0]["preco_venda"]):
        return float(t.iloc[0]["preco_venda"])

    # 3. Sem preço — UI tem que pedir manualmente
    return 0.0
```

**Casos de borda:**

- **Cliente B2B comprando qtde abaixo da menor faixa B2B.** Ex: B2B levando
  5 unid, mas a menor faixa B2B é qtde_min=10. **Decisão (Open Q 3):** cai
  pro preço B2C. Alternativa "bloqueia venda" é hostil — em situações reais
  ela vai querer vender e cobrar o cheio. Documentar.
- **Tamanho sem nenhum preço em lugar nenhum.** Retorna 0. UI mostra campo
  vermelho "Defina o preço". Não deixar salvar com preço 0 (forma de
  consistência).
- **Preço resolvido pode ser sobrescrito manualmente na UI** — o campo é
  pré-preenchido mas editável. Esse override **não** atualiza a tabela
  Precos; só afeta aquela venda específica. Vide UI abaixo.

---

## 4. UI — desenho das páginas

### 4.1 Nova página `app/pages/8_👥_Clientes.py`

Padrão visual: idêntico ao de Insumos (Tabela + Lista por categoria + Novo).

**Estrutura:**
- **Tab 1 — 📋 Tabela:** `st.data_editor` com todos os clientes ativos.
  Colunas: ID (disabled), Nome, Tipo (selectbox B2C/B2B), Contato, Endereço,
  Dia entrega, Periodicidade, Observações, Ativo (checkbox), Excluir
  (checkbox). Botão "💾 Salvar alterações" no fim, mesmo padrão de
  diff+salvamento em lote do Insumos.
- **Tab 2 — 📇 Lista:** filtro por tipo (`B2C` / `B2B` / `Todos`), busca por
  nome, lista de cards. Cada card mostra nome + ID + contato +
  observações + KPI "Total vendido" e "Última compra" (vazios na Fase 1, vão
  preencher na Fase 2).
- **Tab 3 — ➕ Novo cliente:** form expander. Nome (required) + tipo (radio
  B2C/B2B, default B2C) + contato + endereço + observações. `data_cadastro`
  e `ativo` preenchidos automaticamente.

**Soft-delete:** marcar `ativo=FALSE` em vez de deletar a linha. Preserva FKs
de Vendas. Botão "🗑️ Inativar" no card; "✅ Reativar" se já inativo.
Toggle de "Mostrar inativos" no topo da Lista.

### 4.2 Nova página `app/pages/9_💰_Vendas.py`

Estrutura:
- **Tab 1 — 📋 Vendas registradas:** lista cronológica reversa. Cada venda
  vira card: cliente + tamanho + qtde + total + status. Filtros: data
  (slider de período), cliente (selectbox), canal (B2C/B2B), status. Botão
  "Editar" só ajusta `notas` e `status`. **Não permite editar `preco_unit_efetivo`** depois
  de salvo — é histórico. Se errou o preço, deleta a venda e refaz.
- **Tab 2 — ➕ Nova venda:** form vertical (não data_editor — venda é
  evento, não tabela editável).
  1. `Cliente` — selectbox com todos os clientes ativos. Busca embutida do
     Streamlit. Mostra "CLI-005 — Padaria do Sô José (B2B)".
  2. `Tamanho` — selectbox de Tamanhos.
  3. `Qtde` — `number_input`, min 1, step 1.
  4. `Preço unitário` — `number_input` **pré-preenchido com
     `resolve_preco_unit(...)`** mas editável. Caption embaixo: "Preço
     sugerido: R$ X (faixa B2B 10+)". Se editou pra algo diferente, mostra
     warning amarelo "⚠️ Preço diferente da tabela. Salva mesmo assim?".
  5. `Forma de pagamento` — selectbox.
  6. `Status` — radio (entregue/pendente/cancelada), default entregue.
  7. `Data` — date_input, default hoje.
  8. `Notas` — text_area.
  9. **Resumo antes de salvar:** card destacado com total =
     `qtde × preco_unit`, mostra qual faixa foi aplicada, e mostra **lucro
     estimado** (`(preco_unit - custo_unit) × qtde`).
  10. Botão "💾 Registrar venda".

- **Tab 3 — 🗑️ Vendas canceladas:** view simples só de `status=cancelada`,
  pra histórico.

### 4.3 Nova página `app/pages/10_💸_Tabela de Preços.py` (Fase 3)

Edição da aba `Precos`. Padrão idêntico ao de
`Embalagens_Por_Tamanho` no edit form de Tamanhos: `data_editor` simples,
linha por (tamanho_id, tipo_cliente, qtde_min). Pode "Adicionar nova
faixa" via multiselect de tamanhos × tipo + qtde_min + preço.

**Validação ao salvar:** para cada `(tamanho_id, tipo_cliente)`, garantir que
os `qtde_min` sejam únicos. Se a pessoa cadastrar duas faixas com qtde_min=10,
avisar e bloquear save.

**Visualização:** quadro por tamanho mostrando todas as faixas dele,
ordenadas por qtde_min crescente. Ex:

```
TAM-002 — Pudim 500g
  B2C  qtde_min=1     R$ 30,00
  B2B  qtde_min=10    R$ 25,00   (- 17%)
  B2B  qtde_min=20    R$ 22,00   (- 27%)
```

A coluna de desconto é só visual (calculado vs preço B2C de qtde 1) — ajuda
ela a ver se as faixas fazem sentido.

### 4.4 Dashboards (adiados pra fase 5, fora do escopo deste plano)

Faturamento por cliente, ranking, faturamento mensal, lucro por canal.
**Não desenhar agora.** Esquema acima já suporta — é só agregação no
momento.

---

## 5. Interação com schema existente

| Schema antigo | Mudança | Compatibilidade |
|---------------|---------|------------------|
| `Tamanhos.preco_venda` | Continua. Vira "preço B2C de balcão" (preço default quando não tem entrada em Precos) | Total — nada quebra |
| `Tamanhos` outras colunas | Sem mudança | Total |
| `Fornadas.qtde_vendida` / `preco_venda_unit` | Continua existindo paralelamente | **Discussão:** Fornadas vira agregação ou some? Ver Open Q 5 |
| `Calculadora` | Continua usando `Tamanhos.preco_venda`. Pode ganhar tab "Simular preço B2B" depois | Total |
| `Compras`, `Receitas`, `Produtos`, `Fornecedores` | Zero impacto | Total |

**Preço gravado na Venda vs tabela mutável:** quando ela mudar a tabela de
Precos depois (ex: subir B2B 20+ de R$22 pra R$23), **vendas antigas não
são afetadas** porque `preco_unit_efetivo` foi snapshot em Vendas!F. Esse é
o ponto central. Mesma lógica vale pra `custo_unit_estimado` na K.

---

## 6. Bot Telegram — esboço do `/venda` (Fase 4)

**Não implementar na Fase 1-3.** Só rascunho pra confirmar que o schema
suporta.

Fluxo (cópia mental do `/compra` em `bot/lib/orchestrator.py:1301+`):

```
USUÁRIO: /venda

BOT: 💰 Registrar uma venda. Pra qual cliente?
     [CLI-001 — João da Padaria]
     [CLI-002 — Café da Esquina]
     [CLI-005 — Padaria do Sô José]
     ... (filtra ativos, ordena por última venda)
     [❌ Cancelar]

USUÁRIO: clica CLI-005

BOT: ✓ Cliente: Padaria do Sô José (B2B)
     Qual tamanho?
     [TAM-001 — Pudim 200g]
     [TAM-002 — Pudim 500g]
     [TAM-003 — Pudim 1kg]
     [← Voltar]

USUÁRIO: clica TAM-002

BOT: ✓ Tamanho: Pudim 500g
     Quantas unidades?
     (digite o número)

USUÁRIO: 15

BOT: 💰 Confirma a venda?
     Cliente: Padaria do Sô José (B2B)
     Tamanho: Pudim 500g
     Qtde: 15
     Preço unit: R$ 25,00 (faixa B2B 10+)
     Total: R$ 375,00
     Forma de pagamento: Pix (padrão)
     [✅ Salvar] [💸 Mudar preço] [💳 Mudar pagamento] [❌ Cancelar]

USUÁRIO: clica ✅ Salvar

BOT: ✅ Venda VEN-042 registrada.
     Faturamento de hoje: R$ 590,00 (3 vendas).
```

**Como esse fluxo encaixa no orchestrator:**
- Novo `start_venda_flow(chat_id)` análogo a `start_compra_flow`.
- Estados: `cliente` → `tamanho` → `qtde` → `confirm` → `save`.
- A resolução de preço é a mesma função `resolve_preco_unit` que o app
  Streamlit usa — fica em `app/lib/data.py` (ou novo `app/lib/pricing.py`)
  e o bot a importa. **Schema da Venda permite isso** porque
  `preco_unit_efetivo` aceita qualquer valor (resolvido ou manualmente
  setado).
- Forma de pagamento e status: defaults sensatos (Pix, entregue), botões
  pra mudar.

---

## 7. Fases de implementação

### Fase 1 — Schema `Clientes` + página Clientes (CRUD)

**Escopo:**
- Criar aba `Clientes` na planilha (manual ou script).
- Adicionar `get_clientes()` em `app/lib/data.py` (mesmo padrão de
  `get_produtos`, cache 30s).
- Adicionar `create_cliente`, `update_cliente_row` em `bot/lib/sheets.py`
  (mesmo padrão de `create_produto`).
- Adicionar `_next_id_for_prefix(..., "CLI")` — já existe genérico em
  sheets.py, só usar.
- Criar `app/pages/8_👥_Clientes.py` (data_editor padrão Insumos).
- Soft-delete via coluna `ativo`.

**Sem dependências.** Pode rodar standalone — Clientes existe na planilha
mas ninguém referencia ele ainda. **Quebra zero.**

**Estimativa:** 1 sessão. ~200 linhas de Python.

### Fase 2 — Schema `Vendas` + página Vendas + resolução de preço B2C simples

**Escopo:**
- Criar aba `Vendas` na planilha.
- Adicionar `get_vendas()`, `create_venda`, `update_venda` no data layer.
- Implementar `resolve_preco_unit(cliente_id, tamanho_id, qtde)` —
  **mas sem aba Precos ainda.** Nesta fase a função só faz fallback pra
  `Tamanhos.preco_venda`, e respeita uma coluna nova
  `Tamanhos.preco_venda_b2b` (sim — voltei pra Opção 1 simplificada
  **apenas como degrau**) ou usa preço único pra ambos os tipos.
  - **Recomendação:** começar com **um único `preco_venda`** pra ambos os
    tipos nesta fase. Resolve_preco_unit retorna esse valor independente
    do tipo. Ela registra vendas, valida o fluxo, e na Fase 3 a aba Precos
    entra e o resolver passa a usar tipo+qtde.
  - **Por que esse degrau:** entrega valor imediato (ela consegue
    registrar vendas e ver faturamento) sem bloquear na complexidade de
    faixas. Faixas é o doce pro café — Vendas funcionando já mata 80% do
    item 14+15.
- Criar `app/pages/9_💰_Vendas.py`.
- Snapshot de `custo_unit_estimado` no save da venda.

**Dependências:** Fase 1.

**Estimativa:** 1-2 sessões. ~400 linhas (UI + data + tests).

### Fase 3 — Aba `Precos` + faixas por volume (item 16)

**Escopo:**
- Criar aba `Precos` na planilha.
- Adicionar `get_precos()` no data layer.
- Substituir o resolver da Fase 2 pelo resolver real (faixas).
- Criar `app/pages/10_💸_Tabela de Preços.py`.
- Validar unicidade de `(tamanho_id, tipo_cliente, qtde_min)`.
- Migrar dados: pra cada Tamanho existente, criar linha
  `(tamanho_id, B2C, 1, preco_venda)` em Precos (1 vez, script).

**Dependências:** Fase 2.

**Estimativa:** 1 sessão. ~200 linhas.

### Fase 4 — Bot `/venda` (item 14 via bot)

**Escopo:**
- Adicionar `start_venda_flow` ao orchestrator.
- Estados no payload: cliente, tamanho, qtde, preco_unit, forma_pgto.
- Reuso de `resolve_preco_unit` (passar do app pra um módulo
  compartilhado — `shared/pricing.py`? ou direto em `bot/lib/sheets.py`
  espelhando a função? **Decisão:** copiar a função pro bot/lib mesmo. O
  duplicate é 30 linhas, evita criar um módulo shared/ novo que vira
  burocracia. Quando a função mudar (3ª vez), aí cria o shared.).
- Bot escreve em `Vendas` igual o app.

**Dependências:** Fase 3 (pra ter resolução de preço completa).

**Estimativa:** 1 sessão. ~300 linhas no orchestrator.

### Fase 5 — Dashboards (fora do escopo deste plan)

Faturamento por cliente, ranking, lucro mensal por canal. Vira plan
próprio quando Fase 1-4 estiverem rodando e a Luiza tiver feedback de uso.

---

## 8. Open questions pra Luiza

1. **Granularidade de `tipo`:** confirmar B2B/B2C binário, ou ela já sabe
   que quer mais? (Minha aposta: binário agora, segmento depois quando
   tiver 10+ clientes.)

2. **Soft-delete vs hard-delete de Clientes:** ok inativar (preserva
   histórico de Vendas)? Ou ela prefere apagar mesmo e perder FKs?
   (Minha aposta: soft-delete, é padrão B2B.)

3. **B2B com qtde abaixo da menor faixa:** ex, cliente B2B compra 3 unid
   mas menor faixa B2B é 10. Cai pro preço B2C ou bloqueia? (Minha aposta:
   cai pro B2C, com warning visual.)

4. **Editar preço de venda salva:** uma vez salva uma venda, dá pra editar
   o preço unitário depois? (Minha aposta: **não**. Editável só
   status+notas. Erro → cancela venda e refaz.)

5. **Fornadas.qtde_vendida vs Vendas:** depois das fases, vão coexistir
   ou Fornadas vira só "produção"? (Minha aposta: **coexistem na v1**.
   Fornadas continua medindo produção/cortesia. Vendas substitui o
   conceito de "faturamento". A coluna `qtde_vendida` em Fornadas vira
   derivada — soma de Vendas pra aquele tamanho na janela da fornada —
   ou cai numa fase futura.)

6. **Endereço:** texto livre é suficiente, ou já quer pensar em
   geocoding/rota de entrega? (Minha aposta: texto livre na v1. Rota de
   entrega vira plan próprio se virar dor.)

7. **Forma de pagamento "Fiado":** se ela tem cliente que paga depois,
   `status=pendente` + `forma_pagamento=Fiado` já cobre, ou precisa de
   coluna `data_pagamento`? (Minha aposta: cobre na v1; `data_pagamento`
   vira coluna se ela começar a perder visibilidade de quem deve.)

8. **Migração inicial de Tamanhos.preco_venda → Precos:** rodar script
   automático na Fase 3 ou ela quer revisar manualmente cada preço B2C
   na hora da migração? (Minha aposta: script automático, com `dry-run`
   e log do que foi migrado. Padrão Caramelo.)

9. **Cliente "Avulso" / "Balcão":** pra venda B2C que não vai catalogar
   (ex: vendeu 1 pudim no evento pra desconhecido), criar um
   `CLI-000 — Cliente Avulso` permanente? Ou exigir cadastro a cada
   venda? (Minha aposta: `CLI-000` permanente. Senão vai virar 200
   "João Silva" duplicados.)

---

## 9. Riscos e gotchas

- **Performance do resolver:** se Precos crescer pra 100+ linhas, fazer
  `df.query` em cada save de venda fica caro. Solução: cache_data de 30s
  no `get_precos` (mesmo padrão dos outros) — já resolve.
- **Snapshot de custo unitário:** depende de `get_tamanho_costs` que por
  sua vez depende de Compras + Receitas. Se rodar com receita vazia,
  `custo_unit` sai 0. Aceitar e mostrar "?" no resumo.
- **Cliente deletado com Vendas:** garantir que o soft-delete não permita
  hard-delete enquanto houver Vendas referenciando o `cliente_id`. UI
  bloqueia, igual Insumos bloqueia delete quando tem Compras.
- **Sheets locale pt_BR:** todas as fórmulas usam `;` como separador.
  Validações de qtde_min usar `>=` literal não fórmula — evitar.
- **IDs do bot:** `_next_id_for_prefix` faz scan da coluna A inteira. Pra
  Vendas que vai crescer rápido (mais que Compras), aceitável até ~5000
  linhas. Reotimizar depois se virar dor.
