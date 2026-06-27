"""
Modo Feira — registro leve de vendas durante um evento (feira de rua, bazar).

Diferente das Compras (insumos), uma feira é um evento efêmero onde a Luiza
sai com N pudins e vai vendendo. Cada venda é informal: "vendi 2 pro fulano",
"vendi 2 agora", "vendi 2, fulano vai voltar pra pagar". O bot registra na hora
e, no fim, faz o balanço (vendido, voltou, dinheiro × pix, quem ficou fiado).

Persistência em duas abas da planilha do Caramelo:

- `Feiras` (cabeçalho do evento):
    A id | B data | C status | D descricao | E qtd_levada | F preco_unit
    G chat_id | H qtd_voltou | I dinheiro | J pix | K data_fechamento | L notas
  status ∈ {aberta, fechada, cancelada}

- `VendasFeira` (uma linha por venda):
    A id | B feira_id | C data | D cliente_nome | E qtde | F preco_unit
    G preco_total | H forma_pagamento | I status_pagamento | J status | K notas
  forma_pagamento ∈ {dinheiro, pix, ""}  (vazio quando ainda não definido / fiado)
  status_pagamento ∈ {pago, fiado}
  status ∈ {ativa, cancelada}   (cancelada = desfeita pelo botão Desfazer)

Este módulo é independente do fluxo de Compras (orchestrator.py). A escolha de
abas dedicadas (e nome de cliente em texto livre, sem cadastro) é proposital:
mantém a feira leve e não colide com o plano maior `Tema D` (Clientes/Vendas/
Preços B2B), que continua valendo pra quando o atacado justificar.
"""

import os
from datetime import datetime

from . import sheets


FEIRAS_SHEET = "Feiras"
VENDAS_SHEET = "VendasFeira"

FEIRAS_HEADER = [
    "id", "data", "status", "descricao", "qtd_levada", "preco_unit",
    "chat_id", "qtd_voltou", "dinheiro", "pix", "data_fechamento", "notas",
]
VENDAS_HEADER = [
    "id", "feira_id", "data", "cliente_nome", "qtde", "preco_unit",
    "preco_total", "forma_pagamento", "status_pagamento", "status", "notas",
]


def _spreadsheet_id() -> str:
    return os.environ["SPREADSHEET_ID"]


# ============================================================================
# Setup — create tabs on first use
# ============================================================================

def ensure_feira_sheets(spreadsheet_id: str, service=None) -> None:
    """Create the Feiras and VendasFeira tabs (with headers) if missing."""
    service = service or sheets.get_service()
    meta = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    titles = [s["properties"]["title"] for s in meta["sheets"]]

    requests = []
    if FEIRAS_SHEET not in titles:
        requests.append({"addSheet": {"properties": {"title": FEIRAS_SHEET}}})
    if VENDAS_SHEET not in titles:
        requests.append({"addSheet": {"properties": {"title": VENDAS_SHEET}}})
    if requests:
        service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id, body={"requests": requests}
        ).execute()

    if FEIRAS_SHEET not in titles:
        service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range=f"{FEIRAS_SHEET}!A1",
            valueInputOption="RAW",
            body={"values": [FEIRAS_HEADER]},
        ).execute()
    if VENDAS_SHEET not in titles:
        service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range=f"{VENDAS_SHEET}!A1",
            valueInputOption="RAW",
            body={"values": [VENDAS_HEADER]},
        ).execute()


# ============================================================================
# Feiras
# ============================================================================

def _row_to_feira(r: list) -> dict:
    g = lambda i: r[i] if len(r) > i else ""
    return {
        "id": g(0),
        "data": g(1),
        "status": g(2),
        "descricao": g(3),
        "qtd_levada": _to_float(g(4)),
        "preco_unit": _to_float(g(5)),
        "chat_id": g(6),
        "qtd_voltou": _to_float(g(7)) if g(7) != "" else None,
        "dinheiro": _to_float(g(8)) if g(8) != "" else None,
        "pix": _to_float(g(9)) if g(9) != "" else None,
        "data_fechamento": g(10),
        "notas": g(11),
    }


