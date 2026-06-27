# Sessão 2026-06-27 (pm) — Modo Feira no bot

Adicionou ao bot do Telegram um **Modo Feira** pra registrar vendas de pudim
numa feira de rua, por texto, áudio ou imagem, com balanço no final.

Contexto: a Luiza vai vender pudins de **200g a R$18 e 500g a R$45** numa feira
(e pode dar uns 500g pra produção/cortesia). Quer ir anotando as vendas pelo bot
("vendi 2 pro fulano", "vendi 2 de 500g agora", "vendi 2 e fulano vai voltar pra
pagar"), e no fim fechar o caixa.

> **v2 (mesma sessão):** a 1ª versão assumia UM produto/preço por feira e
> travou no teste real (ela vende 2 tamanhos). Refeito pra **multi-produto**:
> vários tamanhos por feira, cada um com qtde e preço; abertura em 2 etapas
> (qtde primeiro, preço depois → rascunho → aberta); cada venda guarda o
> tamanho; balanço e reconciliação de estoque por tamanho; botões pra trocar o
> tamanho de uma venda registrada.

## Decisões (confirmadas com a Luiza nesta sessão)

1. **Esquema leve dedicado** (não o Tema D completo). Abas novas `Feiras` +
   `VendasFeira`, nome do cliente em **texto livre** (sem cadastro de cliente,
   sem preço B2B). O Tema D (`plans/tema-d-clientes-vendas-b2b.md`) continua
   pendente pra quando o atacado justificar — os dois coexistem de propósito.
2. **Registra na hora + botão Desfazer.** Sem confirmar cada venda no meio —
   ritmo de feira. Cada venda responde com resumo curto + `↩️ Desfazer`
   (soft-cancel: marca `status=cancelada`, balanço ignora).

## O que foi construído

### Arquivos novos
- `bot/lib/feira.py` — camada de dados + balanço puro:
  - `ensure_feira_sheets`, `open_feira`, `get_open_feira`, `append_venda`,
    `cancel_venda`, `get_vendas`, `update_closing`, `finalize_feira`,
    `cancel_feira`.
  - `compute_balanco(feira, vendas)` — função **pura** (testada): faturado,
    split dinheiro/pix, fiado + lista de quem deve, reconciliação de estoque
    (levou − vendeu − voltou) e divergência de caixa (informado × registrado).
- `bot/lib/feira_flow.py` — orquestração Telegram: abertura (comando ou texto
  natural com a palavra "feira"), registro de venda, fechamento incremental,
  status parcial, callbacks (`vundo`/`vfecha`/`vcont`), formatação do balanço.
- `bot/tests/test_feira.py` — 23 checks, sem rede. PASS.

### Arquivos alterados
- `bot/lib/gemini.py` — 4 funções novas: `transcribe_audio` (voz OGG→texto via
  `gemini-2.5-flash` nativo), `parse_feira_opening`, `parse_feira_message`
  (classifica venda/fechamento/status/outro + extrai campos),
  `parse_feira_image`.
- `bot/api/webhook.py`:
  - Trata `voice`/`audio` → transcreve → roteia como texto livre.
  - Foto: se feira aberta → lê como venda; senão → nota de compra (igual antes).
  - Comandos `/feira`, `/feira_status`, `/fechar`. `/cancel` aborta a feira se
    houver uma aberta; senão o fluxo de compra. `/help` atualizado.
  - Helper `_handle_free_text` centraliza o pipeline: feira aberta → venda;
    correção de compra; `incluir N`; abrir feira por texto; compra por texto;
    ajuda.
  - Callbacks da feira roteados antes do orchestrator de compras.

## Esquema das abas (auto-criadas no 1º uso) — v2 multi-produto

`Feiras`: id | data | status | descricao | produtos_json | chat_id |
voltou_json | dinheiro | pix | data_fechamento | notas
- status ∈ rascunho/aberta/fechada/cancelada
- produtos_json: `[{"tamanho":"200g","qtd_levada":63,"preco":18.0}, ...]`
  (qtd e/ou preço podem ser null no rascunho)
- voltou_json: `{"200g":58,"500g":2}` (no fechamento)

`VendasFeira`: id | feira_id | data | cliente_nome | tamanho | qtde |
preco_unit | preco_total | forma_pagamento | status_pagamento | status | notas
(forma ∈ dinheiro/pix/""; status_pagamento ∈ pago/fiado; status ∈ ativa/cancelada)

IDs: `FEIRA-NNN`, `VEN-NNN`. **Cabeçalhos das abas já corrigidos na planilha
de produção** (a v1 tinha criado com o schema antigo; rodei um one-off com o
service account pra reescrever os headers; não havia linhas de dados).

## Fluxo de uso

1. *"saindo pra feira, 63 de 200g e 4 de 500g"* → vira **rascunho**, bot pede os
   preços. *"18 o de 200g e 45 o de 500g"* → feira **aberta**. (Ou tudo numa
   mensagem só, ou `/feira ...`.)
2. Enquanto aberta, tudo (texto/áudio/foto) é venda: *"vendi 2 de 200g pro
   fulano"*, *"vendi 1 de 500g no pix"*, *"vendi 2 agora"* (assume tamanho
   principal + botões pra trocar), *"vendi 2, maria vai voltar pra pagar"*
   (fiado). Cada uma loga na hora + Desfazer + ↔️ trocar tamanho.
3. *"voltaram 58 de 200g e 2 de 500g, recebi 200 no dinheiro e 150 no pix"* ou
   `/fechar` → balanço por tamanho + caixa + botão Encerrar.

## Status / testes
- `test_feira` 31/31 (multi-produto), `test_frete_desconto` 25/25,
  `test_nfe_xml` 32/32 PASS.
- Todos os módulos importam limpo (inclusive `webhook.py`).
- **Parsers do Gemini NÃO testados localmente** — `GEMINI_API_KEY` só existe no
  Vercel. Seguem o mesmo padrão do `parse_receipt_text` (que funciona em prod),
  com `response_mime_type="application/json"`. Validar no primeiro uso real.

## Pendências / próximos passos
- **Deploy:** ainda NÃO commitado nem deployado (aguardando OK da Luiza).
  Push pra `main` → Vercel auto-deploya.
- **Validar em produção:** mandar uma abertura, 2-3 vendas (uma fiado, uma pix,
  uma sem forma) e um fechamento; conferir as abas e o balanço.
- **Gotchas conhecidos:**
  - Com feira aberta, foto de nota de COMPRA é lida como venda. Fechar a feira
    antes de fotografar nota. (Comportamento documentado.)
  - Texto natural só abre feira se contiver a palavra "feira"; senão usar
    `/feira`.
  - Abertura sem qtde funciona (qtd_levada=0) mas a reconciliação de estoque
    fica sem base; o ideal é informar quantos levou.
