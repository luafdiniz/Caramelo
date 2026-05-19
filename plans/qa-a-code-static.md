# QA Code Static Analysis — 2026-05-19

Análise estática completa do código (`app/`, `bot/`, `scripts/`). NÃO foi rodado nada — só leitura.

---

## 🛑 BLOCK (impede uso / crash / corrompe dados)

### B1. `migrate_categoria.py` corrompe Produtos e perde referências em Receita_Ingredientes

`scripts/migrate_categoria.py` é a ferramenta de remapeamento entre categorias (foi usada hoje pra mover EMB-008/009/010/011/018 → GRA). Tem três bugs graves se rodada de novo:

- **Linha 86, 211**: lê e limpa `Produtos!A:F`. Mas Produtos hoje tem **A:H** (G=Preco_manual, H=Preco_manual_data — adicionados em `migrate_produtos_preco_manual.py`). Resultado: ao migrar, o override manual de um insumo é **silenciosamente perdido** (não é copiado pra nova linha, e a linha antiga é limpa em A:F mas G:H ficam lá órfãs apontando pra ID inexistente).
- **Linha 170**: ao criar a nova linha do produto migrado, só escreve `[new_id, nome, unidade, notas, relac, marca_pd]` (6 colunas). `preco_manual` / `preco_manual_data` não são copiados.
- **Receita_Ingredientes**: o script **não atualiza** referências em `Receita_Ingredientes!B` (produto_id). Receitas que usem o ingrediente migrado vão apontar pra um ID que não existe mais → cálculo de custo zera silenciosamente.

Impacto retroativo: como os EMB→GRA de hoje envolveram embalagens (não ingredientes), provavelmente Receita_Ingredientes não foi afetado **desta vez**. Mas o override manual pode ter sido perdido em qualquer EMB que estava com `preco_manual` setado.

### B2. `consolidate_compras.py` quebra com a nova largura de Compras / Produtos

`scripts/consolidate_compras.py` tem ranges hard-coded antigos:

- **Linha 54**: `PRODUTOS_RANGE = "Produtos!A:F"` — deveria ser `A:H` (preco_manual/preco_manual_data hoje, podem virar G/H).
- **Linha 259**: `Compras!A{rn}:K{rn}` ao limpar uma compra mesclada — deveria ser `A:M` (L=frete, M=desconto adicionados em `migrate_compras_frete.py`). Limpar até K deixa **lixo de frete/desconto em linhas zumbis**.
- **Linha 287**: `Produtos!A{rn}:F{rn}` ao limpar produto órfão — mesma história, deveria ser A:H.
- **Sem update em Receita_Ingredientes**: se um produto deletado estava em Receita_Ingredientes, a referência fica órfã (igual ao bug B1).

### B3. Orchestrator do bot não tem GRA em vários lugares

Bot foi parcialmente atualizado pra GRA. Estes caminhos ainda quebram quando o usuário cria/edita um produto GRA via Telegram:

- **`bot/lib/orchestrator.py:364`** — `_cat_order = {"ALI": 0, "FOR": 1, "EMB": 2, "EQP": 3, "OPR": 4}`. Falta GRA. Produtos GRA vão pro fim da lista (com chave 99) — não crasha mas mostra fora de ordem.
- **`bot/lib/orchestrator.py:435`** — whitelist de criação `if parts[3] in ("ALI", "FOR", "EMB", "EQP", "OPR")`. Se Gemini classificar como GRA e o usuário clicar "Cadastrar como GRA", o `parts[3] == "GRA"` **não bate**, cai no `else` que pega `item.get("categoria")` — funciona por acaso porque Gemini já preenche "GRA", mas qualquer hard-coded handler novo vai falhar. Mais sério: **não tem botão "Cadastrar como GRA"** no menu `is_outro` (linhas 738-756). Se Gemini errar e classificar um adesivo como OUTRO, o usuário só consegue forçar ALI/EMB/EQP/OPR.
- **`bot/lib/orchestrator.py:685-691`** — `CATEGORIA_LABEL` não tem chave GRA. Linha 746-749 usa `CATEGORIA_LABEL['ALI']/['EMB']/['EQP']/['OPR']` → se um dia for adicionado `CATEGORIA_LABEL['GRA']` aqui mas a lista de botões não, fica inconsistente.
- **`bot/lib/orchestrator.py:1249-1255`** (`CATEGORIA_PICK_BUTTONS` do /novo) — só tem ALI/FOR/EMB/EQP/OPR. **Usuário não consegue criar produto GRA via `/novo`**. Mesma lista é reusada em `_ask_compra_categoria_filter` (linha 1407) → não dá pra filtrar Compras por GRA no fluxo `/compra`.