def get_open_feira(spreadsheet_id: str, chat_id: int, service=None) -> dict | None:
    """Return the latest feira with status='aberta' for this chat, or None."""
    service = service or sheets.get_service()
    ensure_feira_sheets(spreadsheet_id, service=service)
    result = service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id, range=f"{FEIRAS_SHEET}!A2:L"
    ).execute()
    rows = result.get("values", [])
    chat_str = str(chat_id)
    for r in reversed(rows):
        if not r or not r[0]:
            continue
        f = _row_to_feira(r)
        if f["status"] == "aberta" and (f["chat_id"] == chat_str or f["chat_id"] == ""):
            return f
    return None


def _feira_row_number(spreadsheet_id: str, feira_id: str, service=None) -> int | None:
    service = service or sheets.get_service()
    result = service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id, range=f"{FEIRAS_SHEET}!A:A"
    ).execute()
    rows = result.get("values", [])
    for i, r in enumerate(rows):
        if r and r[0] == feira_id:
            return i + 1
    return None


def open_feira(
    spreadsheet_id: str,
    chat_id: int,
    qtd_levada: float,
    preco_unit: float,
    descricao: str = "",
    data: str = "",
    service=None,
) -> str:
    """Append a new open feira. Returns the FEIRA-NNN id."""
    service = service or sheets.get_service()
    ensure_feira_sheets(spreadsheet_id, service=service)
    new_id = sheets._next_id_for_prefix(spreadsheet_id, f"{FEIRAS_SHEET}!A:A", "FEIRA", service=service)
    data = data or datetime.now().strftime("%Y-%m-%d")

    service.spreadsheets().values().append(
        spreadsheetId=spreadsheet_id,
        range=f"{FEIRAS_SHEET}!A:L",
        valueInputOption="USER_ENTERED",
        body={"values": [[
            new_id, data, "aberta", descricao or "",
            qtd_levada, preco_unit, str(chat_id),
            "", "", "", "", "",
        ]]},
    ).execute()
    return new_id


def close_feira(
    spreadsheet_id: str,
    feira_id: str,
    qtd_voltou=None,
    dinheiro=None,
    pix=None,
    service=None,
) -> None:
    """Mark a feira fechada and write the closing counts."""
    service = service or sheets.get_service()
    row = _feira_row_number(spreadsheet_id, feira_id, service=service)
    if not row:
        raise ValueError(f"Feira {feira_id} não encontrada.")
    data_fech = datetime.now().strftime("%Y-%m-%d")
    # C=status, H=qtd_voltou, I=dinheiro, J=pix, K=data_fechamento
    service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=f"{FEIRAS_SHEET}!C{row}",
        valueInputOption="USER_ENTERED",
        body={"values": [["fechada"]]},
    ).execute()
    service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=f"{FEIRAS_SHEET}!H{row}:K{row}",
        valueInputOption="USER_ENTERED",
        body={"values": [[
            "" if qtd_voltou is None else qtd_voltou,
            "" if dinheiro is None else dinheiro,
            "" if pix is None else pix,
            data_fech,
        ]]},
    ).execute()


def update_closing(
    spreadsheet_id: str,
    feira_id: str,
    qtd_voltou=None,
    dinheiro=None,
    pix=None,
    service=None,
) -> None:
    """Write only the provided closing fields (H/I/J) without closing the feira.

    Lets the user inform the balance in pieces ("voltaram 5" then "recebi 200
    no dinheiro"). None means "leave as is".
    """
    service = service or sheets.get_service()
    row = _feira_row_number(spreadsheet_id, feira_id, service=service)
    if not row:
        raise ValueError(f"Feira {feira_id} não encontrada.")
    updates = []
    if qtd_voltou is not None:
        updates.append((f"{FEIRAS_SHEET}!H{row}", qtd_voltou))
    if dinheiro is not None:
        updates.append((f"{FEIRAS_SHEET}!I{row}", dinheiro))
    if pix is not None:
        updates.append((f"{FEIRAS_SHEET}!J{row}", pix))
    for rng, val in updates:
        service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range=rng,
            valueInputOption="USER_ENTERED",
            body={"values": [[val]]},
        ).execute()


