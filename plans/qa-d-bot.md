# QA Bot — 2026-05-19

Auditoria end-to-end do bot Telegram (`bot/`) após mudanças de frete/desconto, categoria GRA e leitura A:H de Produtos. Sem edits — só leitura + tests.

Convenção: nomes reais dos arquivos são `bot/lib/telegram_client.py` (não `tg.py`) e `bot/lib/nfe_xml.py` (não `nfe.py`). O `state.py` existe e é uma aba `_BotState` na planilha. O briefing usou nomes curtos — só pra constar.

---

## 🛑 BLOCK

Nada que justifique parar deploy. O caminho feliz (foto → Gemini → review → save com frete/desconto) funciona end-to-end, os 25 asserts de `test_nfe_xml.py` passam, e o webhook protege chat_id antes de qualquer parser rodar.

---

## ⚠️ FLAG

**F1 — Categoria GRA não está plumbada na UI, só no backend.**
- `bot/lib/sheets.py:144` aceita `"GRA"` em `create_produto`.
- `bot/lib/gemini.py` (SYSTEM_PROMPT e TEXT_PROMPT) explicitamente classifica adesivo/etiqueta como GRA.
- **Mas** a whitelist do callback `icreate` (`bot/lib/orchestrator.py:435`) só aceita `("ALI", "FOR", "EMB", "EQP", "OPR")` quando a categoria vem pelo botão. Quando Gemini classifica como GRA e a confiança é alta, o caminho da linha 438 (`item.get("categoria")`) deixa passar — então o auto-create funciona. O problema é quando o item é OUTRO ou quando o usuário quer manualmente forçar GRA: o menu de "Cadastrar como…" (linhas 743-749) só oferece ALI/EMB/EQP/OPR. Não há botão "Cadastrar como GRA".
- Mesmo gap em `CATEGORIA_PICK_BUTTONS` (`bot/lib/orchestrator.py:1249-1255`), usado por `/novo` e `/compra` — não dá pra cadastrar produto GRA pelo bot.
- `_cat_order` no `ipicklist` (`bot/lib/orchestrator.py:364`) não lista GRA → produtos GRA aparecem por último (sem prefixo conhecido, vão pro bucket 99).
- Resultado prático: 5 produtos GRA migrados ficam visíveis no `ipicklist` (no fim da lista) e em `/compra` se o usuário escolher a categoria EMB ou se Gemini classificar exatamente como GRA. Mas não dá pra criar um produto GRA novo pela UI.

**F2 — Whitelist de `create_produto` aceita "OPR" mas a docstring ainda diz ALI/FOR/EMB/EQP.**
`bot/lib/sheets.py:138` (docstring) está desatualizada. `bot/lib/sheets.py:144` aceita os 6 prefixos corretos. Cosmético, mas confunde leitura.

**F3 — `distribute_frete_desconto` arredondamento sem snap pro centavo.**
`bot/lib/sheets.py:248` retorna floats Python (`raws[i] + ajuste_total * pesos[i]`). Vai pra `append_compra` que escreve direto na coluna I. Para frete 8 / 3 itens, vai dar 2.6666666… na planilha. Sheets formata visualmente como R$ 2,67, mas a célula guarda o float cheio. Quando alguém somar manualmente vai ter erro de fracionamento de centavo. Não bloqueia, mas idealmente arredondar pra 2 casas (`round(x, 2)`) com correção do último item pra fechar a soma com `subtotal + frete - desconto`.

**F4 — Botão "Editar frete/desconto" não tem "Voltar" no prompt.**
`bot/lib/orchestrator.py:502-516`: ao clicar editfd, edita a mensagem e zera o keyboard. Se o usuário desistir, ele tem que mandar `/cancel` ou digitar algo válido. Não é fatal porque o resumo continua acessível com `0/0`, mas é menos ergonômico que outros pontos do fluxo.

**F5 — `awaiting_frete_desconto` não é limpo se o usuário clicar `cancel:` antes de mandar o texto.**
A flag fica no payload, mas como o state inteiro é deletado em `cancel`, na prática não tem leak. Só anotando porque outros `awaiting_*` recebem `payload.pop(...)` explícito.

