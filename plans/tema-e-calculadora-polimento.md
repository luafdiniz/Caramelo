# Tema E — Calculadora multi-direcional + polimento Tamanhos

Plano para os três pontos do Tema E:

- **Item 3** — transformar a Calculadora (`app/pages/3_🧮_Calculadora.py`) num
  solver multi-direcional: a Luiza escolhe qual variável quer descobrir e fixa
  as outras como input.
- **Item 12** — adicionar **Total geral de custo de embalagem** abaixo do
  `st.data_editor` de embalagens em `app/pages/1_🍮_Tamanhos.py`.
- **Item 13b** — avaliar viabilidade de **filtro por coluna** no mesmo
  data_editor e recomendar manter ou descartar.

Sem implementação aqui — só o desenho. Implementação em sessão separada.

---

## Resumo

A Calculadora hoje é unidirecional pra um único caso: dado um Tamanho
cadastrado, mostra custo unitário e simula preço/margem em escadinha. Ela
não responde perguntas como "se vendo o quilo a R$ X, quanto fatura?" ou
"com R$ A em insumos disponíveis, quantos kg consigo produzir?". A
proposta é generalizar pra um modelo de variáveis ligadas por equações
simples e deixar a Luiza fixar/desfixar cada uma.

Os itens 12 e 13b são polimentos pontuais no Tamanhos.

---

## Item 3 — Calculadora multi-direcional

### Variáveis do modelo

Distinguindo o que é **input livre** (a Luiza digita), **derivado** (sai de
fórmula) e **ambos** (pode entrar como input *ou* sair como cálculo):

| # | Variável | Unidade | Natureza | Origem padrão |
|---|----------|---------|----------|----------------|
| 1 | `peso_base_receita` | kg de massa pronta | ambos | hoje implícito; ex: 1kg |
| 2 | `qtde_ingrediente_i` (uma por ingrediente) | kg/L/un | derivado de 1 | proporção da receita escolhida |
| 3 | `preco_unit_ingrediente_i` | R$/un do ingrediente | input | última compra (`latest_unit_price`) |
| 4 | `custo_ingredientes_total` | R$ | derivado de 2×3 | soma |
| 5 | `custo_embalagem_unit` | R$/unidade vendida | input ou vem do Tamanho | `calc_custo_embalagem_unid` |
| 6 | `qtde_unidades_produzidas` | un | ambos | `peso_base_receita / peso_unit` |
| 7 | `peso_unit` | kg/unidade | input | do Tamanho selecionado |
| 8 | `custo_total` | R$ | derivado de 4 + 5×6 | soma |
| 9 | `preco_venda_unit` | R$/unidade | ambos | do Tamanho ou input |
| 10 | `preco_venda_kg` | R$/kg | ambos | `preco_venda_unit / peso_unit` |
| 11 | `faturamento` | R$ | derivado de 6×9 | soma |
| 12 | `lucro_total` | R$ | derivado de 11 − 8 | subtração |
| 13 | `lucro_unit` | R$/unidade | derivado de 9 − (8/6) | subtração |
| 14 | `margem` | % | ambos | `lucro_unit / preco_venda_unit` |
| 15 | `markup` | × | ambos | `preco_venda_unit / custo_unit` |
| 16 | `meta_faturamento` | R$ | input | digitado pela Luiza |
| 17 | `orcamento_insumos` | R$ | input | digitado pela Luiza |

Não modelar todos os ingredientes individualmente como "unknown" — esse vetor
é sempre derivado de `peso_base_receita` × proporção da receita. O ingrediente
nunca é o unknown; **o peso base sim**. Isso simplifica o solver bastante.

### Equações / relações

Todas lineares ou simples-multiplicativas — nenhuma envolve sistema acoplado
de verdade:

```
E1.  qtde_ingrediente_i      = (peso_base_receita / peso_base_padrao) * qtde_padrao_i
E2.  custo_ingredientes_total = Σ qtde_ingrediente_i * preco_unit_ingrediente_i
E3.  qtde_unidades_produzidas = peso_base_receita / peso_unit
E4.  custo_total              = custo_ingredientes_total + custo_embalagem_unit * qtde_unidades_produzidas
E5.  preco_venda_kg           = preco_venda_unit / peso_unit
E6.  faturamento              = preco_venda_unit * qtde_unidades_produzidas
E7.  lucro_total              = faturamento - custo_total
E8.  lucro_unit               = lucro_total / qtde_unidades_produzidas
E9.  margem                   = lucro_unit / preco_venda_unit
E10. markup                   = preco_venda_unit / custo_unit  (onde custo_unit = custo_total / qtde_unidades_produzidas)
```