def finalize_feira(spreadsheet_id: str, feira_id: str, service=None) -> None:
    """Mark a feira fechada and stamp the closing date (closing counts already set)."""
    service = service or sheets.get_service()
    row = _feira_row_number(spreadsheet_id, feira_id, service=service)
    if not row:
        raise ValueError(f"Feira {feira_id} não encontrada.")
    data_fech = datetime.now().strftime("%Y-%m-%d")
    service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=f"{FEIRAS_SHEET}!C{row}",
        valueInputOption="USER_ENTERED",
        body={"values": [["fechada"]]},
    ).execute()
    service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=f"{FEIRAS_SHEET}!K{row}",
        valueInputOption="USER_ENTERED",
        body={"values": [[data_fech]]},
    ).execute()


def cancel_feira(spreadsheet_id: str, feira_id: str, service=None) -> None:
    """Mark a feira cancelada (used by /cancel when a feira is the active flow)."""
    service = service or sheets.get_service()
    row = _feira_row_number(spreadsheet_id, feira_id, service=service)
    if not row:
        return
    service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=f"{FEIRAS_SHEET}!C{row}",
        valueInputOption="USER_ENTERED",
        body={"values": [["cancelada"]]},
    ).execute()


# ============================================================================
# Vendas
# ============================================================================

def _row_to_venda(r: list) -> dict:
    g = lambda i: r[i] if len(r) > i else ""
    return {
        "id": g(0),
        "feira_id": g(1),
        "data": g(2),
        "cliente_nome": g(3),
        "qtde": _to_float(g(4)),
        "preco_unit": _to_float(g(5)),
        "preco_total": _to_float(g(6)),
        "forma_pagamento": g(7),
        "status_pagamento": g(8),
        "status": g(9),
        "notas": g(10),
    }


def append_venda(
    spreadsheet_id: str,
    feira_id: str,
    qtde: float,
    preco_unit: float,
    cliente_nome: str = "",
    forma_pagamento: str = "",
    status_pagamento: str = "pago",
    notas: str = "",
    service=None,
) -> tuple[str, dict]:
    """Append a sale row. Returns (VEN-NNN id, venda dict)."""
    service = service or sheets.get_service()
    ensure_feira_sheets(spreadsheet_id, service=service)
    new_id = sheets._next_id_for_prefix(spreadsheet_id, f"{VENDAS_SHEET}!A:A", "VEN", service=service)
    data = datetime.now().strftime("%Y-%m-%d")
    preco_total = round(float(qtde) * float(preco_unit), 2)

    row = [
        new_id, feira_id, data, cliente_nome or "",
        qtde, preco_unit, preco_total,
        forma_pagamento or "", status_pagamento or "pago", "ativa", notas or "",
    ]
    service.spreadsheets().values().append(
        spreadsheetId=spreadsheet_id,
        range=f"{VENDAS_SHEET}!A:K",
        valueInputOption="USER_ENTERED",
        body={"values": [row]},
    ).execute()
    return new_id, _row_to_venda(row)


def cancel_venda(spreadsheet_id: str, venda_id: str, service=None) -> bool:
    """Soft-cancel a venda (Desfazer button). Returns True if it acted."""
    service = service or sheets.get_service()
    result = service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id, range=f"{VENDAS_SHEET}!A:K"
    ).execute()
    rows = result.get("values", [])
    for i, r in enumerate(rows):
        if r and r[0] == venda_id:
            if len(r) > 9 and r[9] == "cancelada":
                return False  # already cancelled
            service.spreadsheets().values().update(
                spreadsheetId=spreadsheet_id,
                range=f"{VENDAS_SHEET}!J{i + 1}",
                valueInputOption="RAW",
                body={"values": [["cancelada"]]},
            ).execute()
            return True
    return False