**F6 — `_resolve_forn_name` e `_get_produto_unidade` chamam `sheets.get_service()` sem passar o `service` já criado pelo caller.**
`bot/lib/orchestrator.py:1236` e `bot/lib/orchestrator.py:778`. Funciona, mas paga uma chamada HTTP extra desnecessária toda vez que o resumo final é renderizado ou cada vez que pack_size é pedido. Em runtime serverless, isso conta latência.

**F7 — `test_parser.py:84` referencia `orchestrator.format_receipt_summary` que não existe mais.**
Foi renomeado pra `_format_overview` (privado, com underscore). O script crasha se chegar nessa linha — basicamente teste morto. Não afeta produção mas dá impressão errada de "tests existem".

**F8 — Nenhum teste cobre `distribute_frete_desconto`.**
Função nova, com ramo de erro (`ValueError`), edge cases de subtotal=0 e divisão proporcional. Zero unit tests. Daqui pra frente é o ponto onde mais provavelmente vai aparecer bug numérico.

**F9 — `unidade = "UN"` hardcoded em `icreate`.**
`bot/lib/orchestrator.py:441`: quando o bot cria produto na hora do fluxo de revisão de nota, força `unidade=UN`. Pra ovos, açúcar a granel, leite, etc. não é o ideal. O fluxo `/novo` pergunta unidade certinho, mas o `icreate` no meio da revisão de foto não.

**F10 — `_apply_pack_size` mostra `qtde × n = total un` mesmo quando `qtde` veio fracionada (ex: 1.5).**
Linha 547: `int(qtde) if qtde == int(qtde) else qtde` — funciona, mas é casa pra confusão visual com qtdes não-inteiras de NF-e (ex: kg). Não viu blocker, só atenção.

**F11 — `find_latest_active_state_id` busca o mais recente sem distinguir flow.**
Se o usuário tem um fluxo `/compra` aguardando texto de "qtde" e manda uma foto, `handle_photo` chama `_start_review_flow` que cria um state NOVO — agora o chat tem dois states pendentes. `handle_text_hint` pega o mais recente (foto) e responde como se fosse o awaiting_pack_size dela. Pode confundir. Mitigação atual: `/novo` e `/compra` chamam `delete_state(old_id)` no início — mas `handle_photo` / `handle_document` / `handle_text_receipt` NÃO. Múltiplos receipts em paralelo ficam pendurados na planilha como CONSUMED-quando-resolvidos, ou pra sempre se o usuário abandonar. Sem cleanup automático.

**F12 — `handle_text_hint` é chamado ANTES de tentar `incluir N`.**
`bot/api/webhook.py:111-127`: se houver state pendente com `awaiting_pack_size_for_item`, e o usuário mandar `incluir 3`, vai cair em `_handle_pack_size_text` (que falha o parse de int, manda "Digite um número") em vez de re-revivir o item 3. Não é bug grave porque pelo menos o usuário vê mensagem, mas a ordem é "estranho-amigável" — text hint primeiro, comandos depois.

**F13 — Erros do webhook expõem o conteúdo da exceção na mensagem do chat.**
`bot/api/webhook.py:42, 63, 93, 99, 104, 113, 124, 135, 164`: todos fazem `f"❌ Erro: <code>{e}</code>"`. Se a exception incluir secrets (improvável mas possível em traceback do googleapi com URL assinada, ou no Gemini SDK), vai parar na conversa. O `chat_id` é whitelistado então pelo menos não vaza pra fora — mas globalmente o pattern é "não logar conteúdo de exceção em destino do usuário". Recomendação: mostrar `type(e).__name__` ou string genérica e logar o detalhe via `traceback.print_exc()` (que já está sendo feito).

---

## ✅ PASS

