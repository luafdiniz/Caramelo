"""
Alias memory — remember which receipt-text maps to which Produto/Fornecedor.

Stored in an `Aliases` tab in the spreadsheet (auto-created on first use):
| ID    | tipo       | texto_original          | resolved_id | created_at |
|-------|------------|-------------------------|-------------|------------|
| A-001 | FORNECEDOR | IMPACTO Atacado & Varejo| FORN-005    | 2026-05-12 |
| A-002 | PRODUTO    | PLASTILANIA - FORMA ... | FOR-002     | 2026-05-12 |

Usage:
- check_alias(spreadsheet_id, "PRODUTO", text) → returns resolved_id or None
- save_alias(spreadsheet_id, "FORNECEDOR", text, "FORN-005")
"""

from datetime import date
from typing import Optional
from .sheets import get_service, _next_id_for_prefix


ALIASES_SHEET = "Aliases"


def ensure_sheet(spreadsheet_id: str, service=None) -> None:
    """Create the Aliases tab if it doesn't exist."""
    service = service or get_service()
    meta = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    titles = [s["properties"]["title"] for s in meta["sheets"]]
    if ALIASES_SHEET in titles:
        return

    service.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={"requests": [{"addSheet": {"properties": {"title": ALIASES_SHEET}}}]},
    ).execute()
    service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=f"{ALIASES_SHEET}!A1",
        valueInputOption="RAW",
        body={"values": [["ID", "tipo", "texto_original", "resolved_id", "created_at"]]},
    ).execute()


def _norm(s: str) -> str:
    """Normalize text for comparison: lowercase + collapse whitespace."""
    return " ".join((s or "").lower().split())


def get_all(spreadsheet_id: str, service=None) -> list[dict]:
    """Return all aliases as list of dicts."""
    service = service or get_service()
    ensure_sheet(spreadsheet_id, service=service)
    result = service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id, range=f"{ALIASES_SHEET}!A2:E"
    ).execute()
    rows = result.get("values", [])
    return [
        {
            "id": r[0] if len(r) > 0 else "",
            "tipo": r[1] if len(r) > 1 else "",
            "texto_original": r[2] if len(r) > 2 else "",
            "resolved_id": r[3] if len(r) > 3 else "",
            "created_at": r[4] if len(r) > 4 else "",
        }
        for r in rows if r and r[0]
    ]


def check(spreadsheet_id: str, tipo: str, text: str, service=None) -> Optional[str]:
    """
    Look up an alias. Returns resolved_id or None.

    Match is exact after normalization (lowercase, collapsed whitespace).
    """
    target = _norm(text)
    if not target:
        return None
    for a in get_all(spreadsheet_id, service=service):
        if a["tipo"] == tipo and _norm(a["texto_original"]) == target:
            return a["resolved_id"]
    return None


def save(spreadsheet_id: str, tipo: str, text: str, resolved_id: str, service=None) -> str:
    """
    Save an alias. Skips if the exact (tipo, text) already exists.

    Returns the new alias ID (A-NNN) or the existing one.
    """
    service = service or get_service()
    ensure_sheet(spreadsheet_id, service=service)

    # Skip if already saved
    existing = check(spreadsheet_id, tipo, text, service=service)
    if existing == resolved_id:
        return ""  # no-op

    new_id = _next_id_for_prefix(spreadsheet_id, f"{ALIASES_SHEET}!A:A", "A", service=service)

    # Find next empty row
    result = service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id, range=f"{ALIASES_SHEET}!A:A"
    ).execute()
    next_row = len(result.get("values", [])) + 1

    service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=f"{ALIASES_SHEET}!A{next_row}",
        valueInputOption="USER_ENTERED",
        body={
            "values": [[
                new_id,
                tipo,
                text,
                resolved_id,
                date.today().isoformat(),
            ]]
        },
    ).execute()
    return new_id