Resultado prático: GRA funciona pelo app web, mas pelo bot ainda é cidadão de segunda classe.

### B4. Bot `create_produto` ignora `unidade` ao escrever na planilha

`bot/lib/sheets.py:155-160`:

```python
service.spreadsheets().values().update(
    spreadsheetId=spreadsheet_id,
    range=f"Produtos!A{next_row}",
    valueInputOption="USER_ENTERED",
    body={"values": [[new_id, nome, unidade, notas]]},
).execute()
```

A assinatura aceita `unidade: str = "UN"` (linha 139), mas ao escrever só usa A:D (id/nome/unidade/notas) — OK, parece bom. **Porém**: o docstring na linha 138 (comentário sobre categorias válidas) ainda diz `"ALI", "FOR", "EMB", "EQP"` — GRA e OPR foram adicionados na whitelist (linha 144) mas o comentário ficou desatualizado. Só docstring stale — não crasha.

---

## ⚠️ FLAG (não crítico mas precisa atenção)

### F1. `latest_unit_price` (deprecated) ainda usado em produção

`data.latest_unit_price` está marcado como deprecated na linha 575 de `app/lib/data.py` ("Use current_unit_price"). Mas ainda é chamado em:

- `app/pages/7_📜_Receitas.py:130, 267, 363` (3 chamadas)
- `app/pages/1_🍮_Tamanhos.py:362, 372` (2 chamadas)

Como `latest_unit_price` apenas delega pra `current_unit_price` (linha 577), o comportamento é o mesmo — mas o nome confunde quem lê o código ("será que ignora override manual?"). Trocar todas as ocorrências por `current_unit_price` e remover o wrapper.

### F2. Compras page não mostra frete/desconto

`app/pages/5_🛒_Compras.py` lê `data.get_compras()` (que já retorna `frete` e `desconto`), mas a tabela de histórico (linha 175-186) e o drill-down (192-208) **não exibem** as colunas. Para uma compra com frete rateado, o usuário não consegue ver de onde veio o ajuste — só vê o `preco_total` final já mexido.

Também: o resumo mensal (linha 65) usa `preco_total` que JÁ inclui o rateio. Ao agregar gastos totais por mês, isso está correto. Mas o KPI "Total gasto" não diferencia gasto bruto de gasto com frete (perde insight tipo "gastei R$ 120 só em frete esse mês").

### F3. NF-e XML não extrai frete/desconto

`bot/lib/nfe_xml.py:172-179` (`parse_nfe_xml`) retorna o dict sem chaves `frete`/`desconto`. Como o orchestrator depois faz `float(payload.get("frete") or 0)` (orchestrator linha 885, 504, etc.), `0` é o fallback — não crasha, mas NF-e que tem `vFrete` e `vDesc` no `ICMSTot` perdem essa informação. Frete só é capturado por foto/PDF (via Gemini) ou se o usuário editar manualmente via `editfd`.

NF-e tem esses campos em `total/ICMSTot/vFrete` e `total/ICMSTot/vDesc`. Tem que adicionar a extração.

### F4. Bot/`create_compra` flow não captura frete nem desconto

`_handle_compra_callback` / `_handle_compra_text` (orchestrator 1501+) registra uma compra sem nota (`csave` em 1547) sem perguntar frete/desconto, e chama `append_compra` sem passar esses kwargs (linha 1545-1557). Pra uma compra de feira com taxa de entrega, o usuário precisa ir na planilha pra adicionar depois. Aceitável MVP, mas inconsistente com o fluxo de foto.