- **Tests `test_nfe_xml.py`** rodaram com **25 passed, 0 failed**. Cobrem layout 3.10/4.00, root `<nfeProc>` e `<NFe>`, XML inválido, XML totalmente quebrado.
- **Webhook valida `chat_id`** contra `TELEGRAM_ALLOWED_CHAT_IDS` antes de qualquer processamento. Resposta direta `"⛔ Não autorizado"` quando bloqueia. Sem whitelist = aberto (intencional, documentado).
- **Todos os `tg.send_*` usam `parse_mode="HTML"`.** Nenhum Markdown. Caractere `_` em texto não corrompe (regra do CLAUDE.md respeitada).
- **`sheets.get_service`** detecta JSON inline vs path com `creds_json.startswith("{")` — não passa env var direto pra `Path(...).is_file()`. A proteção do CLAUDE.md (Python 3.12 OSError leak) está honrada.
- **`_finalize` captura `ValueError` de `distribute_frete_desconto`** e edita a mensagem com texto amigável: `❌ Não consegui salvar essa compra: Desconto (R$ X) maior que o total… Edita os valores e reenvia.` (`bot/lib/orchestrator.py:913-919`).
- **`_handle_frete_desconto_text` parser** aceita os 3 formatos do briefing: `"8/0"`, `"15,50 / 5"`, `"0/0"`. Vírgula vira ponto, spaces tolerados, max(0, x) força não-negativo.
- **`aliases.save` protege contra sobrescrita divergente** (`bot/lib/aliases.py:135-137`): "Different resolution recorded earlier — keep history, don't overwrite." Quando o usuário troca um texto pra produto diferente, o save retorna `""` (sem aprender) e a memória anterior sobrevive — é o behavior esperado em `iredo` (que ANTES deleta o alias antigo via `aliases.delete`).
- **`iredo` deleta o alias antigo** (`bot/lib/orchestrator.py:196-201`) usando `original_descricao` se disponível. Tem `try/except` defensivo. Bem feito.
- **`_BotState`** tab é criada com `hidden=True` (`bot/lib/state.py:37`) — não polui a visão da planilha.
- **Cada step de fluxo (`/novo`, `/compra`, revisão) chama `state.delete_state` + `state.save_state` no transition**, garantindo persistência atômica. Reload da conversa retoma de onde parou.
- **`cancel:state_id`** funciona em qualquer ponto (`bot/lib/orchestrator.py:169-173`), e cobre ambos os fluxos (foto, /novo, /compra) porque é processado antes da branch `flow == ...`.
- **Vercel routes** apontam pra `bot/api/webhook.py` corretamente (`vercel.json` root). O `bot/vercel.json` parece ser herança de quando a app era standalone — não afeta deploy de produção (Vercel usa o do root).
- **`requirements.txt` está mínimo e completo** pros imports que vejo: `google-genai`, `google-api-python-client`, `google-auth`, `requests`, `python-dotenv`, `rapidfuzz`. Todas usadas.

---

## 📋 Por área

### Fluxo de Compra

Fluxo: foto/PDF/XML/texto → `_start_review_flow` → `_format_overview` → `_next_step` loop (supplier → cada item product → cada item pack_size) → `_ask_final` → opcional `editfd` → `save`.

- **Voltar:** `voltar:state_id` desfaz última decisão (`_undo_last_decision`), prioridade pack_size > product. Botão aparece sempre que `_can_undo` (qualquer item resolvido). Limitação: NÃO desfaz decisão de fornecedor — uma vez `resolved_supplier_id` setado, não tem caminho de volta automático (só `cancel` ou esperar o `fback` que existe APENAS na tela de `fpicklist`).
- **State persiste em cada step:** confirmado em todas as branches de `handle_callback`.
- **Reentrar em callback velho:** tratado em `bot/lib/orchestrator.py:164-167` — payload `None` → "Esta confirmação já não está válida" + clear keyboard. Boa proteção.
- **`cancel:` em qualquer ponto:** funciona, processado antes do dispatcher `flow`.

### Frete/desconto

