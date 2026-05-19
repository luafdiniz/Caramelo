# Tema C — Frete/desconto rateado + categoria GRA- (gráfica)

> Plano. Nada de código aqui — só decisões, fórmulas, e a lista do que precisa
> mudar. Itens 7 e 8 do roadmap.

## Resumo

Dois problemas independentes que viajam juntos porque ambos mexem em Compras
e na taxonomia de produtos:

1. **Item 7 — Frete e desconto rateados.** Hoje uma Compra com 10 itens da
   feira não carrega o frete (ou um desconto no total) — então o `preco_unitario`
   salvo subestima/super-estima o custo real. Precisa diluir esses valores
   nos itens daquela Compra antes de gravar.

2. **Item 8 — Nova categoria `GRA-` (gráfica).** Hoje `EMB-` mistura embalagem
   física (potes, sacolas, lacres, fitas) com material impresso em gráfica
   (adesivos, etiquetas, papel impresso). Decisão da dona: *"tudo que for
   adesivo, etiqueta, que é impresso na gráfica, vai morar aí dentro dessa
   nova categoria GRA-"*. Separar evita inflar o custo de embalagem com
   gastos que na real são de comunicação visual / marca.

---

## Item 7 — Frete e desconto rateados

### Schema

Adicionar **duas colunas na tab `Compras`**:

| col | nome | tipo | nota |
|-----|------|------|------|
| L   | `frete`    | número | total de frete/taxa de entrega da Compra |
| M   | `desconto` | número | total de desconto aplicado à Compra (positivo) |

Vazias = 0. Coluna nova, não reordena nada. `app/lib/data.py::get_compras`
já lê com `range="Compras!A2:K"` — passa pra `A2:M` e adiciona as colunas
em `cols`.

**Frete e desconto são por Compra, não por item.** Faz sentido:

- O recibo da feira/atacado vem com **um valor de frete** total e **um
  desconto** total, independente de quantos itens estão na nota.
- Manter por-item exigiria a usuária ratear na cabeça antes de inserir.
  O ponto do rateio é exatamente o oposto: ela informa o total, o sistema
  distribui.
- Hoje uma "Compra" no schema é uma **linha por item** (cada item da nota
  vira uma row em Compras, todas com a mesma data/fornecedor). Não existe
  ainda o conceito de "header" da compra agrupando linhas. Duas opções:

  - **Opção A (escolhida): repetir `frete` e `desconto` em TODAS as linhas
    daquela compra.** Redundante, mas o schema atual de Compras já é flat
    e isso evita criar uma tab `Compras_Header` nova. O rateio acontece
    no momento da gravação — depois disso, `preco_unitario` já reflete o
    rateio, então as colunas `frete`/`desconto` viram só auditoria.
  - **Opção B (descartada por enquanto): nova tab `Compras_Sessao`** com
    `id_sessao`, `data`, `fornecedor_id`, `frete`, `desconto`, `total_nota`,
    e adicionar `sessao_id` em Compras. Mais limpo, mais trabalhoso, e a
    UI não tem como atualmente exibir "sessões". Adiar.

Atualizar `CLAUDE.md` mentalmente: a tab Compras passa a ter 13 colunas
(A–M), com `frete` e `desconto` opcionais — vazio = 0.

### Algoritmo de rateio

Fórmula proposta pela dona, confirmada:

```
ajuste_total = frete - desconto                 # pode ser negativo
subtotal     = sum(preco_total_item for item in itens_da_compra)

para cada item:
    if subtotal > 0:
        peso = item.preco_total / subtotal
    else:
        peso = 1 / n_itens                       # rateio igualitário
    ajuste_item = ajuste_total * peso
    preco_total_efetivo = item.preco_total + ajuste_item
    preco_unitario_efetivo = preco_total_efetivo / item.total_unidades
```

**Justificativa:** ratear por `preco_total` é o padrão fiscal brasileiro
de rateio de frete em NF — quem comprou mais (em R$) absorve mais frete.
Alternativa por quantidade física não funciona porque os itens têm unidades
diferentes (KG, UN, L, FOLHA).

**O que vai gravado em Compras:** o **`preco_unitario` efetivo (já com
rateio)**. Razões:

- `latest_unit_price()` em `app/lib/data.py` simplesmente lê `preco_unitario`
  da última Compra do produto. Se gravarmos o valor bruto, o custo dinâmico
  de receita/embalagem fica subestimado — exatamente o bug que estamos
  consertando.