### F5. `state.py` — busca linear cara em todos os reads

`state.find_latest_active_state_id` e `load_state` puxam `_BotState!A:D` inteiro toda vez. Cada update do bot é ~4-6 chamadas dessas → cada interação do usuário lê o histórico inteiro de estados várias vezes. Funciona com volume baixo mas vai degradar. O state nunca é purgado (linhas marcadas `CONSUMED` ficam pra sempre).

### F6. `consolidate_compras.py` clear de Aliases A:F está correto, mas...

Aliases tem 6 colunas (A:F: ID, tipo, texto_original, resolved_id, created_at, pack_size). O script limpa A:F (correto). OK aqui.

### F7. orchestrator faz `editMessageText` direto via `requests` em vez de usar `tg.edit_message_text`

`bot/lib/orchestrator.py:235-247, 305-317, 374-389` — 3 lugares fazem `_req.post(editMessageText, ...)` direto pra usar `reply_markup` com `inline_keyboard`. O cliente `tg.edit_message_text` já aceita `reply_markup` como dict (telegram_client.py:69, 79-80), então essas 3 chamadas inline podem ser substituídas por uma chamada limpa ao cliente abstraído. Não quebra nada, mas é dívida.

### F8. Race condition leve no toggle view/edit do Insumos (Tabela)

`app/pages/2_📦_Insumos.py:311-340`: o `ins_tabela_edit_mode` é uma chave de session_state global (não scoped por insumo, porque é tabela única). Quando salva (linha 631+) só faz `data.invalidate_cache()` + `st.rerun()`, **sem resetar `ins_tabela_edit_mode = False`**. Resultado: depois de salvar, fica em modo edit com a tabela já refletindo os novos valores → segundo Salvar dispararia sem mudanças (debounce ruim mas não destrutivo). Comparar com Receitas/Clientes/Precos que resetam o flag explicitamente.

### F9. Vendas page lê `vendas` antes de checar se a aba existe

`app/pages/9_💰_Vendas.py:35-44`: faz `vendas = data.get_vendas()` na linha 35, depois verifica `if not data._has_sheet("Vendas")` na linha 39. Como `get_vendas` já trata sheet inexistente (retorna empty DF), funciona, mas é uma chamada extra ao Sheets desnecessária. Trocar a ordem.

Mesma coisa em `8_👥_Clientes.py:36/38`.

### F10. `Tamanhos!I` (receita_id) — leitura defensiva, escrita condicional

`app/lib/data.py:140` lê `Tamanhos!A2:I` (9 colunas com receita_id). OK.

`app/pages/1_🍮_Tamanhos.py:480-486` escreve `Tamanhos!I{row_num}` SOMENTE se `not receitas_df.empty`. Pré-migração: a coluna I não existe ainda, escrita seria criar a coluna com um único valor. Defensiva OK.

`app/pages/1_🍮_Tamanhos.py:734-742` (criar novo tamanho) escreve linha completa A:H — **NÃO escreve I**, mesmo se houver Receitas. Não é bug porque empty significa "usa padrão" via `resolve_receita_id_for_tamanho`, mas é inconsistente: usuário não consegue selecionar receita na hora de criar (só na edição depois).

### F11. `create_spreadsheet.py` cria Produtos com header de 4 colunas

`scripts/create_spreadsheet.py:259-263` ainda cria a aba Produtos com `["ID", "Nome", "Unidade", "Notas"]` (4 cols). Falta E (Relacionados), F (marca_padrao), G (preco_manual), H (preco_manual_data). Se alguém usar esse script pra bootstrapar uma planilha nova e tentar rodar o app, o app vai funcionar (loaders são defensivos) mas todas as migrations precisam rodar depois pra adicionar os headers. Documentar ou atualizar o script.

### F12. `relacionados` (Produtos!E) — nunca aparece como editável no app

Coluna E de Produtos é `relacionados` (lista CSV de produto_ids relacionados, usada pra auto-incluir embalagens — Tamanhos.py:444-456). É lida em `bot/lib/sheets.py:51-52`, mas **não há UI** pra editar isso (Insumos.py edita B,C,D,F mas pula E). Só pode ser editado direto na planilha. Documentar ou criar UI.

