"""
Google Sheets client using a service account.

Reads Produtos and Fornecedores (for matching) and appends rows to Compras.
"""

import os
import json
from typing import Optional
from google.oauth2 import service_account
from googleapiclient.discovery import build


SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


def get_service(credentials_json: Optional[str] = None):
    """Build Sheets API service from service account credentials."""
    creds_json = credentials_json or os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
    if not creds_json:
        raise RuntimeError("GOOGLE_SERVICE_ACCOUNT_JSON not configured")

    # Allow either inline JSON or file path
    if creds_json.startswith("{"):
        info = json.loads(creds_json)
    else:
        with open(creds_json) as f:
            info = json.load(f)

    creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
    return build("sheets", "v4", credentials=creds, cache_discovery=False)


def get_produtos(spreadsheet_id: str, service=None) -> list[dict]:
    """Return list of products with optional relacionados + marca_padrao.

    Columns G (Preco_manual) and H (Preco_manual_data) are the manual price
    override added by `scripts/migrate_produtos_preco_manual.py`. They are
    optional — if the migration hasn't run, the dicts come back with empty
    string defaults and the cost layer falls back to the WAC of past compras.
    """
    service = service or get_service()
    result = service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id, range="Produtos!A2:H"
    ).execute()
    rows = result.get("values", [])
    out = []
    for r in rows:
        if not r or not r[0]:
            continue
        relacionados_raw = r[4] if len(r) > 4 else ""
        relacionados = [x.strip() for x in (relacionados_raw or "").split(",") if x.strip()]
        out.append({
            "id": r[0],
            "nome": r[1] if len(r) > 1 else "",
            "unidade": r[2] if len(r) > 2 else "",
            "notas": r[3] if len(r) > 3 else "",
            "relacionados": relacionados,
            "marca_padrao": (r[5] if len(r) > 5 else "") or "",
            "preco_manual": (r[6] if len(r) > 6 else "") or "",
            "preco_manual_data": (r[7] if len(r) > 7 else "") or "",
        })
    return out


def get_fornecedores(spreadsheet_id: str, service=None) -> list[dict]:
    """Return list of suppliers."""
    service = service or get_service()
    result = service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id, range="Fornecedores!A2:E"
    ).execute()
    rows = result.get("values", [])
    return [
        {
            "id": r[0] if len(r) > 0 else "",
            "nome": r[1] if len(r) > 1 else "",
            "tipo": r[2] if len(r) > 2 else "",
            "localizacao": r[3] if len(r) > 3 else "",
            "notas": r[4] if len(r) > 4 else "",
        }
        for r in rows if r and r[0]
    ]


def _next_id_for_prefix(spreadsheet_id: str, sheet_range: str, prefix: str, service=None) -> str:
    """Find next available ID like PREFIX-NNN by scanning column A of a range."""
    service = service or get_service()
    result = service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id, range=sheet_range
    ).execute()
    rows = result.get("values", [])
    max_n = 0
    for r in rows:
        if r and r[0].startswith(f"{prefix}-"):
            try:
                n = int(r[0].split("-")[1])
                max_n = max(max_n, n)
            except (ValueError, IndexError):
                continue
    return f"{prefix}-{max_n + 1:03d}"


def get_next_compra_id(spreadsheet_id: str, service=None) -> str:
    """Find the next available C-NNN ID."""
    return _next_id_for_prefix(spreadsheet_id, "Compras!A:A", "C", service=service)


def create_fornecedor(
    spreadsheet_id: str,
    nome: str,
    tipo: str = "Loja",
    localizacao: str = "",
    notas: str = "Cadastrado via bot",
    service=None,
) -> str:
    """Add a new fornecedor row. Returns the new FORN-NNN ID."""
    service = service or get_service()
    new_id = _next_id_for_prefix(spreadsheet_id, "Fornecedores!A:A", "FORN", service=service)

    # Find next empty row
    result = service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id, range="Fornecedores!A:A"
    ).execute()
    next_row = len(result.get("values", [])) + 1

    service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=f"Fornecedores!A{next_row}",
        valueInputOption="USER_ENTERED",
        body={"values": [[new_id, nome, tipo, localizacao, notas]]},
    ).execute()
    return new_id