- A coluna `preco_total` também passa a refletir o efetivo (rateado), pra
  manter a invariante `preco_unitario = preco_total / total_unidades` que
  a fórmula `=IF(H>0;I/H;0)` na coluna J já espera.
- O bruto fica recuperável: `preco_bruto = preco_total - (frete - desconto) * peso`,
  e `frete`/`desconto` ficam visíveis na linha pra auditoria.

**Edge cases:**

| caso | comportamento |
|------|---------------|
| Compra com 1 item só | `peso = 1.0`, ajuste 100% no item. Funciona sem mudanças. |
| `subtotal = 0` (todos itens com preço 0 — improvável mas possível em brindes) | rateio igualitário (`1/n`). |
| `desconto > subtotal + frete` (resultado negativo no preço efetivo) | **abortar** o save com erro pra usuária revisar. Mais seguro que clampar a 0 — preço negativo geralmente é erro de digitação. Mensagem: *"Desconto (R$ X) maior que o total da compra (R$ Y). Confere os valores."* |
| Item com `total_unidades = 0` | gravar `preco_unitario = 0`, gravar nota *"unidades=0, preço unitário não calculável"*. Não aborta a compra inteira. |
| `frete = 0 e desconto = 0` | rateio é no-op. Salva como hoje. |

### Interação com Tema A (custo dinâmico)

**Não muda nada do Tema A.** O custo dinâmico continua olhando `preco_unitario`
da última Compra via `latest_unit_price()`. A diferença é que agora esse
valor já incorpora o rateio — então o custo de receita por unidade fica
mais próximo do real, sem mexer em nenhum cálculo de custo.

### Bot — extração de frete/desconto

**Status atual:** `bot/lib/gemini.py:39,64` — o prompt menciona desconto só
em `observacoes` (campo de texto livre), e **não menciona frete em lugar
nenhum**. Nenhum campo estruturado pros dois.

`bot/lib/orchestrator.py:879-890` (`_finalize`) chama `append_compra` item
por item, sem passar frete/desconto. `bot/lib/sheets.py:156` (`append_compra`)
também não recebe esses parâmetros.

**Plano:**

1. **Adicionar ao prompt de `gemini.py` (`SYSTEM_PROMPT` e `TEXT_PROMPT`):**

   ```
   "frete": 0.00,        // taxa de entrega total da compra, ou 0
   "desconto": 0.00,     // desconto total aplicado, sempre positivo, ou 0
   ```

   Instrução adicional no prompt: *"Se a nota mostrar uma linha 'TAXA DE
   ENTREGA', 'FRETE', 'ENTREGA' → frete. Se mostrar 'DESCONTO', 'DESC.',
   'ABATIMENTO' → desconto (sempre positivo). Se não houver, deixe 0."*

2. **No fluxo do bot (orchestrator), antes do confirm final** (`_finalize`):
   - Se Gemini retornou `frete > 0` ou `desconto > 0`, mostra na overview
     (`_format_overview` em `orchestrator.py:903`).
   - **Step novo opcional** *antes do save*: botão "✏️ Editar frete/desconto"
     na confirmation message — abre prompt de texto pra digitar valor
     corrigido. Pra primeira versão, dispensa: usa o que Gemini extraiu, e
     se precisar corrigir a usuária edita no Sheet depois (vai existir UI
     em Compras — ver abaixo).
   - **Step novo obrigatório quando há múltiplos itens:** uma mensagem
     "🚚 Tem frete nessa compra?" com botões `R$ 0` / `Sim, digitar` —
     mesmo se Gemini achou que era zero. Razão: frete é o caso mais
     omitido pela OCR (linha pequena, fácil perder) e é exatamente quando
     o rateio mais importa.

3. **No `_finalize`:** computar o rateio antes do loop de append, passar
   `frete` e `desconto` pra cada chamada de `append_compra` (que grava
   nas colunas L/M de cada linha — mesmo valor repetido) e passar o
   `preco_total_efetivo` ao invés do `preco_total` bruto. Bot exibe no
   resumo final: *"✅ Adicionei 5 compras (frete R$ 8 ratado, desconto R$ 0)."*

4. **Fluxo manual `/compra`** (single-item, `bot/lib/orchestrator.py:1384`):
   atualmente pergunta produto/fornecedor/qtde/preço. Manter como está —
   single-item com frete não faz sentido de ratear (todo o frete cai no
   único item, equivalente a `preco += frete - desconto`). Adicionar
   step opcional *"Tem frete? (digite 0 se não)"* só depois do preço.
   Adia se quiser uma versão mínima.

