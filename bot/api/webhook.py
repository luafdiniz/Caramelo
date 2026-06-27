"""
Telegram webhook — Vercel serverless function.

Receives updates from Telegram and dispatches to the orchestrator.
"""

import os
import sys
import json
import traceback
from http.server import BaseHTTPRequestHandler

# Make sibling 'lib' importable on Vercel
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib import telegram_client as tg
from lib import orchestrator
from lib import gemini
from lib import feira_flow


def _allowed_chat(chat_id: int) -> bool:
    raw = os.environ.get("TELEGRAM_ALLOWED_CHAT_IDS", "").strip()
    if not raw:
        return True  # no allowlist configured
    allowed = {int(x.strip()) for x in raw.split(",") if x.strip()}
    return chat_id in allowed


def _handle_free_text(chat_id: int, text: str) -> None:
    """
    Route a free-text message (typed or transcribed from audio) through the
    pipeline: open feira > feira sale > compra-correction > incluir > open feira
    from text > purchase description > default help.
    """
    # 1. A feira is open → everything is a sale/closing/status.
    if feira_flow.has_open_feira(chat_id):
        if feira_flow.handle_text(chat_id, text):
            return

    # 2. Mid-compra interactive correction (item name / pack size / frete).
    if orchestrator.handle_text_hint(chat_id, text):
        return

    # 3. "incluir N" — revive a skipped receipt item.
    import re
    m = re.match(r"^(?:incluir|include|\+)\s*(\d+)\s*$", text, re.IGNORECASE)
    if m:
        orchestrator.handle_include_command(chat_id, int(m.group(1)))
        return

    # 4. Natural-language feira opening ("tamo saindo pra feira, 30 a R$18").
    if feira_flow.try_open_from_text(chat_id, text):
        return

    # 5. Free-text purchase description (Gemini parses).
    if orchestrator.handle_text_receipt(chat_id, text):
        return

    # 6. Fallback help.
    tg.send_message(
        chat_id,
        "📸 Manda foto/PDF/XML de nota, ou descreve a compra em texto "
        "(ex: <i>comprei 30 ovos na feira por 15 reais</i>).\n"
        "🎪 Pra vender numa feira: /feira (ex: <i>saindo pra feira, 30 pudins a R$18</i>).\n"
        "Comandos: /novo /compra /feira /fechar /cancel /help",
    )