### F13. `aliases.save` retorna `""` em colisão sem feedback do motivo

`bot/lib/aliases.py:131-145`: se o usuário tinha um alias "AÇÚCAR REFINADO" → `ALI-005` e agora tenta salvar `ALI-007` pro mesmo texto, retorna `""` sem reportar a colisão. O caller (orchestrator) interpreta retorno vazio como "alias já existia" e não mostra aprendizado. Mas se o motivo for "resolução diferente já registrada" (linha 135), o usuário pode estar confuso ("editei mas não aprendeu?"). Pelo menos logar.

### F14. `update` em Receitas usa range incorreto se padrao mudou

`app/pages/7_📜_Receitas.py:486-491` escreve `Receitas!B{rn}:C{rn}` (Nome, Padrao) — OK. Depois chama `_ensure_single_padrao` (493) que itera por todas as receitas escrevendo `Receitas!C{sheet_row}` uma por uma. Funciona, mas o `bool(new_padrao)` no body já garantiu o valor — o `_ensure_single_padrao` é redundante pra essa linha, gasta uma chamada extra. Pequeno otimização.

### F15. Precos editor: `disp.iloc[i].name + 2` quebra se Precos tem linha em branco no meio

`app/pages/10_💸_Precos.py:148`: `sheet_row = (orig_row.name + 2)`. `orig_row` vem de `disp.iloc[i]` (post-sort) que veio de `precos.copy()` — mas `data.get_precos()` filtra linhas com `tamanho_id` vazio e faz `reset_index(drop=True)`. Resultado: o `.name` é o índice 0..N-1 SEM os gaps, mas a planilha real pode ter linhas em branco intercaladas. Editar/deletar uma faixa pode atingir a linha errada.

Defesa simples: depois de `data.get_precos()` retornar, reler a planilha bruta e mapear `tamanho_id+tipo_cliente+qtde_min → sheet_row`, igual `find_row_by_id`.

---

## ✅ PASS

- `app/lib/data.py` — schema reading bate com migrations:
  - `get_produtos` range A:H, get_compras A:M, get_tamanhos A:I, get_receitas A:D, get_receita_ingredientes A:F, get_clientes A:J, get_vendas A:L, get_precos A:E. Todos consistentes com os headers escritos pelas migrations.
  - Shim pré-migração funcional (`_has_sheet`, fallback REC-001) e marcadamente comentado pra remoção futura.
- `app/lib/calc.py` — solvers puros, lógica testável, warnings sãos.
- `app/lib/ui.py` — helpers (`brl`, `pct`, `qty_fmt`, `compact_kpi`, `card_title`) escapam HTML user-controlled antes de injetar via markdown — sem XSS.
- `bot/lib/sheets.distribute_frete_desconto` — rateio proporcional bem implementado, com fallback pra split igual quando subtotal=0 e ValueError quando desconto > total (cobre o edge case crítico de desconto maior que compra).
- `bot/lib/gemini.py` — SYSTEM_PROMPT e TEXT_PROMPT ambos têm GRA na lista de categorias com regra clara ("adesivo e etiqueta sempre vão em GRA").
- `bot/lib/orchestrator._finalize` — chama `distribute_frete_desconto` antes do append, persiste frete+desconto em CADA linha do batch (auditoria), e exibe mensagem de erro amigável quando o rateio falha.
- `bot/lib/orchestrator.handle_text_hint` — dispatches todos os states `awaiting_*` (pack_size, text_for_item, frete_desconto) + flows /novo + /compra.
- `bot/lib/orchestrator.handle_callback` — dispatches `editfd`, `save`, `cancel`, `iredo`, `iedit`, `voltar`, `fuse/fpicklist/fpick/fback/fcreate`, `ipicklist/ipick/iback/iuse/icreate/iskip/ihint`, `psize`, `ncat/nuni/ncreate`, `cfcat/cback_cat/cprod/cforn/csave`. Cobertura completa.
- State persistence (`bot/lib/state.py`) — save/delete em torno de cada step, mantém histórico consumido em vez de remover (auditoria).
- Padrão view/edit toggle nas tabelas (Insumos, Clientes, Vendas, Precos, Receitas, Tamanhos.emb) — implementação consistente: flag em session_state, botão "Editar" → flag=True, save reseta flag (exceto Insumos — ver F8).
- `scripts/migrate_*.py` — todos têm dry-run default, idempotência detectada (header check), confirmação tty antes de aplicar.
- HTML escaping (`_esc` no orchestrator, `_esc_html` no ui.py) usado consistentemente antes de inserir conteúdo de usuário em mensagens HTML.