### UI Compras — edição

**Status atual:** `app/pages/5_🛒_Compras.py` só **lê** Compras (resumo
mensal, tabela detalhada, drill-down). **Não tem edição nem delete.**

Pra primeira versão do Item 7, o mínimo viável é:

1. **Mostrar `frete` e `desconto` no drill-down** (`app/pages/5_🛒_Compras.py:192-208`):
   ao expandir uma compra, exibir as duas colunas se existirem. Não-zero
   destacado.

2. **Editar via Sheet por enquanto.** A usuária abre o Google Sheet
   diretamente e ajusta `frete`/`desconto` se o bot extraiu errado. Adicionar
   um caption na página: *"Pra ajustar frete/desconto, edita direto no
   Sheet — a UI ainda não tem edição."*

3. **Próxima iteração (não nesta fase):** botão "✏️ Editar" em cada linha
   do drill-down que abre um form com os campos editáveis. Aí também
   recomputa o rateio e atualiza todas as linhas daquela compra
   (precisa agrupar por `data + fornecedor_id + observação-da-mesma-nota`
   — não tem chave de compra hoje, esse é parte do trabalho da Opção B
   do schema).

---

## Item 8 — Nova categoria `GRA-` (gráfica)

### Lista de mudanças no código

Categoria nova precisa entrar em **5 lugares** (todos com o mesmo padrão
das outras 5):

1. **`bot/lib/sheets.py:136`** — adicionar `"GRA"` ao whitelist:
   ```python
   if categoria not in ("ALI", "FOR", "EMB", "EQP", "OPR", "GRA"):
   ```

2. **`bot/lib/gemini.py`** — `SYSTEM_PROMPT` (linha ~31) e `TEXT_PROMPT`
   (linha ~150): adicionar `"GRA"` à enum de `categoria` e à seção de
   classificação:
   ```
   - GRA = material impresso em gráfica (adesivo, etiqueta, rótulo,
     papel impresso, cartão, flyer). Custo de comunicação visual /
     identidade, não embalagem física.
   - EMB = embalagens FÍSICAS do produto final (sacola, fita, barbante,
     pote, tampa, lacre, celofane, colher descartável). NÃO inclui
     impressos.
   ```
   Importante: deixar o prompt EXPLÍCITO de que adesivo/etiqueta vão pra
   GRA, não EMB — senão o modelo continua botando em EMB.

3. **`scripts/migrate_categoria.py:41`** — adicionar `"GRA"` a
   `VALID_CATEGORIAS`.

4. **`app/pages/2_📦_Insumos.py:70-86`** — adicionar GRA aos 4 dicts
   (`CAT_EMOJI`, `CAT_LABEL`, `CAT_TAB_ORDER`, `CAT_TAB_TITLE`) e à
   chamada `st.tabs([...])` na linha 179-186, e ao dict `_cat_tabs` na
   linha 187. Sugestão de emoji: 🖨️ (impressora). Ordem na linha:
   depois de EMB (faz sentido visual já que são "primos").

   ```python
   CAT_EMOJI = {"ALI": "🍯", "FOR": "🥣", "EMB": "📦", "GRA": "🖨️", "EQP": "🔧", "OPR": "🧻"}
   CAT_LABEL = {..., "GRA": "Gráfica (impressos)", ...}
   CAT_TAB_ORDER = ["ALI", "FOR", "EMB", "GRA", "EQP", "OPR"]
   CAT_TAB_TITLE = {..., "GRA": "🖨️ Gráfica", ...}
   ```

   Isso automaticamente:
   - Adiciona a 7ª root tab na Insumos page.
   - Aparece como opção no form "Novo insumo" (que usa `CAT_LABEL.keys()`).
   - Aparece nas Lista cards (que usam `CAT_EMOJI.get(categoria)`).

5. **`app/pages/1_🍮_Tamanhos.py:295` e `:620`** — `_cat_order = {"FOR": 0, "EMB": 1}`
   determina quais categorias aparecem como opção de "embalagem" pra um
   tamanho. **Decisão:** adicionar GRA aqui também — `{"FOR": 0, "EMB": 1, "GRA": 2}`.
   Razão: um adesivo é literalmente colado em cada pote de pudim, então
   conta como custo unitário por tamanho via `Embalagens_Por_Tamanho` (mesma
   mecânica das outras embalagens). Custo de adesivo entra no cálculo de
   `custo_embalagem_unid` do tamanho. Nome da função/coluna fica genérico
   (`Embalagens_Por_Tamanho`) mas inclui gráfica — aceitável, não vale a
   pena renomear schema só por isso.

