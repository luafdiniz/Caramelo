"""
Pending-confirmation state, stored in a hidden Sheets tab.

Why Sheets and not Redis/KV? Free, no extra infra. Each pending receipt
is one row in a "_BotState" tab. Telegram callback_data references the row.

Lifecycle:
1. Bot parses receipt → writes pending state, replies with buttons
2. User clicks Confirm → bot reads state, writes to Compras, deletes state row
3. User clicks Cancel → bot deletes state row
"""

import os
import json
import time
from typing import Optional
from .sheets import get_service


STATE_SHEET = "_BotState"


def ensure_state_sheet(spreadsheet_id: str, service=None) -> None:
    """Create the hidden state sheet if it doesn't exist."""
    service = service or get_service()
    meta = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    titles = [s["properties"]["title"] for s in meta["sheets"]]
    if STATE_SHEET in titles:
        return

    body = {
        "requests": [
            {
                "addSheet": {
                    "properties": {
                        "title": STATE_SHEET,
                        "hidden": True,
                    }
                }
            }
        ]
    }
    service.spreadsheets().batchUpdate(spreadsheetId=spreadsheet_id, body=body).execute()
    # Add header
    service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=f"{STATE_SHEET}!A1",
        valueInputOption="RAW",
        body={"values": [["state_id", "created_at", "payload_json"]]},
    ).execute()


def save_state(spreadsheet_id: str, payload: dict, service=None) -> str:
    """Save a pending state and return its ID."""
    service = service or get_service()
    ensure_state_sheet(spreadsheet_id, service=service)

    state_id = f"s{int(time.time() * 1000)}"
    service.spreadsheets().values().append(
        spreadsheetId=spreadsheet_id,
        range=f"{STATE_SHEET}!A:C",
        valueInputOption="RAW",
        body={
            "values": [[
                state_id,
                int(time.time()),
                json.dumps(payload, ensure_ascii=False),
            ]]
        },
    ).execute()
    return state_id


def load_state(spreadsheet_id: str, state_id: str, service=None) -> Optional[dict]:
    """Load a pending state by ID. Returns None if not found."""
    service = service or get_service()
    result = service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id, range=f"{STATE_SHEET}!A:C"
    ).execute()
    rows = result.get("values", [])
    for r in rows:
        if r and r[0] == state_id:
            return json.loads(r[2]) if len(r) > 2 else None
    return None


def delete_state(spreadsheet_id: str, state_id: str, service=None) -> None:
    """Mark a state as consumed (clear its payload)."""
    service = service or get_service()
    result = service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id, range=f"{STATE_SHEET}!A:C"
    ).execute()
    rows = result.get("values", [])
    for i, r in enumerate(rows):
        if r and r[0] == state_id:
            row_num = i + 1  # 1-indexed
            service.spreadsheets().values().update(
                spreadsheetId=spreadsheet_id,
                range=f"{STATE_SHEET}!C{row_num}",
                valueInputOption="RAW",
                body={"values": [["CONSUMED"]]},
            ).execute()
            return