---

## 📋 Detalhes por área

### Schema consistency

| Tab | Migration cria | data.py lê | sheets.py lê (bot) | Status |
|---|---|---|---|---|
| Produtos | A:H (preco_manual added by migrate_produtos_preco_manual.py) | A:H (get_produtos via _sheets.get_produtos) | A:H | ✅ |
| Compras | A:M (frete/desconto added by migrate_compras_frete.py) | A:M (get_compras) | append_compra writes A:M | ✅ |
| Tamanhos | A:I (receita_id added by migrate_receitas.py) | A:I (get_tamanhos) | n/a | ✅ |
| Receitas | A:D (created by migrate_receitas.py) | A:D (get_receitas) | n/a | ✅ |
| Receita_Ingredientes | A:F | A:F (get_receita_ingredientes) | n/a | ✅ |
| Clientes | A:J (created by migrate_clientes_vendas.py) | A:J (get_clientes) | n/a | ✅ |
| Vendas | A:L | A:L (get_vendas) | n/a | ✅ |
| Precos | A:E | A:E (get_precos) | n/a | ✅ |
| Embalagens_Por_Tamanho | A:D | A:D | n/a | ✅ |
| Fornadas | A:M | A:M | n/a | ✅ |
| Fornecedores | A:E | A:E | A:E | ✅ |
| Aliases | A:F | n/a | A:F | ✅ |

**Stale ranges em scripts** (não migrations):
- `consolidate_compras.py:54` PRODUTOS_RANGE = "Produtos!A:F" → deve ser A:H. **BLOCK B2.**
- `consolidate_compras.py:259, 287` clears com A:K, A:F → devem ser A:M, A:H. **BLOCK B2.**
- `migrate_categoria.py:86` produtos range A:F + linha 211 clear A:F → A:H. **BLOCK B1.**
- `migrate_categoria.py:170` nova linha só escreve 6 colunas → falta G/H. **BLOCK B1.**

### Imports / refs

- `data._sheets.create_produto` (Insumos.py:239) — assinatura confere com `bot/lib/sheets.py:135` (categoria, unidade, notas, service).
- `data._sheets.create_fornecedor` (Fornecedores.py:209) — confere.
- `data._sheets._next_id_for_prefix` chamado em Tamanhos.py:727, Produção.py:172, Receitas.py:684 — função pública na interface, OK.
- `sheets.append_compra` chamado em orchestrator.py:924 (com frete+desconto) e 1547 (sem) — assinatura tem defaults `frete=0.0, desconto=0.0`, ambas compatíveis.
- `latest_unit_price` ainda usado em 5 lugares mesmo sendo deprecated — ver F1.

### GRA categoria

Cobertura de GRA por arquivo:

| Arquivo | GRA OK? | Detalhes |
|---|---|---|
| `bot/lib/sheets.py:144` | ✅ | Whitelist tem GRA. |
| `scripts/migrate_categoria.py:41` | ✅ | VALID_CATEGORIAS inclui GRA. |
| `bot/lib/gemini.py` SYSTEM_PROMPT | ✅ | linha 31, 52-58. |
| `bot/lib/gemini.py` TEXT_PROMPT | ✅ | linha 157, 175. |
| `app/pages/2_📦_Insumos.py` CAT_EMOJI/LABEL/TAB | ✅ | linhas 70-88. |
| `app/pages/1_🍮_Tamanhos.py:339, 667` _cat_order embalagens | ✅ | Tem GRA. |
| `bot/lib/orchestrator.py:364` _cat_order item picklist | ❌ | **Falta GRA.** Block B3. |
| `bot/lib/orchestrator.py:435` whitelist criar OUTRO→cat | ❌ | **Falta GRA.** Block B3. |
| `bot/lib/orchestrator.py:685-691` CATEGORIA_LABEL | ❌ | **Falta GRA.** Block B3. |
| `bot/lib/orchestrator.py:1249-1255` CATEGORIA_PICK_BUTTONS (/novo + /compra) | ❌ | **Falta GRA.** Block B3. |