### Produtos candidatos a migrar (EMB- → GRA-)

Heurística: produtos cujo nome contenha (case-insensitive) alguma de
"ADESIVO", "ETIQUETA", "RÓTULO", "ROTULO", "IMPRESSO", "PAPEL IMPRESSO",
"CARTAO IMPRESSO", "TAG".

Da seed inicial em `scripts/deploy_to_sheets.sh:72-91` (lista pode ter
crescido com bot), os candidatos óbvios são:

| ID atual | Nome | Justificativa |
|----------|------|---------------|
| EMB-008  | ETIQUETA REDONDA TAMPA VINIL (7,5x7,5)   | etiqueta → GRA |
| EMB-009  | ADESIVO CACHORRO CARAMELO                | adesivo → GRA |
| EMB-010  | ADESIVO BANDEIRA CARAMELO                | adesivo → GRA |
| EMB-011  | ADESIVO ME VÊ 2 FATIAS                   | adesivo → GRA |
| EMB-018  | ETIQUETA REDONDA TAMPA PAPEL (7,5x7,5)   | etiqueta → GRA |

Os outros EMB- da seed (sacolas, celofane, fita, colher, barbante, saco
plástico) ficam em EMB — são embalagem física.

**Validar contra Produtos antes de migrar.** A lista real do Sheet pode
ter EMB- adicionados pelo bot que não estão na seed. Antes de rodar a
migração, abrir a tab Produtos e procurar os mesmos padrões via filtro.

### Comando de migração

Cada produto migra individualmente via `scripts/migrate_categoria.py` (já
trata Compras, Aliases e Embalagens_Por_Tamanho):

```bash
# Dry-run primeiro (default)
python scripts/migrate_categoria.py --from EMB-008 --to-categoria GRA
python scripts/migrate_categoria.py --from EMB-009 --to-categoria GRA
python scripts/migrate_categoria.py --from EMB-010 --to-categoria GRA
python scripts/migrate_categoria.py --from EMB-011 --to-categoria GRA
python scripts/migrate_categoria.py --from EMB-018 --to-categoria GRA

# Confere a saída de cada um (lista refs em Compras/Aliases/Embalagens_Por_Tamanho)
# então roda com --apply:
python scripts/migrate_categoria.py --from EMB-008 --to-categoria GRA --apply
# ...repetir pros outros 4
```

**Pré-requisito:** mudança 3 acima (adicionar `"GRA"` a `VALID_CATEGORIAS`)
precisa estar mergeada antes de rodar a migração.

**Ordem das mudanças:**

1. Mudanças de código (1–5 acima).
2. Deploy do app e do bot.
3. Migração dos produtos (5 comandos `--apply`).
4. Validar: abrir Insumos no app, ver a tab 🖨️ Gráfica com os 5 produtos
   novos (GRA-001 a GRA-005). Verificar que custo de embalagem dos
   tamanhos que usavam EMB-008/009/010/011/018 não mudou (refs em
   Embalagens_Por_Tamanho devem ter sido atualizadas).
5. Manda uma nota teste pelo bot pra confirmar que ele classifica
   adesivo como GRA agora.

---

## Open questions

1. **Tema A (custo dinâmico) está em andamento ou já feito?** Esse plano
   assume que `latest_unit_price` continua o mecanismo de custo. Se o
   Tema A já trocou pra média ponderada ou janela temporal, o item 7
   muda nada (a coluna que ele lê continua sendo `preco_unitario`), mas
   vale checar.

2. **Frete de devoluções / vale-troca:** não considerei. Caso raro,
   acionável depois.

3. **Compras antigas sem frete/desconto preenchidos:** ficam como estão
   (preço bruto). Não vale repassar histórico — o cálculo de custo usa
   só a Compra mais recente.

4. **EMB-005 "FITA PRODUTO ARTESANAL":** essa fita tem texto impresso? Se
   sim, é GRA. Se é só fita lisa, fica em EMB. Verificar com a dona antes
   de migrar.

5. **Granularidade de "frete" para compras online (Mercado Livre, etc.):**
   muitas vezes o frete vem por item, não por pedido. Assumindo que pra
   esses casos a dona simplesmente põe `frete=0` por linha e o preço do
   item já inclui o frete dele — mesma situação de hoje.
