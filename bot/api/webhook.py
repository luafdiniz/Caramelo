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


def _allowed_chat(chat_id: int) -> bool:
    raw = os.environ.get("TELEGRAM_ALLOWED_CHAT_IDS", "").strip()
    if not raw:
        return True  # no allowlist configured
    allowed = {int(x.strip()) for x in raw.split(",") if x.strip()}
    return chat_id in allowed


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
            orchestrator.handle_photo(chat_id, photo["file_id"], image_bytes)
        except Exception as e:
            tg.send_message(chat_id, f"❌ Erro: `{e}`")
            traceback.print_exc()
        return

    # Text command
    if msg and msg.get("text"):
        chat_id = msg["chat"]["id"]
        text = msg["text"].strip()
        if not _allowed_chat(chat_id):
            tg.send_message(chat_id, f"⛔ Não autorizado. Seu chat_id: `{chat_id}`")
            return
        if text.startswith("/start") or text.startswith("/help"):
            tg.send_message(
                chat_id,
                "*Pudim Caramelo Bot* 🍮\n\n"
                "Manda uma foto de nota fiscal que eu extraio os itens e adiciono "
                "na planilha (aba Compras).\n\n"
                "Comandos:\n"
                "/start /help — esta mensagem\n"
                "/whoami — mostra seu chat_id",
            )
        elif text.startswith("/whoami"):
            tg.send_message(chat_id, f"Seu chat_id: `{chat_id}`")
        else:
            tg.send_message(chat_id, "📸 Manda uma foto de nota fiscal pra eu processar.")
        return

    # Button callback
    cb = update.get("callback_query")
    if cb:
        chat_id = cb["message"]["chat"]["id"]
        if not _allowed_chat(chat_id):
            tg.answer_callback_query(cb["id"], "Não autorizado")
            return
        try:
            orchestrator.handle_callback(
                chat_id=chat_id,
                message_id=cb["message"]["message_id"],
                callback_data=cb["data"],
                callback_query_id=cb["id"],
            )
        except Exception as e:
            tg.answer_callback_query(cb["id"], "Erro processando")
            tg.send_message(chat_id, f"❌ Erro: `{e}`")
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