- **`_ask_final` mostra `Frete: R$ 0.00 · Desconto: R$ 0.00`** quando Gemini não extraiu (default `payload.get('frete') or 0`). Linha 859. OK.
- **Botão "🚚 Editar frete/desconto"** está em `_ask_final:870` — sempre renderizado, mesmo em `_can_undo == False`. Bom.
- **Handler `editfd`** marca `awaiting_frete_desconto=True`, persiste state, mostra prompt. **Sem botão "Voltar"** dentro do prompt (F4).
- **`_handle_frete_desconto_text`** parser cobre os formatos do briefing. Não há suporte explícito a `"frete 8 desconto 0"` ou números soltos — exige o `/` separator.
- **`_finalize` → `distribute_frete_desconto`:** rateio proporcional ao subtotal raw. Fallback equal-split quando subtotal=0 (todos os itens grátis + frete). Levanta `ValueError` quando algum item efetivo ficaria negativo. `_finalize` captura e mostra mensagem amigável.
- **Mensagem de sucesso** inclui `(frete R$ X ratado, desconto R$ Y)` quando aplicável (`bot/lib/orchestrator.py:942-950`). Bem feito.
- **Frete/desconto escrito em colunas L/M** de cada linha de Compras (`bot/lib/sheets.py:209-210`). Vazio quando 0 — não polui a planilha com `0.00` em toda compra.
- **Edge case:** itens com `action=skip` são excluídos do rateio (linha 899-900). Correto — só o que vai pra Compras absorve o rateio.

### Categoria GRA

- ✅ **Prompts Gemini mencionam GRA** explicitamente: SYSTEM_PROMPT linha 56, TEXT_PROMPT linha 175. Reforço de "adesivo e etiqueta sempre GRA, não EMB". Bom.
- ✅ **`create_produto` aceita "GRA"** (`bot/lib/sheets.py:144`).
- ✅ **Auto-create no fluxo de nota:** quando Gemini retorna `categoria="GRA"`, o `icreate` sem categoria-explícita pega via `item.get("categoria")` (linha 438) e cria como GRA. ✓
- ⚠️ **UI gaps (F1):**
  - Botão "Cadastrar como GRA" não existe em OUTRO menu.
  - `/novo` não permite escolher GRA.
  - `/compra` não permite filtrar por GRA.
  - `_cat_order` no `ipicklist` não ordena GRA → vai pro bucket 99 (fim da lista).
- ✅ **Sem lookups hard-coded que excluam GRA** em produtos cadastrados. `get_produtos` retorna tudo. Matcher não filtra por prefixo.

### State management

- ✅ **`awaiting_pack_size_for_item`:** setado em `psize:custom` (linha 488), limpo em `_handle_pack_size_text:1068`. Em caso de idx inválido, limpo em 1057 (bom).
- ✅ **`awaiting_text_for_item`:** setado em `ihint` (linha 472), limpo em `_handle_item_name_text:1100, 1108`.
- ✅ **`awaiting_frete_desconto`:** setado em `editfd` (linha 503), limpo em `_handle_frete_desconto_text:1045`. (F5: não é explicitamente limpo no `cancel`, mas `cancel` deleta o state inteiro então não vaza.)
- ✅ **`force_review`** respeitado em `_next_step:585` — pula auto-resolve de alias/skip/high-confidence quando `True`. Usado por `iredo` e `handle_include_command`. ✓
- ⚠️ **F11 acima:** múltiplos receipts em paralelo geram múltiplos states, `find_latest_active_state_id` pega só o último. Sem cleanup proativo no entry point de foto/document/text_receipt.

### Aliases

- ✅ **`aliases.delete` chamado em `iredo`** (linha 196-201) com `try/except` defensivo. Usa `original_descricao` se houver, senão `descricao` atual.
- ✅ **`aliases.save` não sobrescreve divergente** (linha 135-137). Comportamento documentado. Bom.
- ⚠️ Pequeno detalhe: o save em `iskip` (linha 461) usa `item.get("descricao", "")` em vez de `original_descricao` — se o usuário primeiro corrigiu o nome via `ihint` e DEPOIS skip, vai salvar alias do nome corrigido, não do texto original da nota. Consequência: se a mesma foto rodar de novo, o alias não casa (porque a nota vai trazer o texto original, não o corrigido). Pequeno, mas inconsistente com outras branches (iuse:423, ipick:401, icreate:449 que TODAS usam `original_descricao or descricao`).

### Webhook security

- ✅ **`_allowed_chat`** lê `TELEGRAM_ALLOWED_CHAT_IDS` env e valida ANTES de qualquer parser. Sem whitelist = passa tudo (mas pelo menos o `/whoami` responde com chat_id pro usuário se cadastrar).
- ✅ **Sempre retorna 200** (`bot/api/webhook.py:179-182`) — Telegram não fica fazendo retry quando algo falha internamente.
- ⚠️ **F13:** erros são mostrados ao usuário com `<code>{e}</code>` — exposição da string da exception. Whitelisted chat só, mas pattern não é ideal.
- ✅ **Não há logs imprimindo conteúdo de payload sensível** — `traceback.print_exc()` vai pro stderr (Vercel logs), não pra Telegram.