Grupos independentes (subgrafos):

- **Receita:** E1+E2 → custo de ingredientes a partir de `peso_base_receita`.
- **Produção:** E3 → quantas unidades, a partir do peso base e peso unitário.
- **Custo:** E4 → total monetário do batch.
- **Preço:** E5, E6 → faturamento.
- **Resultado:** E7..E10 → lucro/margem/markup.

### UX — recomendação: Opção A (radio "Resolver para")

**Recomendação: Opção A**, com pequenas adaptações.

Justificativa:

- **Opção A (radio "Resolver para X")**: a Luiza escolhe num único lugar
  o que é o unknown e o resto vira input editável. **Mais simples de
  modelar e de explicar.** Combina com como ela pensa (frases tipo "quero
  saber X dado Y, Z"). Único lugar onde precisa atenção: a lista de "para
  que resolver" tem que ser curta e em PT-BR claro (ver presets abaixo).
- **Opção B (todas as vars na tela, ela "pina" o que é input)**: poderosa
  mas overkill. Streamlit não tem componente nativo de "pin/unlock";
  faríamos com checkbox por linha e a UX vira sopa visual. Reservar como
  *talvez v2* se ela pedir.
- **Opção C (tabs/steps de modo guiado)**: na prática vira o mesmo que A,
  mas pior — radio resolve em 1 clique, tab consome largura horizontal e
  duplica labels.

**Presets do radio "Resolver para:"** (lista curta, em PT-BR, ordenada por
frequência de uso esperada):

1. **Custo unitário e margem** (o que a tela faz hoje — caso default,
   pré-selecionado).
2. **Preço de venda pra atingir margem X**.
3. **Quanto preciso vender pra faturar R$ Y** (qtde de unidades dado
   `meta_faturamento` + `preco_venda_unit`).
4. **Quantos kg consigo produzir com R$ Z em insumos** (`peso_base_receita`
   a partir de `orcamento_insumos`).
5. **Faturamento e lucro de uma fornada** (input: tamanho, qtde produzida,
   preço; output: faturamento e lucro).
6. **Preço por kg ↔ preço por unidade** (conversor simples — atende o
   "vendo o quilo a R$ X" que é a forma como concorrentes anunciam).

Cada preset é só um arranjo de "este campo é unknown, o resto é input
livre". Implementação interna é uma função pura `solve(preset, inputs) →
outputs`.

**Layout sugerido da página:**

```
🧮 Calculadora
[selectbox Tamanho (opcional — pré-popula inputs)]
[radio "Resolver para:" com os 6 presets]
─────────────────────────────
[bloco de inputs do preset escolhido]   [bloco de outputs em compact_kpi]
─────────────────────────────
[expander "🔍 Ver memória de cálculo"]
```

Manter o "Salvar preço de venda" atual como ação separada no final, só
quando o preset for o 1 (custo + margem do Tamanho selecionado) — fora dele
não faz sentido salvar.

### Arquitetura

**KISS confirmado.** As equações são lineares/escalares e o grafo de
dependência é um DAG raso (3-4 níveis no max). **Não precisa sympy.**

Implementação:

- `app/lib/calc.py` (arquivo novo, ~80 linhas):
  - `class CalcState` (dataclass) com os 17 campos opcionais (`float |
    None`).
  - Função pura `solve(state, preset) → state` que, dado o preset,
    rouba os valores que ele exige como input do `state` e calcula os
    derivados via substituição direta nas equações E1..E10.
  - Cada preset é uma função pequena (10-15 linhas) que chama as
    equações relevantes na ordem certa. Não precisa motor genérico de
    grafo — 6 funções específicas são mais legíveis e mais fáceis de
    debugar do que um resolver mágico.
- `app/pages/3_🧮_Calculadora.py` chama `solve()` e renderiza inputs
  com `st.number_input` e outputs com `compact_kpi`.

Eu evitaria construir um "motor de grafo de dependência genérico" mesmo
sendo bonito — pra 6 presets a engenharia extra não compensa. **Mantém ~80
linhas de código testáveis em isolamento.**

### Sanity warnings

A página deve avisar (com `st.warning` ou `st.error`) quando:

- `lucro_total < 0` ou `lucro_unit < 0` → "Tá vendendo no prejuízo."
- `margem < 0` → idem (redundante mas explícito).
- `margem > 0.95` → "Margem absurdamente alta — confere se preço/custo tão certos."
- `custo_total > faturamento` → "Custo maior que faturamento, vai dar
  prejuízo."
- `qtde_unidades_produzidas` não-inteira quando `peso_unit` divide
  exatamente o `peso_base_receita`: arredondar pra baixo e mostrar
  caption "Sobra X g de massa".
- Algum `preco_unit_ingrediente_i == 0` (não tem compra cadastrada): mostrar
  "⚠️ Sem preço pra ingrediente Y — resultado está subestimado."
- Faltam dados (rendimento vazio, receita vazia): mensagem clara sobre o que
  cadastrar antes de calcular.

---

## Item 12 — Total geral de custo de embalagem

**Onde:** logo abaixo do `st.data_editor` de embalagens dentro do
`with st.expander("Ver composição completa")` no
`app/pages/1_🍮_Tamanhos.py` (~linha 380, depois do `edited_emb_df = ...`),
mas **antes** do "Salvar alterações".

**Conteúdo:** uma linha com o somatório da coluna **Custo** do data_editor.
Como o `Custo` é recomputado no save, o total mostrado pode usar `comp_df`
(ou `edited_emb_df` filtrado pelas linhas não-removidas) como fonte.

Exemplo:

```python
total_emb = float(edited_emb_df.loc[~edited_emb_df["Remover"], "Custo"].sum())
st.caption(f"**Total embalagem por unidade: {brl_md(total_emb)}**")
```

Usa `brl_md` (helper já existe em `app/lib/ui.py`) — o data_editor está num
contexto markdown, então `$` precisa escape. Direita alinhada não é
estritamente necessária; o caption sob a tabela é suficientemente próximo
visualmente.

Bonus opcional: se a Luiza valorizar, mostrar também o **custo
ingredientes/unid + total embalagem = custo unitário** ali mesmo, fechando
a equação na cabeça dela sem ter que olhar o card lá em cima.

---

## Item 13b — Filtro por coluna no data_editor

**Recomendação: descartar.**

Razões:

1. **Streamlit 1.40.1 não tem filtro nativo por coluna no data_editor.** O
   `column_config` aceita customizar tipo, label, formato e edição, mas
   não filtro. Só sort por header (já tem). Confirmado nas docs e via
   inspeção do código atual.
2. **Volume não justifica.** Cada Tamanho tem tipicamente 3-6 embalagens
   (forma + tampa + lacre + saco + etiqueta, mais ou menos). Em mais de
   ~10 itens talvez o filtro fizesse sentido — não é o caso.
3. **Alternativa custosa.** Pra implementar manualmente: um expander
   "🔍 Filtros" com selectbox por categoria/produto + busca por nome.
   Pra a quantidade real de linhas isso é mais clique do que ganho.

**O que sim ajudaria** (caso a Luiza insista que tá difícil achar coisa):

- Search box global (`st.text_input` "🔎 Buscar nome/ID") acima da tabela,
  filtra `current_pkgs` por substring case-insensitive. ~5 linhas. **Implementar
  só se ela pedir explicitamente** — por enquanto fica como ideia anotada,
  não no escopo do Tema E.

---

## Open questions

1. **Receita do solver** — a calculadora multi-direcional deve travar numa
   única receita (a padrão), ou deixar a Luiza escolher receita igual o
   Tamanhos faz? Default: deixar escolher, mas pré-selecionar a padrão.
2. **Embalagem na calculadora** — quando o preset não é "custo de um
   Tamanho específico", de onde vem `custo_embalagem_unit`? Três
   alternativas:
   (a) sempre pegar do Tamanho selecionado no topo;
   (b) input livre;
   (c) ignorar embalagem nos presets "abstratos" (3, 4, 6).
   Sugestão: (a) com fallback pra (b) quando nenhum tamanho selecionado.
3. **Margem: sobre preço ou sobre custo?** Hoje o código calcula `lucro /
   preco_venda` (markup-style margem comercial). A Luiza pode pensar
   diferente em conversa ("ganho 50% no pudim" pode ser sobre custo).
   Confirmar antes de implementar pra não inverter a fórmula nela.
4. **Salvar resultado em algum lugar?** Hoje o "Salvar preço" só faz
   sentido no preset 1. Outros presets são exploratórios e não
   salvariam — confirmar se ela quer botão "Aplicar preço a tamanho X"
   no preset 2 também.
5. **Mobile** — radio + 6 presets pode ser longo no celular. Considerar
   `st.selectbox` em mobile (uma linha) e `st.radio` em desktop. Ou
   sempre selectbox por simplicidade. Decidir na implementação.
6. **Item 12 + Tamanhos novos** — replicar o total também no formulário
   `tab_new` (cadastro de novo tamanho)? Mais consistente, mas adiciona
   ruído enquanto ela ainda tá montando. Sugestão: só na edição (onde
   vale conferir o número antes de salvar).
