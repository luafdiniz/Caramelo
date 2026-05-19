# Tema A — Custo dinâmico de insumos + edição manual sem Compra fantasma

> Plano de design para resolver os itens **6** (variação automática do custo
> da receita quando entra Compra nova) e **9** (editar preço de um insumo
> sem criar Compra "Ajuste manual de preço").
>
> **Não implementa código** — só descreve a estratégia, schema e UX.

---

## TL;DR — recomendação

Adotar **média ponderada por quantidade das últimas N compras** (N=3, por
produto) computada on-the-fly em `app/lib/data.py`, **com override manual
opcional** (colunas novas `preco_manual` + `preco_manual_data` na aba
Produtos) que **expira automaticamente na próxima Compra registrada** do
mesmo produto. Sem coluna de "custo atual" persistida na planilha — o custo
continua derivado, mas a função `latest_unit_price` vira `current_unit_price`
e encapsula a regra (override → média ponderada → última compra → 0). Isso
elimina as Compras-fantasma do item 9, suaviza picos de preço esporádicos
(uma compra de emergência em mercadinho caro não pula o custo do pudim
inteiro) e, ao mesmo tempo, mantém o custo reagindo a mudanças reais
(uma nova compra reduz o peso do preço antigo no rolling).

---

## Pesquisa — estratégias comparadas

Foram avaliadas seis estratégias clássicas de custeio de insumo aplicáveis a
um pequeno negócio artesanal em Sheets. Resumo das fontes consultadas no
final desta seção.

### 1. Última compra (estado atual)

- **O que é:** o `preco_unitario` da Compra mais recente vira o custo do
  insumo.
- **Prós:** trivial de implementar (1 linha de SQL/pandas), reflete o
  preço de reposição no momento.
- **Contras:** **volátil**. Uma compra emergencial num mercadinho caro
  (e.g. 12 ovos a R$ 18 num domingo) muda o custo do pudim inteiro até a
  próxima compra normal. Não diferencia outlier de tendência.
- **Sheets:** já está em produção (`latest_unit_price` em
  `app/lib/data.py:362`).
- **Robustez com compras irregulares:** baixa — quanto maior o intervalo
  entre compras, mais tempo um outlier domina o cálculo.

### 2. Média simples de TODAS as compras

- **O que é:** média aritmética de todos os `preco_unitario` históricos do
  produto.
- **Prós:** muito estável, suaviza outliers.
- **Contras:** **lenta pra reagir a tendências reais**. Se ovo subiu 40%
  ano passado e fica nesse patamar, a média ainda carrega o preço antigo
  por muito tempo. Compras antigas podem nem refletir o produto atual
  (marca trocada, embalagem mudou).
- **Sheets:** trivial (`AVERAGEIF`).
- **Robustez:** baixa pra negócio em crescimento; alta pra commodity
  estável.

### 3. Média ponderada por quantidade — TODAS as compras (Weighted Average Cost / WAC)

- **O que é:** `Σ(preço × qtde) / Σ(qtde)` sobre todo o histórico do
  produto.
