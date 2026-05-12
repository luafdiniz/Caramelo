"""
Orchestrator: ties Gemini parsing, product matching, state, and Telegram replies.

Public entrypoints:
- handle_photo(chat_id, file_id, image_bytes)
- handle_callback(chat_id, message_id, callback_data)
"""

import os
from datetime import datetime
from . import gemini, sheets, matcher, state, telegram_client as tg


SPREADSHEET_ID = None  # set lazily from env


def _spreadsheet_id() -> str:
    global SPREADSHEET_ID
    if SPREADSHEET_ID is None:
        SPREADSHEET_ID = os.environ["SPREADSHEET_ID"]
    return SPREADSHEET_ID


CONFIDENCE_EMOJI = {
    "alta": "✅",
    "media": "⚠️",
    "baixa": "❓",
}


def _esc(s) -> str:
    """Escape HTML special chars for Telegram HTML parse mode."""
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def format_receipt_summary(receipt: dict) -> str:
    """Format an enriched receipt as Telegram HTML."""
    forn = receipt.get("fornecedor_match")
    if forn:
        forn_line = f"<b>Fornecedor:</b> {_esc(forn['id'])} — {_esc(forn['nome'])} {CONFIDENCE_EMOJI.get(forn['match_confidence'], '')}"
    else:
        forn_line = f"<b>Fornecedor:</b> ⚠️ <code>{_esc(receipt.get('fornecedor', '?'))}</code> (não encontrado — cadastre antes)"

    data_line = f"<b>Data:</b> {_esc(receipt.get('data') or 'não detectada')}"
    total_line = f"<b>Total da nota:</b> R$ {receipt.get('total', 0):.2f}"

    lines = [forn_line, data_line, total_line, "", "<b>Itens:</b>"]

    for i, item in enumerate(receipt.get("itens", []), 1):
        prod = item.get("produto_match")
        conf = CONFIDENCE_EMOJI.get(item.get("confianca", "media"), "")
        if prod:
            match_conf = CONFIDENCE_EMOJI.get(prod["match_confidence"], "")
            prod_line = f"→ {_esc(prod['id'])} {_esc(prod['nome'])} {match_conf}"
        else:
            prod_line = "→ ⚠️ Produto não encontrado (vai precisar cadastrar)"

        marca = f" • {_esc(item['marca'])}" if item.get("marca") else ""
        qtd_emb = item.get("qtde_embalagens", 1)
        unid_emb = item.get("unidades_por_embalagem", 1)
        preco = item.get("preco_total", 0)

        lines.append(f"{i}. {conf} {_esc(item.get('descricao', '?'))}{marca}")
        lines.append(f"   {qtd_emb}x{unid_emb} unid — R$ {preco:.2f}")
        lines.append(f"   {prod_line}")
        lines.append("")

    if receipt.get("observacoes"):
        lines.append(f"<i>{_esc(receipt['observacoes'])}</i>")

    return "\n".join(lines)


def handle_photo(chat_id: int, file_id: str, image_bytes: bytes) -> None:
    """
    Full photo flow:
    1. Parse with Gemini
    2. Match products and supplier
    3. Save state + reply with Confirm/Cancel buttons
    """
    tg.send_message(chat_id, "📸 Recebi a nota, processando...")

    try:
        receipt = gemini.parse_receipt(image_bytes)
    except Exception as e:
        tg.send_message(chat_id, f"❌ Erro ao processar a imagem: <code>{_esc(e)}</code>")
        return

    service = sheets.get_service()
    produtos = sheets.get_produtos(_spreadsheet_id(), service=service)
    fornecedores = sheets.get_fornecedores(_spreadsheet_id(), service=service)

    enriched = matcher.enrich_receipt(receipt, produtos, fornecedores)

    summary = format_receipt_summary(enriched)
    state_id = state.save_state(_spreadsheet_id(), enriched, service=service)

    buttons = [
        [
            {"text": "✅ Confirmar tudo", "callback_data": f"confirm:{state_id}"},
            {"text": "❌ Cancelar", "callback_data": f"cancel:{state_id}"},
        ]
    ]
    tg.send_message_with_buttons(chat_id, summary, buttons)


def handle_callback(chat_id: int, message_id: int, callback_data: str, callback_query_id: str) -> None:
    """Handle button clicks."""
    if ":" not in callback_data:
        tg.answer_callback_query(callback_query_id, "Ação inválida")
        return

    action, state_id = callback_data.split(":", 1)
    service = sheets.get_service()
    payload = state.load_state(_spreadsheet_id(), state_id, service=service)

    if not payload:
        tg.answer_callback_query(callback_query_id, "Estado expirado ou já processado")
        tg.edit_message_text(chat_id, message_id, "⏱ Esta confirmação não está mais válida.", reply_markup=None)
        return

    if action == "cancel":
        state.delete_state(_spreadsheet_id(), state_id, service=service)
        tg.answer_callback_query(callback_query_id, "Cancelado")
        tg.edit_message_text(chat_id, message_id, "❌ Cancelado, nada foi salvo.", reply_markup=None)
        return

    if action == "confirm":
        tg.answer_callback_query(callback_query_id, "Salvando...")
        added_ids = []
        skipped = []

        data = payload.get("data") or datetime.now().strftime("%Y-%m-%d")
        forn_match = payload.get("fornecedor_match")
        if not forn_match:
            tg.edit_message_text(
                chat_id, message_id,
                "⚠️ Fornecedor não identificado. Cadastre na aba Fornecedores e mande a nota de novo.",
                reply_markup=None,
            )
            state.delete_state(_spreadsheet_id(), state_id, service=service)
            return

        for item in payload.get("itens", []):
            prod_match = item.get("produto_match")
            if not prod_match:
                skipped.append(item.get("descricao", "?"))
                continue
            compra_id = sheets.append_compra(
                spreadsheet_id=_spreadsheet_id(),
                data=data,
                produto_id=prod_match["id"],
                fornecedor_id=forn_match["id"],
                marca=item.get("marca") or "",
                qtde_embalagens=item.get("qtde_embalagens", 1),
                unidades_por_embalagem=item.get("unidades_por_embalagem", 1),
                preco_total=item.get("preco_total", 0),
                notas=f"Via bot — {payload.get('observacoes', '')}".strip(" —"),
                service=service,
            )
            added_ids.append(compra_id)

        state.delete_state(_spreadsheet_id(), state_id, service=service)

        msg_lines = [f"✅ Adicionei {len(added_ids)} compra(s):"]
        for cid in added_ids:
            msg_lines.append(f"• {cid}")
        if skipped:
            msg_lines.append("")
            msg_lines.append(f"⚠️ Não adicionei ({len(skipped)} sem match de produto):")
            for s in skipped:
                msg_lines.append(f"• {s}")
            msg_lines.append("")
            msg_lines.append("Cadastre esses produtos na aba Produtos e mande a nota de novo.")

        tg.edit_message_text(chat_id, message_id, "\n".join(msg_lines), reply_markup=None)
