# Sessão 2026-06-27 (pm) — Modo Feira no bot

Adicionou ao bot do Telegram um **Modo Feira** pra registrar vendas de pudim
numa feira de rua, por texto, áudio ou imagem, com balanço no final.

Contexto: a Luiza vai vender pudins de 200g a R$18 numa feira e quer ir
anotando as vendas pelo bot ("vendi 2 pro fulano", "vendi 2 agora", "vendi 2 e
fulano vai voltar pra pagar"), e no fim fechar o caixa.

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

## Esquema das abas (auto-criadas no 1º uso)

`Feiras`: id | data | status | descricao | qtd_levada | preco_unit | chat_id |
qtd_voltou | dinheiro | pix | data_fechamento | notas
(status ∈ aberta/fechada/cancelada)

`VendasFeira`: id | feira_id | data | cliente_nome | qtde | preco_unit |
preco_total | forma_pagamento | status_pagamento | status | notas
(forma ∈ dinheiro/pix/""; status_pagamento ∈ pago/fiado; status ∈ ativa/cancelada)

IDs: `FEIRA-NNN`, `VEN-NNN` (via `sheets._next_id_for_prefix`).

## Fluxo de uso

1. *"tamo saindo pra feira, levando 30 pudins a R$18"* (ou `/feira`) → abre.
2. Enquanto aberta, tudo (texto/áudio/foto) é venda: *"vendi 2 pro fulano"*,
   *"vendi 2 agora"*, *"vendi 2, maria vai voltar pra pagar"* (fiado),
   *"vendi 3 pro joão no pix"*. Cada uma loga na hora + Desfazer.
3. *"voltaram 5, recebi 200 no dinheiro e 150 no pix"* ou `/fechar` → balanço +
   botão Encerrar.

## Status / testes
- `test_feira` 23/23, `test_frete_desconto` 25/25, `test_nfe_xml` 32/32 PASS.
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
