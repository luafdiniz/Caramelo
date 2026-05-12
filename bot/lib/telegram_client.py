"""
Telegram Bot API helpers.

Minimal client — only what the bot needs:
- send_message: text replies
- send_message_with_buttons: inline keyboard for confirmations
- get_file: download photo bytes
"""

import os
from typing import Optional
import requests


def _api_url(method: str, token: Optional[str] = None) -> str:
    token = token or os.environ["TELEGRAM_BOT_TOKEN"]
    return f"https://api.telegram.org/bot{token}/{method}"


def send_message(
    chat_id: int,
    text: str,
    parse_mode: str = "HTML",
    reply_to_message_id: Optional[int] = None,
    token: Optional[str] = None,
) -> dict:
    """Send a plain text message."""
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode,
    }
    if reply_to_message_id:
        payload["reply_to_message_id"] = reply_to_message_id

    resp = requests.post(_api_url("sendMessage", token), json=payload, timeout=10)
    resp.raise_for_status()
    return resp.json()


def send_message_with_buttons(
    chat_id: int,
    text: str,
    buttons: list[list[dict]],
    parse_mode: str = "HTML",
    token: Optional[str] = None,
) -> dict:
    """
    Send a message with an inline keyboard.

    buttons format: [[{"text": "Sim", "callback_data": "confirm:abc"}], [...]]
    """
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode,
        "reply_markup": {"inline_keyboard": buttons},
    }
    resp = requests.post(_api_url("sendMessage", token), json=payload, timeout=10)
    resp.raise_for_status()
    return resp.json()


def edit_message_text(
    chat_id: int,
    message_id: int,
    text: str,
    parse_mode: str = "HTML",
    reply_markup: Optional[dict] = None,
    token: Optional[str] = None,
) -> dict:
    """Edit an existing message (used to update confirmation flows)."""
    payload = {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": text,
        "parse_mode": parse_mode,
    }
    if reply_markup is not None:
        payload["reply_markup"] = reply_markup
    resp = requests.post(_api_url("editMessageText", token), json=payload, timeout=10)
    resp.raise_for_status()
    return resp.json()


def answer_callback_query(callback_query_id: str, text: str = "", token: Optional[str] = None) -> None:
    """Acknowledge a button press."""
    payload = {"callback_query_id": callback_query_id}
    if text:
        payload["text"] = text
    requests.post(_api_url("answerCallbackQuery", token), json=payload, timeout=10)


def get_file_bytes(file_id: str, token: Optional[str] = None) -> bytes:
    """Download a file (photo) sent to the bot."""
    token = token or os.environ["TELEGRAM_BOT_TOKEN"]
    # Step 1: get file path
    resp = requests.get(_api_url("getFile", token), params={"file_id": file_id}, timeout=10)
    resp.raise_for_status()
    file_path = resp.json()["result"]["file_path"]

    # Step 2: download file
    file_url = f"https://api.telegram.org/file/bot{token}/{file_path}"
    file_resp = requests.get(file_url, timeout=30)
    file_resp.raise_for_status()
    return file_resp.content