- **Prós:** padrão contábil aceito mundialmente para pequenos negócios
  ([Craftybase](https://craftybase.com/blog/what-is-the-weighted-average-cost-method),
  [Finale](https://www.finaleinventory.com/accounting-and-inventory-software/inventory-costing-methods)).
  Uma compra grande pesa mais que uma pequena — o que faz sentido pra
  custo unitário do que efetivamente está sendo usado.
- **Contras:** carrega o histórico inteiro indefinidamente — uma caixa
  grande de açúcar de 2024 ainda influencia 2026. Pra Caramelo isso é
  ruim porque hoje a Luiza compra _ovos_ em volumes muito diferentes
  (caixa de 30 vs. cartela de 12) e o produto físico muda menos do que o
  produto comercial (marca, qualidade).
- **Sheets:** `SUMPRODUCT(qtde, preco) / SUM(qtde)` por produto. Fácil.
- **Robustez:** alta pra valor contábil de inventário; média pra preço
  de reposição.

### 4. Média ponderada das últimas N compras (Moving Weighted Average)

- **O que é:** WAC restrito às N compras mais recentes (e.g. N=3 ou N=5)
  daquele produto.
- **Prós:** combina suavização de outlier (uma compra cara não domina)
  com reatividade a tendências (passa o tempo, compras antigas saem da
  janela). Cada nova Compra automaticamente desloca a média —
  exatamente o comportamento que o item 6 pede.
- **Contras:** escolha de N é arbitrária. Se N for muito grande perto da
  frequência de compra, vira igual ao WAC total. Se N=1 vira igual à
  última compra. **N=3 é o sweet-spot pra compras quinzenais/mensais
  irregulares**.
- **Sheets:** dá pra fazer com `QUERY` + `ORDER BY data DESC LIMIT N`,
  mas é feio. Em Python (`pandas.sort_values`+`head(N)`) é trivial.
- **Robustez:** **alta** pra contexto de Caramelo. Compra emergencial
  vira 1/3 do peso e some depois de 3 compras normais.

### 5. FIFO (First-In, First-Out)

- **O que é:** o custo de cada unidade consumida é o preço da Compra
  mais antiga ainda com saldo positivo. Requer modelar **consumo**
  (saídas), não só compras.
- **Prós:** padrão contábil ideal pra perecíveis
  ([Finale](https://www.finaleinventory.com/accounting-and-inventory-software/inventory-costing-methods)).
  Reflete bem o fluxo físico (insumo velho é gasto primeiro).
- **Contras:** **exige rastrear estoque consumido por fornada**. Hoje
  Caramelo tem apenas Compras (entradas) — não há saídas. Implementar
  FIFO sem o item "Estoque com baixa por consumo" (adiado em
  [future-ideas.md](./future-ideas.md)) é inconsistente.
- **Sheets:** difícil. Precisa de tabela auxiliar de "lotes" com saldo
  decrescente.
- **Robustez:** alta — mas só vale a pena se o estoque real for
  rastreado.

### 6. LIFO (Last-In, First-Out)

- **O que é:** custo da Compra mais recente é consumido primeiro.
- **Prós:** quase nenhum no contexto.
- **Contras:** **proibido fora dos EUA**
  ([Craftybase](https://craftybase.com/blog/fifo-lifo-and-weighted-average-cost-methods)).
  Não faz sentido físico pra perecíveis. Descartado.

### Fontes consultadas

- Craftybase — "FIFO vs LIFO vs Weighted Average Cost — Which Method Should
  Handmade Sellers Use?" (https://craftybase.com/blog/fifo-lifo-and-weighted-average-cost-methods)
- Craftybase — "What is the Weighted Average Cost Method?"
  (https://craftybase.com/blog/what-is-the-weighted-average-cost-method)
- Finale Inventory — "Inventory Costing Methods: Complete Guide"
  (https://www.finaleinventory.com/accounting-and-inventory-software/inventory-costing-methods)
- IFRS Community — "Cost Formulas for Inventories (FIFO) IAS 2"
  (https://ifrscommunity.com/knowledge-base/fifo-lifo-weighted-average-cost/)
- Restroworks — "Recipe Costing Example" (recipe costing aceita tanto WAC
  quanto última invoice como base).
- McKinsey — "Recipe for success for sourcing in the food industry"
  (volatilidade real de commodities, hedge via formulação flexível —
  contexto mas não aplicável ao nosso porte).

---

## Decisão e justificativa

**Estratégia escolhida: Moving Weighted Average com N=3 + override manual
expirável.**

Por quê:

- **N=3** é grande o suficiente pra absorver uma compra emergencial cara
  (vira ≤ 33% do peso) e pequeno o suficiente pra esquecer compras de 6+
  meses atrás. Pra ovo (compra quase quinzenal) cobre ~6 semanas — bom
  proxy de preço atual. Pra produtos comprados raramente (e.g. fita de
  cetim), N=3 acaba englobando o histórico quase inteiro, o que está
  certo: pra produtos baratos com baixa rotação, estabilidade ganha de
  reatividade.
- **Ponderada por qtde** (não simples) porque uma compra de 30 ovos a
  R$ 0,40 deve pesar mais que uma compra de 6 ovos a R$ 0,80 — refletir
  o quanto cada compra realmente representa do estoque.
- **Override manual expirável** porque a Luiza precisa, de vez em quando,
  corrigir o preço sem comprar (e.g. promoção que ela viu mas não comprou
  ainda, ou erro de digitação numa Compra antiga que ela não quer
  re-editar). O override sobrescreve a média até a próxima Compra real
  daquele produto entrar — aí volta sozinho a obedecer o algoritmo. Isso
  evita as Compras-fantasma e mantém o sistema auto-corrigindo.
- **Sem rastreio de consumo** — não exige modelar saídas/estoque (item
  adiado em [future-ideas.md](./future-ideas.md)). Mantém o escopo
  pequeno.

Single-user em Sheets, sem auditoria fiscal, com compras irregulares:
moving weighted average é o método mais estável e simples que cobre os
dois casos sem inventar abstrações.

---

## Schema changes (Sheets)

### Aba `Produtos` — duas colunas novas

| Col | Nome | Tipo | Exemplo | Notas |
|-----|------|------|---------|-------|
| A | ID | text | `ALI-001` | (existente) |
| B | Nome | text | `LEITE CONDENSADO 395G` | (existente) |
| C | Unidade | text | `UN` | (existente) |
| D | Notas | text | `Usado na calda` | (existente) |
| E | Relacionados | text | `LC, LECO` | (existente) |
| F | Marca_padrao | text | `MOÇA` | (existente) |
| **G** | **Preco_manual** | **number** | **`3.85`** | **NOVO. Override de preço unitário. Vazio = sem override.** |
| **H** | **Preco_manual_data** | **date** | **`2026-05-19`** | **NOVO. Quando o override foi definido. Vazio = sem override. Usada pra detectar "Compra mais nova que o override → expira override".** |

**Por que duas colunas e não uma só:** precisamos saber **quando** o override
foi salvo pra comparar com a data da Compra mais recente. Sem a data, não
dá pra implementar a regra de expiração.

### Aba `Compras` — sem mudança

Permanece exatamente como está. Compras geradas pelo bot e pela página
Compras continuam idênticas. **Some uma única coisa**: o
"Ajuste manual de preço" deixa de ser criado pela página Insumos.

---

## Mudanças em `app/lib/data.py`

### Renomear / refatorar `latest_unit_price` → `current_unit_price`

A função pública nova encapsula toda a regra. Os outros lugares que hoje
chamam `latest_unit_price` (em `calc_custo_alimento_unid`,
`calc_custo_embalagem_unid` e na página Insumos pra montar a coluna "Preço
atual" da Tabela) passam a chamar a nova função sem se preocupar com a
estratégia.

```python
# pseudo-code, not for committing
def current_unit_price(produto_id, *, compras=None, produtos=None) -> float:
    """
    Resolved unit price for a produto, applying (in order):

      1. Manual override (Produtos.preco_manual) IF it is more recent than
         the most recent Compra of this produto. Otherwise the override is
         considered EXPIRED — fall through.
      2. Weighted average of the last 3 compras (by data DESC), weighted
         by total_unidades.
      3. If there are < 3 compras, weighted average over whatever exists.
      4. Zero if no compras and no override.
    """
    # ... implementation reads:
    #   - produtos[produto_id].preco_manual
    #   - produtos[produto_id].preco_manual_data
    #   - last 3 compras of produto_id sorted by data DESC
    # Returns a float. Never raises — defaults to 0.
```

### Helper privado: `_weighted_avg_last_n`

Função pura que recebe um DataFrame de Compras já filtrado por
`produto_id` e ordenado, e retorna `Σ(preco_unit × total_unid) / Σ(total_unid)`
das N primeiras linhas. N default = 3, mas exposto como argumento pra
permitir tunar depois sem refatorar.

### `latest_unit_price` deprecado mas mantido

Mantém a função antiga como **alias** chamando `current_unit_price` por
compatibilidade temporária — algumas chamadas espalhadas na app talvez
não sejam migradas no mesmo PR. Marca com docstring de deprecation. Apaga
depois que todas as chamadas migrarem.

### `calc_custo_alimento_unid` — quase nenhuma mudança

Hoje:

```python
breakdown["preco_unit_atual"] = breakdown["produto_id"].apply(
    lambda p: latest_unit_price(p, compras)
)
```

Vira:

```python
breakdown["preco_unit_atual"] = breakdown["produto_id"].apply(
    lambda p: current_unit_price(p, compras=compras, produtos=produtos)
)
```

O nome da coluna no breakdown (`preco_unit_atual`) continua igual —
display na UI não muda. Mesma assinatura, comportamento mais robusto.

### `calc_custo_embalagem_unid` — mesma mudança

Idem. Uma linha alterada.

### Cache

A função fica embaixo do mesmo `@st.cache_data(ttl=CACHE_TTL_SECONDS)` por
proxy — ela é chamada dentro de funções já cacheadas
(`get_tamanho_costs`, `calc_custo_*`). Não precisa cache próprio.

---

## UI — página Insumos (item 9)

### Mudança no campo "Preço atual" da Tabela

**Antes:** editar "Preço atual" cria uma linha em Compras chamada
"Ajuste manual de preço".

**Depois:** editar "Preço atual" grava em `Produtos.preco_manual` +
`Produtos.preco_manual_data = hoje`. Não toca em Compras.

### Coluna `Preço atual` — mostrar quando é override

Quando `preco_manual` está preenchido E ainda não expirou (i.e. não há
Compra mais nova que ele), o valor mostrado é o override. Adicionar um
indicador visual — ícone `✋` à esquerda do valor, ou tooltip
"Override manual desde DD/MM/YYYY — vai expirar na próxima Compra deste
insumo".

Como o `st.data_editor` não permite formatação condicional rica, a opção
prática é: adicionar **uma coluna `Origem` pequena** (não editável) com
3 valores possíveis:

- `📊 Média` — custo veio do moving weighted average
- `✋ Manual` — custo veio do override ainda ativo
- `—` — sem compras nem override

### Botão "Limpar override" no card da Lista

Na visão de **cards por categoria** (Lista), quando o produto tem override
ativo, mostrar abaixo do KPI "Preço atual" um botão pequeno:
`✋ Override manual desde DD/MM — limpar`. Click → zera as duas colunas e
volta a calcular pela média. Confirmação inline igual aos outros deletes
da página.

Não precisa botão na Tabela — quem quiser limpar override **edita a célula
pra vazio** e salva. O diff já cobre.

### Texto de ajuda atualizado

O `help=` da coluna "Preço atual" hoje diz:

> "Edite para registrar uma Compra de ajuste manual (qtde 1, fornecedor =
> o da última compra deste insumo)."

Atualizar pra:

> "Override de preço. Salva direto no insumo (não cria Compra). Expira
> automaticamente quando uma Compra mais nova entrar."

### Fluxo de save da Tabela — `price_updates`

Hoje (linhas 535-547 de `2_📦_Insumos.py`):

```python
for pu in price_updates:
    data._sheets.append_compra(
        spreadsheet_id, data=date.today()..., notas="Ajuste manual de preço", ...
    )
```

Vira:

```python
# pseudo-code
for pu in price_updates:
    row_num = data.find_row_by_id("Produtos", pu["produto_id"])
    service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=f"Produtos!G{row_num}:H{row_num}",
        valueInputOption="USER_ENTERED",
        body={"values": [[pu["preco"], date.today().isoformat()]]},
    ).execute()
```

Para o caso de "Preço atual" ser **apagado** (célula vazia), o diff
detecta `new_preco is None and orig_preco is not None`: grava `["", ""]`
em `G:H` (limpa override).

---

## Migração — script `scripts/migrate_produtos_preco_manual.py`

Operação one-shot, idempotente, com flag `--apply`:

1. Lê metadata da aba `Produtos` (`spreadsheets().get()`).
2. Verifica se já tem 8 colunas. Se sim, exit.
3. `batchUpdate` adiciona duas colunas em branco depois da F. Headers:
   `Preco_manual` (G) e `Preco_manual_data` (H).
4. **Não faz backfill.** Override começa todo vazio — a função
   `current_unit_price` segue calculando do histórico de Compras. Sem
   risco de regredir nada.
5. Dry-run loga "vai adicionar colunas G/H em Produtos com headers X/Y".

Sem outras migrations:
- Compras antigas com nota "Ajuste manual de preço" **ficam** na planilha
  (são histórico real do que foi tentado). Decidir depois se a Luiza quer
  limpá-las — script `scripts/cleanup_ajustes_manuais.py` separado, opt-in.

---

## Casos de borda — comportamentos previstos

| Cenário | Comportamento esperado |
|---------|------------------------|
| Produto sem nenhuma Compra, sem override | `current_unit_price` retorna 0.0 (idêntico a hoje) |
| Produto com 1 Compra, sem override | Custo = preço dessa única Compra (WAC com 1 ponto) |
| Produto com 2 Compras | WAC das 2 — não espera ter 3 |
| Produto com 5 Compras | WAC das 3 mais recentes |
| Produto com 3 Compras + override | Override vale enquanto `preco_manual_data > MAX(Compras.data)` |
| Override é salvo, depois entra Compra nova mais recente | Override automaticamente "expira" — `current_unit_price` volta a usar WAC. **Não apaga as colunas G/H** — fica como histórico. Na próxima edição do produto, se a Luiza re-salvar o mesmo preço, a data atualiza e ativa de novo (raramente útil; documentar mas não otimizar) |
| Luiza limpa override pela UI (botão "Limpar override") | G/H zeradas → custo volta pra WAC imediatamente |
| Bot registra uma Compra via Telegram | Sem mudança — append_compra continua escrevendo só na aba Compras. Próximo refresh da app, `current_unit_price` já considera essa Compra na janela de 3 |
| Compra antiga é deletada da aba Compras (raro) | WAC é recalculada — janela move pra incluir a próxima mais antiga. Sem efeito colateral |
| Compra é editada (preco_unitario muda) | Idem — WAC recalcula |

---

## Open questions pra Luiza decidir

1. **N=3 ou N=5?** Recomendação é 3 (mais reativo). 5 dá mais
   estabilidade mas atrasa mudanças de tendência. **Não bloqueia** — N
   fica como parâmetro de função, dá pra trocar depois sem refatorar.
2. **Override deve mostrar um aviso "está expirando em breve"?** Por
   exemplo, quando entra Compra nova mais recente que `preco_manual_data`,
   a UI poderia mostrar um banner "Seu override de R$ X.XX em ALI-001
   acabou de expirar — o custo agora segue a média". Útil ou ruído?
3. **Botão "Limpar override" também na Tabela?** A proposta atual é só
   editar a célula pra vazio. Adicionar um botão dedicado complica a UI
   da Tabela mas explicita a ação. **Default: não adicionar — manter
   minimalismo.**
4. **Migrar histórico de "Ajuste manual de preço"?** Pra não ficar
   sujeira na aba Compras, vale rodar um one-off pra deletar todas as
   Compras com notas exatamente igual a "Ajuste manual de preço"? Risco:
   uma dessas pode estar refletindo uma compra real cuja única
   anotação ficou errada. **Default: não fazer — Luiza decide caso a
   caso.**
5. **Receitas calda vs. massa — alguma diferença?** Não. A estratégia é
   por produto, indiferente do componente onde o produto é usado.
6. **Bot pode escrever override?** Não vejo razão. Bot só registra
   Compras reais. Override é decisão consciente da operadora.

---

## Resumo de impacto

- **Arquivos alterados:** `app/lib/data.py` (1 função nova, 2 chamadas
  trocadas), `app/pages/2_📦_Insumos.py` (fluxo `price_updates` no save
  da Tabela; novo botão "Limpar override" nos cards da Lista; coluna
  `Origem` na Tabela).
- **Arquivos novos:** `scripts/migrate_produtos_preco_manual.py`.
- **Aba alterada:** `Produtos` ganha 2 colunas (G, H). `Compras` intacta.
- **Não-regressão:** `latest_unit_price` mantida como alias por algumas
  versões. `calc_custo_alimento_unid` mantém assinatura. Páginas
  Tamanhos, Receitas e Calculadora seguem funcionando sem alteração.
- **Risco:** baixo. Override expira sozinho — falha do override no pior
  caso volta ao comportamento atual (custo derivado de Compras).