### Dead code

- Nenhum TODO/FIXME no projeto.
- `latest_unit_price` (data.py:575) — deprecated, mas ainda referenciado (F1). Não é dead, é stale.
- `bot/lib/sheets.py:138` comentário diz "ALI, FOR, EMB, EQP" — desatualizado em relação à whitelist (B4).
- `app/pages/9_💰_Vendas.py:35-37` lê vendas/clientes/tamanhos antes da verificação `_has_sheet("Vendas")` (F9). Reads redundantes na primeira execução pré-migração.
- `Bot do Telegram para Pudim Caramelo.rtf`, `Caramelo-bot-key_caramelo-v2-692ac2b31508.json`, `Screenshot 2026-05-12 at 13.17.14.png`, `vercel-recovery-codes.txt` — arquivos no root que provavelmente não deveriam estar versionados. **Particularmente o JSON de service account é credencial sensível em arquivo separado** — verificar se está no .gitignore e nunca foi commitado. (Fora do escopo de QA de código, mas worth flagging.)

### View/edit pattern

| Tabela | Reset session_state ao salvar | Estado scoped | Status |
|---|---|---|---|
| Insumos Tabela (Insumos.py:311) | ❌ não reseta `ins_tabela_edit_mode` ao salvar | Global | F8 |
| Receitas (Receitas.py:282 `rec_edit_mode_<id>`) | ✅ linha 540 | Por receita | OK |
| Tamanhos embalagens (Tamanhos.py:213) | ✅ linha 529 | Por tamanho | OK |
| Clientes (Clientes.py:115) | ✅ linha 228 | Global (uma tabela só) | OK |
| Precos (Precos.py:100) | ✅ linha 189 | Global | OK |

Não vi leakage de session_state entre receitas/clientes/produtos diferentes — todas as chaves de pending state (`pending_add_<receita_id>_<comp>`, `_auto_added_<tam_id>`, `confirm_del_*`, `add_pkg_<tam_id>`, etc.) são scoped por id.

### Bot orchestrator

- `_finalize` (linha 879) — chama `distribute_frete_desconto`, trata ValueError com mensagem amigável, passa frete/desconto em cada `append_compra`. ✅
- `handle_text_hint` (linha 986) — cobre awaiting_pack_size, awaiting_text_for_item, awaiting_frete_desconto, /novo (name+unidade_custom), /compra (qtde+preco). ✅
- `editfd` (linha 502) — abre fluxo, marca `awaiting_frete_desconto=True`, persiste estado. `_handle_frete_desconto_text` (1022) parseia `frete/desconto`, valida (não-negativos), chama `_ask_final` de novo. ✅
- State persistence — cada step faz `state.delete_state` + `state.save_state` em sequência. Pra Sheets-backed state isso é OK (atômico do ponto de vista do Telegram); pra alta concorrência seria race, mas o bot é single-tenant.
- `start_compra_flow` salva payload sem capturar o `state_id` retornado, depois chama `_ask_compra_categoria_filter` que chama `find_latest_active_state_id` (extra read). Pequena ineficiência.

---

## Resumo executivo

3 BLOCKs reais — todos em scripts (B1, B2) e no fluxo bot pra produtos GRA (B3). A camada web (`app/`) está consistente; a camada bot tem GRA pela metade. As migrations + schema readers em `data.py` estão alinhados. Comprou-se dívida moderada com a deprecação de `latest_unit_price` (F1) e a falta de exibição de frete/desconto na página de Compras (F2). Nada que impeça o uso diário do app web — mas re-rodar `migrate_categoria.py` ou `consolidate_compras.py` AGORA pode silenciosamente perder overrides manuais e quebrar referências.