def get_vendas(spreadsheet_id: str, feira_id: str, service=None, include_cancelled=False) -> list[dict]:
    """Return all sale rows for a feira (active only by default)."""
    service = service or sheets.get_service()
    result = service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id, range=f"{VENDAS_SHEET}!A2:K"
    ).execute()
    rows = result.get("values", [])
    out = []
    for r in rows:
        if not r or not r[0]:
            continue
        v = _row_to_venda(r)
        if v["feira_id"] != feira_id:
            continue
        if not include_cancelled and v["status"] == "cancelada":
            continue
        out.append(v)
    return out


# ============================================================================
# Balanço — pure computation (no I/O, easy to test)
# ============================================================================

def compute_balanco(feira: dict, vendas: list[dict]) -> dict:
    """
    Aggregate a feira's active sales into a closing balance.

    Returns a dict with:
      - qtde_vendida, faturado_total
      - dinheiro, pix, fiado (somas por forma/status de pagamento, calculados)
      - pago_total (dinheiro + pix + outros pagos sem forma definida)
      - fiados: lista de {nome, valor} ainda em aberto
      - qtd_levada, qtd_voltou, qtd_nao_contabilizada (levada - vendida - voltou)
      - recebido_informado (dinheiro+pix do fechamento), divergencia_caixa
    """
    qtde_vendida = sum(v["qtde"] for v in vendas)
    faturado_total = round(sum(v["preco_total"] for v in vendas), 2)

    dinheiro = round(sum(v["preco_total"] for v in vendas
                         if v["status_pagamento"] == "pago" and v["forma_pagamento"] == "dinheiro"), 2)
    pix = round(sum(v["preco_total"] for v in vendas
                    if v["status_pagamento"] == "pago" and v["forma_pagamento"] == "pix"), 2)
    pago_sem_forma = round(sum(v["preco_total"] for v in vendas
                              if v["status_pagamento"] == "pago" and v["forma_pagamento"] not in ("dinheiro", "pix")), 2)
    fiado_total = round(sum(v["preco_total"] for v in vendas
                           if v["status_pagamento"] == "fiado"), 2)
    pago_total = round(dinheiro + pix + pago_sem_forma, 2)

    fiados = [
        {"nome": v["cliente_nome"] or "(sem nome)", "valor": v["preco_total"], "qtde": v["qtde"]}
        for v in vendas if v["status_pagamento"] == "fiado"
    ]

    qtd_levada = feira.get("qtd_levada") or 0
    qtd_voltou = feira.get("qtd_voltou")
    qtd_nao_contabilizada = None
    if qtd_levada and qtd_voltou is not None:
        qtd_nao_contabilizada = round(qtd_levada - qtde_vendida - qtd_voltou, 2)

    recebido_informado = None
    divergencia_caixa = None
    f_din = feira.get("dinheiro")
    f_pix = feira.get("pix")
    if f_din is not None or f_pix is not None:
        recebido_informado = round((f_din or 0) + (f_pix or 0), 2)
        divergencia_caixa = round(recebido_informado - pago_total, 2)

    return {
        "qtde_vendida": qtde_vendida,
        "faturado_total": faturado_total,
        "dinheiro": dinheiro,
        "pix": pix,
        "pago_sem_forma": pago_sem_forma,
        "pago_total": pago_total,
        "fiado_total": fiado_total,
        "fiados": fiados,
        "n_vendas": len(vendas),
        "qtd_levada": qtd_levada,
        "qtd_voltou": qtd_voltou,
        "qtd_nao_contabilizada": qtd_nao_contabilizada,
        "recebido_informado": recebido_informado,
        "divergencia_caixa": divergencia_caixa,
    }


# ============================================================================
# helpers
# ============================================================================

def _to_float(v) -> float:
    if v is None or v == "":
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace("R$", "").replace(" ", "")
    # pt-BR: "1.234,56" -> "1234.56"; also handle "36,00" and "36.00"
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return 0.0
