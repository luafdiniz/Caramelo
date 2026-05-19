# QA App UX — 2026-05-19

Auditoria de UX e flows do app Streamlit (`app/`). Sem rodar o app — só leitura
estática dos arquivos. Convenção: `app/pages/X_NAME.py:LINE` para citar linha.

---

## 🛑 BLOCK

São problemas que travam um fluxo essencial, corrompem dado, ou contradizem
explicitamente o padrão acordado hoje. Devem ser arrumados antes de a Luiza
voltar a usar o app.

### B1 — Tamanhos: ao criar tamanho novo, a coluna I (`receita_id`) NÃO é setada
**Arquivo:** `app/pages/1_🍮_Tamanhos.py:732-752`
**O quê:** o `new_tamanho` form escreve só A2:H (8 colunas: id, nome, peso,
volume, rendimento, canal, preco, notas) via `update` em `Tamanhos!A{next_row}`.
O range escreve A2:H, mas a coluna I (`receita_id`) fica vazia — o que é o
comportamento correto pra "use padrão", então ok funcionalmente. **Porém**, se
você criou tamanhos antigos com I preenchida (lixo) e essa linha foi reaproveitada,
a I não é limpa. **Risco baixo** porque `update` no range A:H não toca I — mas
não há sinal claro de que a próxima linha está vazia em I. Bug latente se a
sheet tiver "buracos".
**Severidade:** baixa, mas marquei aqui porque mistura "tamanho novo silenciosamente
herda receita errada" — risco de cálculo de custo errado, que é o pior bug do app.
**Fix:** estender o range pra A:I e mandar `""` explicitamente na 9ª posição.

### B2 — Calculadora: `tamanhos.empty` faz `st.stop()`, mas `index=1` em selectbox quebra
**Arquivo:** `app/pages/3_🧮_Calculadora.py:47`
```python
sel = st.selectbox("Tamanho base (opcional)", list(opts.keys()), index=1)
```
**O quê:** depois do `st.stop()` quando `tamanhos.empty`, sabemos que tem ≥1
tamanho. `opts` tem `"— Sem tamanho base —"` + N tamanhos, ou seja len ≥ 2 — então
`index=1` é válido. Sem bug aqui, mas o preset `kg_com_orcamento` (linha 188)
avisa para selecionar Tamanho base mesmo o default sendo já o primeiro tamanho.
Ou seja, fluxo OK. **Removo a flag.** (Mantenho a nota: confirmar manualmente.)

### B3 — Vendas: `preco_unit` é desabilitado pelo botão mas resolve_preco_unit retorna 0 em vários cenários
**Arquivo:** `app/pages/9_💰_Vendas.py:78-83, 112`
**O quê:** quando `resolve_preco_unit` retorna 0 (cliente B2B sem faixa cadastrada
e Tamanho sem `preco_venda`), o número-input pré-popula 0 e o botão "Registrar
venda" fica disabled. Bom — não permite venda zerada. **Porém:** o usuário precisa
digitar manualmente o preço, e sem nenhum aviso. **Fix de UX:** mostrar
`st.warning("Nenhuma faixa de preço encontrada para esse cliente/tamanho — digite manualmente")`
quando `preco_resolvido == 0`. Não bloqueia, só explica.

### B4 — Vendas: salvar venda sem validar que `tamanho_id` ainda existe
**Arquivo:** `app/pages/9_💰_Vendas.py:54-62`
**O quê:** se um tamanho foi deletado entre o carregamento da página e o submit
(janela pequena, mas existe), a venda salva com `tamanho_id` órfão. **Severidade:**
muito baixa (concorrência baixa, single user). **Marco como FLAG**, não BLOCK.

