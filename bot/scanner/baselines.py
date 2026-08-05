"""Reference prices from the antiga sheet + nossa Compras.

Given a scanner alert, returns two references shown alongside the current
median-30d baseline in the notification:

- ultima_compra:   MIN(Valor por unidade) across the antiga rows mapped via
                   `codigos_planilha` for this SKU — reflects the last price
                   the Luiza/Fila actually paid at any supplier.
- menor_historico: MIN(col L "Menor preço histórico" da antiga,
                       preco_unitario da nossa `Compras` do bot) —
                   the all-time low we ever registered anywhere.

Both are None when we have no data (empty `codigos_planilha`, missing rows,
no compras).

Fonte da verdade da antiga: `PLANILHA_ANTIGA_ID` env — a service account do
Caramelo tem acesso read-only.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Optional

from lib import sheets
from scanner.config import AlertaConfig


_ANTIGA_TABS = ["Insumos alimentícios", "Insumos de embalagem"]

# "R$ 1.234,56" / "R$ 1,32" / "1,32" / "1.32" → 1.32
_BRL_RE = re.compile(r"[^\d,.\-]")

# "419,58 (400 UNIDADES)" → total=419.58, unidades=400. The antiga's
# "Menor preço histórico" column mixes unit prices and pack totals — we
# need the parenthesized qty to convert pack totals back to per-unit.
_PACK_NOTE_RE = re.compile(r"\(\s*(\d+)\s*UNIDAD", re.IGNORECASE)


def _parse_historico_cell(cell) -> Optional[float]:
    """Parse a 'Menor preço histórico' cell. Handles both:
      - Unit price ("R$ 1,05")
      - Pack total with qty in parens ("419,58 (400 UNIDADES)") — divides
        by the parenthesized qty to return unit price.
    Returns None if empty/unparseable.
    """
    raw = str(cell or "").strip()
    if not raw:
        return None
    m = _PACK_NOTE_RE.search(raw)
    # Strip the "(N UNIDADES)" clause before parsing the numeric part, so
    # `_parse_brl` doesn't glue the qty digits onto the price.
    without_note = re.sub(r"\([^)]*\)", "", raw).strip() if m else raw
    total = _parse_brl(without_note)
    if total is None:
        return None
    if m:
        qty = int(m.group(1))
        if qty > 0:
            return total / qty
    return total


def _parse_brl(cell) -> Optional[float]:
    """Parse a BRL-formatted cell value into a float. Returns None if empty
    or unparseable."""
    s = str(cell or "").strip()
    if not s:
        return None
    cleaned = _BRL_RE.sub("", s)
    if not cleaned:
        return None
    # Sheet cells sometimes come as "1.234,56" (BR) or "1,32" or "1.32".
    # If both . and , present: . is thousands, , is decimal.
    if "," in cleaned and "." in cleaned:
        cleaned = cleaned.replace(".", "").replace(",", ".")
    elif "," in cleaned:
        cleaned = cleaned.replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return None


@dataclass
class Reference:
    valor: float
    origem: str   # human-readable label ("F-011, Santo Antônio" / "Compra 2026-06-10")


@dataclass
class Baselines:
    ultima_compra: Optional[Reference]
    menor_historico: Optional[Reference]


def _load_antiga_insumos(service, antiga_id: str) -> dict[str, dict]:
    """Load both `Insumos alimentícios` and `Insumos de embalagem` tabs into
    a single dict keyed by `Código` (A-XXX / F-XXX / EMB-XXX).

    Cheap enough to call on every scan (2 tabs, few hundred rows total).
    """
    result: dict[str, dict] = {}
    for tab in _ANTIGA_TABS:
        # A:Código B:Produto C:Marca D:Fornecedor E:Unidade F:Preço
        # G:Qtde H:Valor por unid I:Capacidade J:Estoque K:(empty)
        # L:Menor preço histórico M:Maior preço histórico
        r = service.spreadsheets().values().get(
            spreadsheetId=antiga_id,
            range=f"'{tab}'!A2:M",
        ).execute()
        for row in r.get("values", []) or []:
            if not row or not row[0]:
                continue
            codigo = str(row[0]).strip()
            row = list(row) + [""] * (13 - len(row))
            result[codigo] = {
                "codigo": codigo,
                "produto": str(row[1]).strip(),
                "marca": str(row[2]).strip(),
                "fornecedor": str(row[3]).strip(),
                "valor_por_unidade": _parse_brl(row[7]),
                "menor_historico": _parse_historico_cell(row[11]),
            }
    return result


def _fornecedor_short(fornecedor: str) -> str:
    """Shorten fornecedor label for compact display in the alert."""
    f = (fornecedor or "").strip()
    if not f:
        return "?"
    # "Mercado Livre (EmbalaiadoSP)" → "ML EmbalaiadoSP"
    m = re.match(r"^Mercado Livre\s*\(([^)]+)\)\s*$", f, re.IGNORECASE)
    if m:
        return f"ML {m.group(1).strip()}"
    if f.lower() == "mercado livre":
        return "ML"
    return f


def _from_antiga(
    codigos: list[str], insumos: dict[str, dict],
) -> tuple[Optional[Reference], Optional[Reference]]:
    """Aggregate ultima_compra and menor_historico across the antiga rows
    mapped for one SKU. Cross-fornecedor: takes the MIN of each."""
    ultima: Optional[Reference] = None
    menor: Optional[Reference] = None

    for cod in codigos:
        row = insumos.get(cod)
        if not row:
            continue
        vpu = row.get("valor_por_unidade")
        if vpu is not None and vpu > 0:
            origem = f"{row['codigo']}, {_fornecedor_short(row['fornecedor'])}"
            if ultima is None or vpu < ultima.valor:
                ultima = Reference(vpu, origem)
        mh = row.get("menor_historico")
        if mh is not None and mh > 0:
            origem = f"{row['codigo']}, {_fornecedor_short(row['fornecedor'])}"
            if menor is None or mh < menor.valor:
                menor = Reference(mh, origem)
    return ultima, menor


def _from_nossa_compras(
    spreadsheet_id: str, insumo_id: str, service,
) -> Optional[Reference]:
    """MIN preco_unitario across the bot's own NF-e-fed `Compras` tab for
    this insumo_id. Used to keep menor_historico fresh even when the antiga's
    col. L is stale (only Fila updates it manually)."""
    compras = sheets.get_compras_by_produto(spreadsheet_id, insumo_id, service=service)
    best: Optional[Reference] = None
    for c in compras:
        pu = c.get("preco_unitario") or 0
        if pu <= 0:
            continue
        data = c.get("data") or ""
        origem = f"Compra {data}" if data else "Compra (bot)"
        if best is None or pu < best.valor:
            best = Reference(float(pu), origem)
    return best


def get_references(
    alerta: AlertaConfig,
    spreadsheet_id: str,
    service=None,
    antiga_id: Optional[str] = None,
    _antiga_cache: Optional[dict[str, dict]] = None,
) -> Baselines:
    """Return última compra + menor histórico for one alert.

    `_antiga_cache` lets the runner load the antiga tabs ONCE per scan cycle
    and reuse across all alerts — the antiga is small but fetching it N
    times per cycle is wasteful.
    """
    antiga_id = antiga_id or os.environ.get("PLANILHA_ANTIGA_ID", "").strip()

    if not alerta.codigos_planilha or not antiga_id:
        # Ainda vale checar as compras da nossa mesmo sem mapping — mas sem
        # códigos não dá pra chamar de "última compra" (não conseguimos
        # amarrar ao mesmo produto na antiga). Retorna só via bot Compras.
        menor_bot = _from_nossa_compras(spreadsheet_id, alerta.insumo_id, service or sheets.get_service())
        return Baselines(ultima_compra=None, menor_historico=menor_bot)

    service = service or sheets.get_service()
    insumos = _antiga_cache if _antiga_cache is not None else _load_antiga_insumos(service, antiga_id)

    ultima, menor_antiga = _from_antiga(alerta.codigos_planilha, insumos)
    menor_bot = _from_nossa_compras(spreadsheet_id, alerta.insumo_id, service)

    # menor_historico = MIN(antiga col L, nossa Compras)
    menor = menor_antiga
    if menor_bot is not None and (menor is None or menor_bot.valor < menor.valor):
        menor = menor_bot

    return Baselines(ultima_compra=ultima, menor_historico=menor)


def load_antiga_cache(service=None, antiga_id: Optional[str] = None) -> dict[str, dict]:
    """Prefetch the antiga insumos dict once per scan cycle. Returns {} if
    PLANILHA_ANTIGA_ID is unset — safe to pass through to get_references."""
    antiga_id = antiga_id or os.environ.get("PLANILHA_ANTIGA_ID", "").strip()
    if not antiga_id:
        return {}
    service = service or sheets.get_service()
    return _load_antiga_insumos(service, antiga_id)
