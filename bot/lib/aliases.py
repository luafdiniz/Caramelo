"""
Alias memory — remember which receipt-text maps to which Produto/Fornecedor.

Stored in an `Aliases` tab in the spreadsheet (auto-created on first use):
| ID    | tipo       | texto_original          | resolved_id | created_at | pack_size |
|-------|------------|-------------------------|-------------|------------|-----------|
| A-001 | FORNECEDOR | IMPACTO Atacado & Varejo| FORN-005    | 2026-05-12 |           |
| A-002 | PRODUTO    | PLASTILANIA - FORMA ... | FOR-002     | 2026-05-12 | 5         |

`pack_size` is only meaningful for PRODUTO aliases: how many units of the
product come per "embalagem" (the receipt line item). Empty/missing = unknown.

Usage:
- check(spreadsheet_id, "PRODUTO", text) → returns resolved_id or None
- get_alias(spreadsheet_id, "PRODUTO", text) → returns full row dict or None
- save(spreadsheet_id, "PRODUTO", text, "FOR-002", pack_size=5)
"""

from datetime import date
from typing import Optional
from .sheets import get_service, _next_id_for_prefix


ALIASES_SHEET = "Aliases"
ALIASES_HEADER = ["ID", "tipo", "texto_original", "resolved_id", "created_at", "pack_size"]


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
        body={"values": [ALIASES_HEADER]},
    ).execute()


def _norm(s: str) -> str:
    """Normalize text for comparison: lowercase + collapse whitespace."""
    return " ".join((s or "").lower().split())


def _parse_pack_size(raw) -> Optional[int]:
    if raw is None or raw == "":
        return None
    try:
        n = int(float(raw))
        return n if n > 0 else None
    except (ValueError, TypeError):
        return None


def _get_all_with_row_indices(spreadsheet_id: str, service=None) -> list[tuple[int, dict]]:
    """Return list of (sheet_row_index, alias_dict). Row 1 is the header."""
    service = service or get_service()
    ensure_sheet(spreadsheet_id, service=service)
    result = service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id, range=f"{ALIASES_SHEET}!A2:F"
    ).execute()
    rows = result.get("values", [])
    out: list[tuple[int, dict]] = []
    for offset, r in enumerate(rows):
        if not r or not r[0]:
            continue
        out.append((
            offset + 2,  # +2 = account for header row (1) and 0-based offset
            {
                "id": r[0] if len(r) > 0 else "",
                "tipo": r[1] if len(r) > 1 else "",
                "texto_original": r[2] if len(r) > 2 else "",
                "resolved_id": r[3] if len(r) > 3 else "",
                "created_at": r[4] if len(r) > 4 else "",
                "pack_size": _parse_pack_size(r[5] if len(r) > 5 else None),
            },
        ))
    return out


def get_all(spreadsheet_id: str, service=None) -> list[dict]:
    """Return all aliases as a list of dicts (without row indices)."""
    return [a for _, a in _get_all_with_row_indices(spreadsheet_id, service=service)]


def get_alias(spreadsheet_id: str, tipo: str, text: str, service=None) -> Optional[dict]:
    """Return the full alias row dict or None. Looks up by (tipo, normalized text)."""
    target = _norm(text)
    if not target:
        return None
    for a in get_all(spreadsheet_id, service=service):
        if a["tipo"] == tipo and _norm(a["texto_original"]) == target:
            return a
    return None


def check(spreadsheet_id: str, tipo: str, text: str, service=None) -> Optional[str]:
    """Back-compat helper — return just the resolved_id."""
    a = get_alias(spreadsheet_id, tipo, text, service=service)
    return a["resolved_id"] if a else None


def save(
    spreadsheet_id: str,
    tipo: str,
    text: str,
    resolved_id: str,
    pack_size: Optional[int] = None,
    service=None,
) -> str:
    """
    Create a new alias or update pack_size on an existing one.

    Returns:
      - new alias ID (A-NNN) when a row was created;
      - "" when the row already existed (pack_size may still be updated in place).
    """
    service = service or get_service()
    ensure_sheet(spreadsheet_id, service=service)

    existing = _get_all_with_row_indices(spreadsheet_id, service=service)
    target = _norm(text)
    for row_idx, a in existing:
        if a["tipo"] != tipo or _norm(a["texto_original"]) != target:
            continue
        # Same (tipo, text) already saved.
        if a["resolved_id"] != resolved_id:
            # Different resolution recorded earlier — keep history, don't overwrite.
            return ""
        if pack_size is not None and a.get("pack_size") != pack_size:
            service.spreadsheets().values().update(
                spreadsheetId=spreadsheet_id,
                range=f"{ALIASES_SHEET}!F{row_idx}",
                valueInputOption="USER_ENTERED",
                body={"values": [[pack_size]]},
            ).execute()
        return ""

    return _create_new_alias(spreadsheet_id, tipo, text, resolved_id, pack_size, service)


def delete(spreadsheet_id: str, tipo: str, text: str, service=None) -> bool:
    """
    Wipe an alias row matching (tipo, normalized text). Returns True if deleted.

    Used when the user explicitly corrects a previously-learned association —
    next time the same receipt text comes in it should be matched fresh, not
    auto-resolved by the stale memory.
    """
    service = service or get_service()
    ensure_sheet(spreadsheet_id, service=service)
    target = _norm(text)
    if not target:
        return False
    existing = _get_all_with_row_indices(spreadsheet_id, service=service)
    for row_idx, a in existing:
        if a["tipo"] == tipo and _norm(a["texto_original"]) == target:
            service.spreadsheets().values().clear(
                spreadsheetId=spreadsheet_id,
                range=f"{ALIASES_SHEET}!A{row_idx}:F{row_idx}",
            ).execute()
            return True
    return False


def _create_new_alias(spreadsheet_id, tipo, text, resolved_id, pack_size, service):
    new_id = _next_id_for_prefix(spreadsheet_id, f"{ALIASES_SHEET}!A:A", "A", service=service)
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
                pack_size if pack_size is not None else "",
            ]]
        },
    ).execute()
    return new_id