### B5 — Insumos (Tabela): rename do produto via editor não atualiza outras abas
**Arquivo:** `app/pages/2_📦_Insumos.py:592-605`
**O quê:** mudar `Nome` em Produtos atualiza só a coluna B daquela linha.
Embalagens_Por_Tamanho e Receita_Ingredientes têm o nome cacheado em coluna
adjacente (via VLOOKUP em embalagens, mas hardcoded em receita ingredientes
— ver `7_📜_Receitas.py:514-519`: salva `nome_prod` na coluna C de
`Receita_Ingredientes`). Resultado: ao renomear "Açúcar refinado" → "Açúcar cristal",
as receitas vão continuar mostrando "Açúcar refinado" até serem editadas e salvas.
**Severidade:** média. Não é dado errado, é só desatualizado visualmente.
Marco como FLAG, mas é o tipo de coisa que confunde a usuária.

---

## ⚠️ FLAG

Inconsistências, edge cases, papercuts. Não bloqueia uso, mas afeta a
experiência.

### F1 — Inconsistência view/edit toggle: páginas que **NÃO** seguem o padrão
- `9_💰_Vendas.py:142-157`: histórico de vendas é **só read-only** (st.table).
  Sem botão de editar — OK porque vendas devem ser imutáveis. Confirme com
  Luiza se é desejado mesmo (e cancelar venda é só via `status="cancelada"`,
  feito no momento da criação? Não há fluxo para mudar status depois).
- `4_🏭_Produção.py:280-301`: histórico de fornadas é **só read-only** (cards
  com `compact_kpi`). Sem editar, sem deletar. Se uma fornada foi registrada
  errada (qtde produzida errada, preço errado), não há jeito de corrigir pelo
  app. **Recomendação:** adicionar `🗑️ Deletar fornada` ou editar inline.
- `5_🛒_Compras.py:186, 192`: tabela detalhada usa `st.dataframe` (não
  `st.table`), e nenhum edit-toggle. Compras são imutáveis também? Se sim,
  manter — mas pelo menos converter pra `st.table` pra estilo consistente.
- `6_🏪_Fornecedores.py:99-185`: lista de fornecedores usa cards individuais
  com `st.expander("✏️ Editar / 🗑️ Deletar")` por linha — **não tem toggle
  view/edit**, é direto edit. Inconsistente com o padrão estabelecido.

### F2 — Compras: `frete` e `desconto` não aparecem em lugar nenhum
**Arquivo:** `app/pages/5_🛒_Compras.py:175-186, 192-208`
**O quê:** `data.get_compras` lê coluna L (`frete`) e M (`desconto`) (`app/lib/data.py:185-187`),
mas a tabela detalhada (`table` linhas 175-186) não exibe nem frete nem desconto.
Tampouco o drill-down (linhas 192-208) mostra esses valores. O detalhe sobre rateio
de frete é importante pra Luiza (existe tema-c-frete-rateio-grafica.md), então
**precisa de coluna ou linha caption**. Pelo menos no drill-down: `f"Frete: {brl(r['frete'])} · Desconto: {brl(r['desconto'])}"` quando não-zero.