def create_produto(
    spreadsheet_id: str,
    nome: str,
    categoria: str,  # "ALI", "FOR", "EMB", "EQP"
    unidade: str = "UN",
    notas: str = "Cadastrado via bot",
    service=None,
) -> str:
    """Add a new produto row. Returns the new ID with category prefix."""
    if categoria not in ("ALI", "FOR", "EMB", "GRA", "EQP", "OPR"):
        raise ValueError(f"Invalid categoria: {categoria}")

    service = service or get_service()
    new_id = _next_id_for_prefix(spreadsheet_id, "Produtos!A:A", categoria, service=service)

    result = service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id, range="Produtos!A:A"
    ).execute()
    next_row = len(result.get("values", [])) + 1

    service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=f"Produtos!A{next_row}",
        valueInputOption="USER_ENTERED",
        body={"values": [[new_id, nome, unidade, notas]]},
    ).execute()
    return new_id


def append_compra(
    spreadsheet_id: str,
    data: str,
    produto_id: str,
    fornecedor_id: str,
    marca: str,
    qtde_embalagens: float,
    unidades_por_embalagem: float,
    preco_total: float,
    notas: str = "",
    frete: float = 0.0,
    desconto: float = 0.0,
    service=None,
) -> str:
    """
    Append a row to Compras. Returns the new C-NNN ID.

    `preco_total` MUST already include the share of frete/desconto for this
    item (the caller does the rateio — see orchestrator._finalize). The raw
    `frete` and `desconto` totals are stored in columns L/M of every row of
    the same Compra batch for audit.

    Total_Unidades and Preco_Unitario are written as formulas so they recalculate.
    """
    service = service or get_service()
    compra_id = get_next_compra_id(spreadsheet_id, service=service)

    # Find next empty row
    result = service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id, range="Compras!A:A"
    ).execute()
    next_row = len(result.get("values", [])) + 1

    row_data = [[
        compra_id,
        data,
        produto_id,
        fornecedor_id,
        marca or "",
        qtde_embalagens,
        unidades_por_embalagem,
        f"=F{next_row}*G{next_row}",
        preco_total,
        f"=IF(H{next_row}>0;I{next_row}/H{next_row};0)",
        notas or "",
        frete if frete else "",
        desconto if desconto else "",
    ]]

    service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=f"Compras!A{next_row}",
        valueInputOption="USER_ENTERED",
        body={"values": row_data},
    ).execute()

    return compra_id


def distribute_frete_desconto(
    items: list[dict], frete: float = 0.0, desconto: float = 0.0,
) -> list[float]:
    """
    Return one effective preco_total per item, with frete and desconto rateado
    proportionally to each item's raw preco_total.

    Formula: ajuste_item = (frete - desconto) × (item.preco_total / subtotal).
    Falls back to equal split when subtotal == 0. Raises ValueError if the
    desconto would push any item negative — the user must fix the input.

    `items` is a list of dicts with at least a `preco_total` key (raw).
    """
    if not items:
        return []
    raws = [float(it.get("preco_total") or 0) for it in items]
    subtotal = sum(raws)
    n = len(items)
    ajuste_total = float(frete or 0) - float(desconto or 0)

    if subtotal > 0:
        pesos = [r / subtotal for r in raws]
    else:
        pesos = [1.0 / n] * n

    effectives = [raws[i] + ajuste_total * pesos[i] for i in range(n)]
    if any(e < 0 for e in effectives):
        raise ValueError(
            f"Desconto (R$ {desconto:.2f}) maior que o total da compra "
            f"(R$ {subtotal + (frete or 0):.2f}). Confere os valores."
        )
    return effectives