### Tests

- **`bot/tests/test_nfe_xml.py`** — 4 testes, 25 asserts. Rodaram: **25 passed, 0 failed**.
- **`bot/tests/test_parser.py`** — script manual que chama Gemini real. Não roda sem API key. Referencia `orchestrator.format_receipt_summary` que NÃO EXISTE mais (F7). Teste morto.
- **Coverage gaps óbvios:**
  - F8: `distribute_frete_desconto` sem nenhum teste. Edge cases: subtotal=0, frete>0/desconto=0, frete=0/desconto<subtotal, desconto>subtotal (raise), desconto=subtotal (boundary, item efetivo == 0 — passa, mas vale documentar).
  - `_handle_frete_desconto_text` parser sem teste (formatos válidos/inválidos).
  - `matcher.score` sem teste — função crítica de ranking.
  - `aliases.save` (branch divergente, pack_size update in-place) sem teste.
  - State machine: `_next_step`, `_undo_last_decision`, `_force_reask_item` sem testes.

### Vercel deploy

- ✅ **`/Caramelo/vercel.json`** aponta `bot/api/webhook.py` com `includeFiles: bot/lib/**`. Correto.
- ⚠️ **`bot/vercel.json`** existe mas é redundante — refere `/api/webhook.py` (sem prefixo `bot/`) e ainda menciona `whoami.py` que não existe mais. Se Vercel só lê o root, é dead config. Vale checar se algum sub-projeto deploy alternativo está usando.
- ✅ **`requirements.txt`** alinhado com imports reais. Não tem `pytest` (ok, testes são scripts).
- ⚠️ Edge case da memória — "Updating env vars in Vercel does NOT trigger redeploy": nenhuma mitigação no código (não dá pra mitigar isso pelo bot, é operacional). Vale anotar no README/CLAUDE.md do projeto.

### Edge cases

- ✅ **Telegram Markdown vs `_` unbalanced:** tudo HTML, não é problema.
- ✅ **Service account JSON Path leak (Python 3.12):** `sheets.get_service` usa `startswith("{")` + `open()`, não `Path.is_file()`. Seguro.
- ⚠️ **Vercel env var change → no redeploy:** sem mitigação no código (não é responsabilidade do bot).
- ⚠️ **NF-e XML grande:** `_strip_namespace` itera toda a árvore — pra notas com 100+ itens fica O(n) mas é fast o suficiente. Não testado em fixtures grandes.
- ⚠️ **Photo HEIC:** Gemini aceita, mas o sniff em `_sniff_mime` (`gemini.py:76`) não detecta HEIC magic bytes — cai no fallback `image/jpeg`. Funciona porque o caller força `mime_type="image/jpeg"` em `handle_photo`, mas se um dia for chamado sem hint, HEIC vai como jpeg (Gemini provavelmente ainda parseia, mas é frágil).
- ⚠️ **Concurrent updates from Telegram:** dois callbacks rápidos do mesmo state_id podem causar race no Sheets (cada um lê o payload antes do outro marcar CONSUMED). Não vi locking. Realisticamente baixa probabilidade em uso single-user, mas vale lembrar.

---

## Resumo executivo

- Caminho feliz funciona, code review limpo, captura de ValueError no rateio implementada certinho.
- Maior gap é **F1 (GRA não está na UI)** — os 5 produtos já migrados existem mas é difícil expandir/manter pelo bot. Próximo bug previsível: usuária quer criar uma nova etiqueta personalizada via `/novo` e não encontra a categoria.
- Segundo maior gap é **F8 (zero testes pra `distribute_frete_desconto`)** — função nova, com edge cases numéricos, sem proteção contra regression.
- Resto são polimentos: arredondamento de centavos (F3), unidade hardcoded UN no auto-create (F9), test morto (F7), couple de UX bumps (F4, F11, F12).
- Tests existentes: **25/25 PASS**.