### F3 — Tamanhos: ao trocar receita_id sem ter Receitas migradas, falha silenciosamente
**Arquivo:** `app/pages/1_🍮_Tamanhos.py:480-486`
**O quê:** o write da coluna I (`receita_id`) é guardado por `if not receitas_df.empty`.
Se `Receitas` ainda não foi migrado, a edição não atualiza receita — mas o usuário
não é avisado. Provavelmente OK (a Receitas page já mostra "Schema novo ainda não
foi migrado"), mas mudei pra FLAG porque é silencioso.

### F4 — Receitas (edit mode): `data_editor` exibe `Custo` como string ("R$ X,YZ") mas o `column_config` declara `TextColumn`
**Arquivo:** `app/pages/7_📜_Receitas.py:172-176, 376-389`
**O quê:** o `column_config` de Custo é `TextColumn(disabled=True)`. O fluxo:
`comp_df` tem Custo numérico → `display_df = _format_custo_column(comp_df)` formata
como BRL → `st.data_editor(display_df, ...)`. Depois `edited_numeric` reusa o Custo
original de `comp_df`. Tudo bem. Mas: ao editar Qtde, **o Custo no editor não atualiza
até o save** (porque Streamlit não recalcula entre teclas). Caption ou help já avisa
("Atualiza ao salvar"), mas o feedback de custo deveria atualizar em real time
ou pelo menos no rerun seguinte. **Papercut.**

### F5 — Receitas: `clear_on_submit=False` em "Nova receita"
**Arquivo:** `app/pages/7_📜_Receitas.py:626`
**O quê:** depois de criar uma receita, todos os ingredientes ficam selecionados.
Se a Luiza esquecer e clicar de novo, ela cria uma receita duplicada. Usar
`clear_on_submit=True` (como em "novo cliente" e "novo fornecedor").

### F6 — Receitas: deletar a única não-padrão deixa só a padrão, mas botão de deletar a padrão é bloqueado SEM oferecer "trocar padrão"
**Arquivo:** `app/pages/7_📜_Receitas.py:552-556`
**O quê:** se há só uma receita e ela é padrão, o usuário não consegue deletá-la
nem trocar de padrão (não tem outra). Mas:
- Aviso "Marca outra como padrão antes de deletar" assume que há outra.
- Se for a única, a Luiza fica presa.
**Fix:** quando `len(receitas) == 1` e a única é padrão, exibir uma mensagem
diferente: "Receita única — pra deletar, cadastre outra primeiro".

### F7 — Calculadora: `peso_unit=0` (preset `preco_kg_unid`) já é tratado, mas `_qtde_unidades` pode dividir por zero
**Arquivo:** `app/lib/calc.py:69-72`
```python
def _qtde_unidades(s: CalcState) -> None:
    if s.peso_base_receita is None or s.peso_unit in (None, 0):
        return
```
**O quê:** ok, dividido por zero está protegido. **Mas** se `peso_unit == 0` e
o usuário pede `solve_custo_e_margem`, `qtde_unidades_produzidas` fica None e
todo o cálculo vira `—`. Sem warning explicando "configure peso unitário do
tamanho". **Fix de UX:** quando `peso_unit == 0` ou None, mostrar warning "peso
unitário não cadastrado pro tamanho selecionado".

### F8 — Calculadora: `solve_custo_e_margem` não valida preco<custo de forma proativa
**Arquivo:** `app/lib/calc.py:103-119` (função `_sanity`)
**O quê:** as warnings só disparam quando `lucro_total < 0` ou `margem > 0.95`
ou `custo_total > faturamento`. Pessoal — `margem >= 1.0` (preço == custo)?
**Fix:** adicionar warning em `margem == 0` ("vendendo no zero a zero").

### F9 — Produção: deletar uma fornada não é possível
**Arquivo:** `app/pages/4_🏭_Produção.py:225-301`
**O quê:** se a Luiza registrar uma fornada errada (qtde produzida zero por
engano + qtde_vendida > 0, por exemplo), não há jeito de remover. **Adicionar
botão deletar** (com confirm two-step) seria útil.

### F10 — Produção: edge case "vendas > produzidos"
**Arquivo:** `app/pages/4_🏭_Produção.py:110-111`
```python
if teste_perda < 0:
    st.error(f"Vendidos + cortesia ({vendidos + cortesia}) é maior que produzidos ({produzidos})")
```
Bom — erro é claro. **Mas:** o botão "💾 Registrar fornada" NÃO valida isso antes
de salvar (linha 165). Se a Luiza não notar o `st.error`, ela salva mesmo assim
e tem fornada com `teste_perda` negativo escrito na coluna notas. Fix: bloquear
submit quando qualquer linha tem `teste_perda < 0`.

### F11 — Produção: salvar fornada com `produzidos = 0` para alguns tamanhos
**Arquivo:** `app/pages/4_🏭_Produção.py:123-132`
**O quê:** já filtra (`if produzidos > 0`). OK.

### F12 — Insumos (Tabela): `unit_changes` é tracked, mas só o último Salvar dispara o aviso
**Arquivo:** `app/pages/2_📦_Insumos.py:464-470, 548-561`
**O quê:** se a Luiza muda unidade em duas linhas diferentes na mesma
edição, ambas aparecem na lista. Bom. **Mas:** o aviso "isso recalcula o preço
unitário de todas as Compras anteriores desse insumo" é **enganoso**. Mudar a
unidade no produto não recalcula a Compras coluna `preco_unitario` (não há código
que faz isso). O texto diz "foi recalculado ao reler o catálogo" (linha 897), mas
não é verdade — só `current_unit_price` usa os Compras como estão. **Fix:** trocar
o aviso pra "isso muda a interpretação da unidade do insumo, mas Compras antigas
mantêm seu preço unitário ORIGINAL — confirme se faz sentido".

### F13 — Insumos (Tabela editor): cancelar com mudanças no editor não pergunta
**Arquivo:** `app/pages/2_📦_Insumos.py:348-350`
**O quê:** "✖ Cancelar edição" descarta tudo sem confirm. Se a Luiza editou 20
linhas e clica cancelar por engano… vai. **Fix:** confirm.

### F14 — Insumos (Lista cards): formulário expande pra cada produto
**Arquivo:** `app/pages/2_📦_Insumos.py:828-852`
**O quê:** cada card tem seu próprio `st.form` dentro do expander. Se há 30
produtos numa categoria, são 30 formulários. Streamlit lida bem, mas o
`session_state` cresce. **Provavelmente OK** — flag só pra ter na cabeça.

### F15 — Clientes: deletar (exclusão hard) sem checar referências em Vendas
**Arquivo:** `app/pages/8_👥_Clientes.py:165-225`
**O quê:** ao marcar Excluir em uma linha, o save deleta direto da Clientes
sheet sem checar se há Vendas apontando pro `cliente_id`. Resultado: vendas
órfãs (mesmo problema do F2 de fornecedores). **O CLI-000 também pode ser
deletado por aqui — não tem proteção mencionada.** A tarefa pediu proteção
do CLI-000, mas o código não tem nada.
**Fix:** bloquear delete quando `cliente_id` aparece em Vendas; bloquear delete
de CLI-000 sempre.

### F16 — Clientes: campo "Tipo" no editor permite mudar B2C→B2B sem checar consistência com Precos/Vendas
**Arquivo:** `app/pages/8_👥_Clientes.py:157`
**O quê:** mudar tipo do cliente muda a faixa de Preços que se aplica a futuras
vendas, mas não reprocessa vendas passadas (que estão com `canal` cacheado em
`Vendas.canal`). Comportamento esperado, mas vale uma caption no header da
coluna avisando.

### F17 — Vendas: tela "Nova venda" mostra `clientes ativos`, mas histórico não destaca cliente desativado
**Arquivo:** `app/pages/9_💰_Vendas.py:58, 142-157`
**O quê:** a tela de criar venda já filtra ativos (bom). O histórico mostra todas
as vendas independente do `ativo`. Bom. Mas: se um cliente desativado aparece
no histórico, não há indicação visual (`📦 Padaria X (inativo)`). **Papercut.**

### F18 — Preços: detectar B2B mais caro que B2C (alerta)
**Arquivo:** `app/pages/10_💸_Precos.py:55-84`
**O quê:** sem validação. B2B deveria sempre ser mais barato (atacado), mas o
código aceita preço B2B > B2C sem avisar. **Fix:** ao salvar uma faixa nova, se
existir uma faixa B2C para o mesmo tamanho e mesma qtde_min cujo preço seja
**menor** que o B2B sendo criado, mostrar warning.

### F19 — Preços: preço negativo
**Arquivo:** `app/pages/10_💸_Precos.py:53, 136`
**O quê:** `st.number_input(min_value=0.0)` impede negativo. Validação `> 0` em
linha 57 ok. **Editor também tem `min_value=0.0`** (linha 137). Sem bug, ok.

### F20 — Preços: editar faixa pode criar duplicação se mudar `qtde_min` pra valor já existente
**Arquivo:** `app/pages/10_💸_Precos.py:142-160`
**O quê:** o save sobre-escreve a linha do sheet. Se a Luiza mudar `Qtde mín` de
20 para 50, mas já existe outra faixa com 50, agora tem duas linhas com
(tamanho, tipo, qtde_min=50) e o resolvedor pega uma delas aleatoriamente (depende
da ordem). **Fix:** ao salvar, detectar duplicação `(tamanho_id, tipo, qtde_min)`
e bloquear. A validação está no fluxo "Nova faixa" (linha 61-68) mas não no
fluxo de edição.

### F21 — Calculadora: alterar `peso_base_receita` faz recalcular `qtde_unidades_produzidas` que pode dar fracional
**Arquivo:** `app/lib/calc.py:116-119`
**O quê:** tratado: warning "Sobra ~X g de massa". Bom.

### F22 — Insumos: criar insumo via "Tabela" expander pode duplicar nome
**Arquivo:** `app/pages/2_📦_Insumos.py:215-253`
**O quê:** sem validação de nome duplicado. Cria um novo `ALI-NNN` mesmo se já
houver outro produto com o mesmo nome. Tema repetido em outras páginas
(fornecedores, clientes, receitas, tamanhos) — todas aceitam duplicatas de nome.
**FLAG geral.**

### F23 — Receitas (edit mode): cancelar edição limpa pending, mas não limpa staged removals
**Arquivo:** `app/pages/7_📜_Receitas.py:442-452`
**O quê:** "✖ Cancelar edição" pop `pending_add_*` mas o estado dos checkboxes
"Remover" no `data_editor` persiste (o widget guarda no session_state com a key
`editor_{receita_id}_{comp}`). Próxima edição vai mostrar checkboxes marcados.
**Fix:** limpar `st.session_state.pop(editor_key, None)` também.

### F24 — Tamanhos: "Cancelar edição de embalagens" não limpa state de `add_pkg_*` e `bulk_rm_*`
**Arquivo:** `app/pages/1_🍮_Tamanhos.py:228-233`
**O quê:** similar ao F23. Cancelar limpa o toggle mas não os widgets internos.

### F25 — Empty states gerais: `st.stop()` cedo demais em algumas páginas
- `8_👥_Clientes.py:91`: depois de cadastrar primeiro cliente, a página `st.stop()`
  no `if clientes.empty`. Mas o form de cadastro vem ANTES — bom.
- `9_💰_Vendas.py:51-56`: requer cliente E tamanho. OK.
- `10_💸_Precos.py:40-41, 87-92`: requer tamanho. Bom — mostra `st.info` antes do
  stop. **Mas:** se a Luiza não tem tamanho, ela é informada na aba Preços que
  precisa cadastrar. Boa UX.

### F26 — Home.py: lista compras recente sem hide_index, mas com Date como string
**Arquivo:** `app/Home.py:69-77, 122`
**O quê:** usa `st.dataframe` em vez de `st.table`. Inconsistente com o padrão.
**Recomendação:** trocar pra `st.table(display.set_index("Data"))`.

### F27 — Calculadora: salvar preço de venda chama o sheets sem checar se o range G existe
**Arquivo:** `app/pages/3_🧮_Calculadora.py:269-290`
**O quê:** assume coluna G = preco_venda em Tamanhos. Schema atual confirma
(`data.py:144`). OK.

### F28 — Vendas: `custo_unit_estimado` cravado no momento da venda; se o custo dos insumos mudar depois, o "Lucro" no histórico fica desatualizado
**Arquivo:** `app/pages/9_💰_Vendas.py:102-104, 117-119`
**O quê:** comportamento correto pra contabilidade (snapshot do custo no momento
da venda) — mas o "Lucro" na tela do histórico (linha 148) usa
`disp["preco_unit_efetivo"] - disp["custo_unit_estimado"]` * `qtde` que pega o
custo CACHEADO. Bom. Confirme com Luiza se é o desejado.

### F29 — Vendas: status "cancelada" excluído do faturamento, mas a venda continua aparecendo no histórico sem destaque
**Arquivo:** `app/pages/9_💰_Vendas.py:160-164`
**O quê:** filtragem do faturamento parece correta (`vendas["status"] != "cancelada"`).
Mas no histórico (linha 151-157), a linha cancelada aparece igual às outras —
sem riscado, sem cor diferente, só com `Status="cancelada"` numa coluna.
Inteligível, mas fácil de passar batido. **Papercut.**

### F30 — Mobile: `Vendas`, `Clientes`, `Preços` (novos arquivos 8/9/10) usam `st.table` que vai virar scroll horizontal no mobile (ver ui.py:672-683)
**Arquivos:** `8_👥_Clientes.py:137`, `9_💰_Vendas.py:157`, `10_💸_Precos.py:118`
**O quê:** o CSS mobile (ui.py:672-683) trata `[data-testid="stTable"]` com
`overflow-x: auto` — então quebra OK no mobile. Bom.
**Mas:** Clientes tem 9 colunas, fica largo demais. **Recomendação:** no
mobile, mostrar uma view compacta (só Nome, Tipo, Contato).

### F31 — Empty `peso_unit` na Calculadora preset `preco_kg_unid`
**Arquivo:** `app/lib/calc.py:204-213`
**O quê:** ok, já trata. Warning "Preencha o peso unitário pra fazer a
conversão." Bom.

### F32 — Salvar preço via Calculadora gera "Salvo R$ X" mas não invalida o tamanho selecionado nem o `out.preco_venda_unit` exibido na caption
**Arquivo:** `app/pages/3_🧮_Calculadora.py:269-290`
**O quê:** `invalidate_cache` é chamado, OK. **Mas** o reload só efetiva em
proxima interação (Streamlit não rerun automaticamente). Adicionar `st.rerun()`
após o success.

### F33 — Receitas: cadastrar receita com 0 ingredientes
**Arquivo:** `app/pages/7_📜_Receitas.py:675-732`
**O quê:** se a Luiza não selecionar ingrediente nenhum, a receita é criada
com `new_ingredientes = []`. Pode ser intencional (vou cadastrar depois) mas
nenhum aviso. **FLAG.**

### F34 — Insumos: criar insumo sem categoria
**Arquivo:** `app/pages/2_📦_Insumos.py:217-222`
**O quê:** `st.radio("Categoria", cat_options)` — Streamlit força um valor.
OK, sem bug.

---

## ✅ PASS

Cobertos sem problemas críticos:

- Autenticação por senha (auth.py).
- Empty states em Home (`get_*` + fallback `st.info`).
- View/edit toggle nos arquivos novos (Clientes, Vendas read-only, Preços).
- Tamanhos: o pattern de embalagens read-only por padrão + botão "Editar
  embalagens" tá implementado direito.
- Tamanhos: state key prefixado por ID (`emb_edit_mode_{row['id']}`,
  `canal_ms_{row['id']}`, etc) — não vaza entre tamanhos.
- Receitas: edit mode também isolado por receita (`rec_edit_mode_{receita_id}`).
- Insumos (Tabela): toggle global (1 toggle = 1 grid). Edit mode tem caption
  "se trocar de aba sem salvar, as alterações não vão persistir" ✔.
- Cache invalidation: confirmado `data.invalidate_cache()` em TODOS os writes
  encontrados (varri todos os `update` e `append` calls).
- Confirmação two-step para destruction: Tamanhos delete, Insumos card delete,
  Receitas delete, Fornecedores delete — todos têm flow de confirm.
- Insumos: critical-changes checkbox antes de salvar mudanças de unidade ou
  deletar produtos com Compras.
- `qty_input_params` (lib/ui.py:874): trata unidades inteiras (UN, DZ, …)
  corretamente.
- `brl_md` vs `brl`: convenção respeitada (markdown vs plain).

---

## 📋 Por página

### Home
- **Empty state:** OK. `compras.empty` cai num caption "Nenhuma compra
  registrada ainda". `recs` empty → "Conforme você registrar mais compras,
  recomendações vão aparecer aqui." Bom.
- **Inconsistência visual:** usa `st.dataframe` em vez de `st.table` (F26).
- **KPIs:** ok.
- **Risco:** se o try (`get_tamanho_costs`) falhar, mostra `st.error` + `st.stop`,
  bloqueando a página. Talvez não-ideal — mas defensivo.

### Tamanhos
- **Toggle view/edit:** ✔ implementado pra embalagens.
- **State key prefixado por ID:** ✔.
- **Aviso de troca de aba:** ✔ ("Use o Salvar do formulário abaixo pra confirmar,
  ou cancela").
- **Edge cases:**
  - Criar sem rendimento — input tem `min_value=1`, default 1, OK.
  - Criar sem preço — `preco_venda > 0 else ""` (linha 739). OK, fica vazio.
  - Criar com peso 0 — input `min_value=0.0`, value=0.5. **Permite 0** se o
    usuário diminuir. Sem warning. Cálculo de custo vai dividir por zero?
    Não — `calc_custo_alimento_unid` usa `rendimento`, não `peso_kg`. OK.
- **Bugs encontrados:** B1 (não escreve coluna I no criar), F3, F24.
- **Geral:** página bem polida.

### Insumos
- **Toggle view/edit:** ✔ na aba Tabela. **Não** na Lista (cards têm
  edit-inline sempre visível dentro do expander — diferença intencional,
  ver docstring do arquivo).
- **Bugs encontrados:** B5 (rename não propaga), F12 (aviso enganoso), F13
  (cancelar sem confirm), F22 (duplicata).
- **Empty states:** OK em todas as sub-tabs.
- **Bulk delete + critical confirm:** bem feito, com confirm-checkbox antes
  de habilitar Save.
- **Inline price-editing:** override manual em Produtos.G/H, sem criar Compra
  fantasma. Bom.

### Calculadora
- **Empty state:** `tamanhos.empty → st.info + st.stop` ✔.
- **Divisão por zero:** protegida em todos os solvers (`_qtde_unidades`,
  `_resultado`).
- **Margem >= 100%:** `solve_preco_para_margem` checa explicitamente. OK.
- **Sem tamanho selecionado em presets que precisam:** `kg_com_orcamento`
  avisa (linha 188-192). Outros presets funcionam sem tamanho? `custo_e_margem`
  precisa de peso_base + custo_ingredientes — se tamanho não selecionado, ambos
  são None, o solver retorna sem KPIs. Mostra `—`. Não há warning pra avisar
  "selecione um tamanho". **FLAG (F7).**
- **Bug:** F8 (margem == custo sem warning), F32 (rerun após salvar preço).
- **Salvar preço:** funciona, invalida cache.

### Produção
- **Empty state:** `tamanhos.empty → st.stop` ✔ (linha 43).
- **Edge cases:**
  - Fornada vazia (todos produzidos=0) — só desabilita o botão (filter
    `if produzidos > 0` em 123). ✔ (F11).
  - Vendidos > produzidos — st.error mas **não bloqueia o submit** (F10).
- **Deletar fornada:** ❌ não existe (F9).
- **Inconsistência visual:** usa `st.dataframe` na agregação mensal (linha 256)
  e cards (`st.container(border=True)`) no histórico. **Sem padrão st.table.**
- **Cache invalidation:** ✔.

### Compras
- **Empty state:** `if compras.empty: st.info + st.stop` ✔.
- **Inconsistência visual:** usa `st.dataframe` em três tabelas (linhas 92, 104,
  186). Devia ser `st.table` pra ficar consistente (F1).
- **Frete e desconto não exibidos:** F2.
- **Edit/Delete de Compras:** não existe. OK se imutável é o padrão.
- **Filtros:** funcionais.

### Fornecedores
- **Empty state:** `if forns.empty: st.info + st.stop` ✔.
- **Padrão view/edit toggle:** ❌ não segue (F1). Edita direto no expander.
- **Delete:** confirm two-step ✔. Aviso "compras vão ficar órfãs" ✔.
- **Edge cases:** criar sem nome bloqueia ✔. Validação dupla de nome? Não.

### Receitas
- **Empty state:** `if not data._has_sheet("Receitas"): st.stop` ✔ (pre-migration
  guard). `if receitas.empty: st.info` ✔.
- **Toggle view/edit:** ✔ por receita (`rec_edit_mode_{receita_id}`).
- **State key prefixado:** ✔.
- **Cancelar edição:** limpa pending_adds mas não limpa o data_editor state (F23).
- **Deletar receita padrão:** ✔ bloqueado (F6 caso edge: única receita).
- **Receita sem ingredientes:** F33 — aceita sem aviso.
- **Bug encontrado:** F4 (custo não atualiza inline), F5 (clear_on_submit=False),
  F6 (caso edge), F23.
- **Auto-include relacionados:** funciona (linha 444-456 em Tamanhos page) — não
  aparece em Receitas. Tá certo? Embalagens é onde faz sentido.

### Clientes
- **Empty state:** `if not data._has_sheet("Clientes"): st.stop` ✔. `if clientes.empty:
  st.info + st.stop` ✔.
- **Toggle view/edit:** ✔.
- **CLI-000 protegido:** ❌ NÃO IMPLEMENTADO (F15). O código permite excluir CLI-000.
- **Vendas órfãs:** F15 — não checa antes de deletar.
- **Novo cliente sem nome:** bloqueia ✔.

### Vendas
- **Empty state:** múltiplos `st.stop` (clientes vazio, tamanhos vazio) ✔.
- **Toggle view/edit:** N/A — histórico imutável.
- **`resolve_preco_unit` retorna 0:** F19/B3 — sem aviso explícito.
- **Lucro com custo cravado:** F28 — comportamento aceitável.
- **Venda cancelada:** F29 — sem destaque visual no histórico.
- **Cliente desativado no histórico:** F17.
- **Cache invalidation:** ✔.

### Preços
- **Empty state:** `if not data._has_sheet("Precos"): st.stop` ✔. `if precos.empty:
  st.info + st.stop` ✔ (com fallback).
- **Toggle view/edit:** ✔.
- **Duplicação de faixa via edit:** F20 — bug.
- **B2B mais caro que B2C:** F18 — sem detect.
- **Preço negativo:** bloqueado ✔.

---

## Resumo executivo

**Blockers (corrigir antes de usar):** B1 a B5 listados acima. O mais sério é
**F15** (deletar CLI-000 + vendas órfãs) e **B5** (rename de produto não propaga
nome para receitas).

**Top 5 flags priorizados:**
1. F15 — Clientes: proteger CLI-000, bloquear delete com vendas referenciando.
2. F2 — Compras: exibir frete/desconto.
3. F20 — Preços: bloquear duplicação ao editar.
4. F10 — Produção: bloquear submit com vendidos>produzidos.
5. F9 — Produção: adicionar delete de fornada.

**Inconsistências de padrão de visual:**
- `st.dataframe` ainda usado em Home, Compras, Produção. Migrar pra `st.table`.
- Fornecedores não segue o padrão view/edit toggle.
- Vendas e fornadas históricas são read-only sem affordance pra editar/deletar.

**Sinais positivos:**
- Cache invalidation consistente em todos os writes.
- State keys prefixados por ID corretamente em Tamanhos e Receitas.
- Confirm two-step pra destruction em todas as deletes (exceto o caso CLI-000).
- Mobile CSS bem cobre os novos arquivos via media queries do `ui.py`.
- Critical-changes confirm checkbox em Insumos é um padrão sólido — vale
  replicar pra outras páginas (e.g., mudar tipo de cliente, mudar tamanho_id
  em uma faixa de preço).
