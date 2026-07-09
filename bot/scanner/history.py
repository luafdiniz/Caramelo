"""Full price history — merge scans (Precos_Observados) with purchases (Compras).

Rationale: a real purchase (NF-e / bot registro) is stronger market signal
than a scrape — it's an actual transaction at the shelf. The baseline used
by rules.classify() should learn from both.

Merged item shape (chronological, oldest → newest):
    {"preco_unidade": float, "timestamp": ISO str, "source": "scan"|"compra"}
"""

from __future__ import annotations

from lib import sheets


def _load_compras(spreadsheet_id: str, insumo_id: str, service=None) -> list[dict]:
    compras = sheets.get_compras_by_produto(spreadsheet_id, insumo_id, service=service)
    out: list[dict] = []
    for c in compras:
        preco_un = c.get("preco_unitario") or 0
        if preco_un <= 0:
            continue
        data = str(c.get("data") or "").strip()
        if not data:
            continue
        # Compras.data comes as YYYY-MM-DD; make it a full ISO datetime
        ts = data if "T" in data else f"{data}T00:00:00"
        out.append({
            "preco_unidade": float(preco_un),
            "timestamp": ts,
            "source": "compra",
        })
    return out


def _load_scans(spreadsheet_id: str, scanner_id: str, service=None) -> list[dict]:
    scans = sheets.get_precos_observados_by_scanner(spreadsheet_id, scanner_id, service=service)
    out: list[dict] = []
    for s in scans:
        pu = s.get("preco_unidade") or 0
        if pu <= 0:
            continue
        out.append({
            "preco_unidade": float(pu),
            "timestamp": s.get("timestamp") or "",
            "source": "scan",
        })
    return out


def get_full_history(
    spreadsheet_id: str,
    scanner_id: str,
    insumo_id: str,
    service=None,
) -> list[dict]:
    """Return scans + compras for this scanner/insumo, sorted oldest → newest."""
    scans = _load_scans(spreadsheet_id, scanner_id, service=service)
    compras = _load_compras(spreadsheet_id, insumo_id, service=service)
    merged = scans + compras
    merged.sort(key=lambda h: h["timestamp"])
    return merged