def _process_update(update: dict) -> None:
    # Photo message
    msg = update.get("message")
    if msg and msg.get("photo"):
        chat_id = msg["chat"]["id"]
        if not _allowed_chat(chat_id):
            tg.send_message(chat_id, "⛔ Não autorizado.")
            return
        # Get largest photo
        photo = max(msg["photo"], key=lambda p: p.get("file_size", 0))
        try:
            image_bytes = tg.get_file_bytes(photo["file_id"])
            # While a feira is open, a photo is a sale note (handwritten tally,
            # pix receipt), not a purchase receipt.
            if feira_flow.has_open_feira(chat_id):
                feira_flow.handle_image(chat_id, image_bytes)
            else:
                orchestrator.handle_photo(chat_id, photo["file_id"], image_bytes)
        except Exception as e:
            tg.send_message(chat_id, f"❌ Erro: <code>{e}</code>")
            traceback.print_exc()
        return

    # Voice / audio message → transcribe, then route as free text
    if msg and (msg.get("voice") or msg.get("audio")):
        chat_id = msg["chat"]["id"]
        if not _allowed_chat(chat_id):
            tg.send_message(chat_id, "⛔ Não autorizado.")
            return
        media = msg.get("voice") or msg.get("audio")
        try:
            audio_bytes = tg.get_file_bytes(media["file_id"])
            mime = media.get("mime_type") or "audio/ogg"
            transcript = gemini.transcribe_audio(audio_bytes, mime_type=mime)
            if not transcript.strip():
                tg.send_message(chat_id, "🎤 Não consegui entender o áudio. Manda de novo ou escreve.")
                return
            tg.send_message(chat_id, f"🎤 <i>Entendi:</i> {transcript}")
            _handle_free_text(chat_id, transcript)
        except Exception as e:
            tg.send_message(chat_id, f"❌ Erro ao processar áudio: <code>{e}</code>")
            traceback.print_exc()
        return

    # Document message (PDF, XML)
    if msg and msg.get("document"):
        chat_id = msg["chat"]["id"]
        if not _allowed_chat(chat_id):
            tg.send_message(chat_id, "⛔ Não autorizado.")
            return
        doc = msg["document"]
        try:
            doc_bytes = tg.get_file_bytes(doc["file_id"])
            orchestrator.handle_document(
                chat_id=chat_id,
                file_id=doc["file_id"],
                file_bytes=doc_bytes,
                mime_type=doc.get("mime_type", ""),
                filename=doc.get("file_name", ""),
            )
        except Exception as e:
            tg.send_message(chat_id, f"❌ Erro: <code>{e}</code>")
            traceback.print_exc()
        return

    # Text command
    if msg and msg.get("text"):
        chat_id = msg["chat"]["id"]
        text = msg["text"].strip()
        if not _allowed_chat(chat_id):
            tg.send_message(chat_id, f"⛔ Não autorizado. Seu chat_id: <code>{chat_id}</code>")
            return
        if text.startswith("/start") or text.startswith("/help"):
            tg.send_message(
                chat_id,
                "<b>Pudim Caramelo Bot</b> 🍮\n\n"
                "📷 Foto / 📄 PDF → leitura de nota via IA\n"
                "📄 XML NF-e → leitura estruturada (mais precisa)\n"
                "🎤 Áudio → transcrevo e interpreto\n\n"
                "<b>Compras (insumos):</b>\n"
                "/novo — cadastrar produto sem nota\n"
                "/compra — registrar compra sem nota\n"
                "<code>incluir N</code> — re-revisar item N da última nota\n\n"
                "<b>Vendas na feira:</b>\n"
                "/feira — abrir feira (ex: <i>saindo pra feira, 30 pudins a R$18</i>)\n"
                "/feira_status — ver o parcial\n"
                "/fechar — encerrar e fazer o balanço\n\n"
                "/cancel — abortar fluxo em andamento\n"
                "/whoami — mostra seu chat id",
            )
        elif text.startswith("/whoami"):
            tg.send_message(chat_id, f"Seu chat_id: <code>{chat_id}</code>")
        elif text.startswith("/feira_status"):
            try:
                feira_flow.status_command(chat_id)
            except Exception as e:
                tg.send_message(chat_id, f"❌ Erro: <code>{e}</code>")
                traceback.print_exc()
        elif text.startswith("/feira"):
            try:
                args = text[len("/feira"):].strip()
                feira_flow.open_via_command(chat_id, args)
            except Exception as e:
                tg.send_message(chat_id, f"❌ Erro: <code>{e}</code>")
                traceback.print_exc()
        elif text.startswith("/fechar"):
            try:
                feira_flow.close_command(chat_id)
            except Exception as e:
                tg.send_message(chat_id, f"❌ Erro: <code>{e}</code>")
                traceback.print_exc()
        elif text.startswith("/novo"):
            try:
                orchestrator.start_novo_flow(chat_id)
            except Exception as e:
                tg.send_message(chat_id, f"❌ Erro: <code>{e}</code>")
                traceback.print_exc()
        elif text.startswith("/compra"):
            try:
                orchestrator.start_compra_flow(chat_id)
            except Exception as e:
                tg.send_message(chat_id, f"❌ Erro: <code>{e}</code>")
                traceback.print_exc()
        elif text.startswith("/cancel"):
            try:
                # If a feira is open, /cancel aborts it; otherwise abort the
                # current compra/novo interactive flow.
                if not feira_flow.cancel_open_feira(chat_id):
                    orchestrator.cancel_active_flow(chat_id)
            except Exception as e:
                tg.send_message(chat_id, f"❌ Erro: <code>{e}</code>")
                traceback.print_exc()
        else:
            try:
                _handle_free_text(chat_id, text)
            except Exception as e:
                tg.send_message(chat_id, f"❌ Erro: <code>{e}</code>")
                traceback.print_exc()
        return

    # Button callback
    cb = update.get("callback_query")
    if cb:
        chat_id = cb["message"]["chat"]["id"]
        if not _allowed_chat(chat_id):
            tg.answer_callback_query(cb["id"], "Não autorizado")
            return
        try:
            parts = (cb["data"] or "").split(":")
            # Feira buttons (vundo / vfecha / vcont) are owned by feira_flow;
            # everything else goes to the compra orchestrator.
            if parts and parts[0] in ("vundo", "vfecha", "vcont", "vmove"):
                feira_flow.handle_callback(
                    chat_id=chat_id,
                    message_id=cb["message"]["message_id"],
                    parts=parts,
                    callback_query_id=cb["id"],
                )
            else:
                orchestrator.handle_callback(
                    chat_id=chat_id,
                    message_id=cb["message"]["message_id"],
                    callback_data=cb["data"],
                    callback_query_id=cb["id"],
                )
        except Exception as e:
            tg.answer_callback_query(cb["id"], "Erro processando")
            tg.send_message(chat_id, f"❌ Erro: <code>{e}</code>")
            traceback.print_exc()
        return


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8")
        try:
            update = json.loads(body)
            _process_update(update)
        except Exception:
            traceback.print_exc()
        # Always reply 200 — Telegram retries on non-200
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"ok":true}')

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"Pudim Caramelo bot webhook. Send POST to use.")
