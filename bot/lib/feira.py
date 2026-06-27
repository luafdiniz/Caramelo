"""
Modo Feira — registro leve de vendas durante um evento (feira de rua, bazar).

Diferente das Compras (insumos), uma feira é um evento efêmero onde a Luiza
sai com pudins de um ou mais tamanhos (ex: 200g a R$18 e 500g a R$45) e vai
vendendo. Cada venda é informal: "vendi 2 pro fulano", "vendi 2 de 500g agora",
"vendi 2, fulano vai voltar pra pagar". O bot registra na hora e, no fim, faz o
balanço (vendido × tamanho, voltou, dinheiro × pix, quem ficou fiado).

Persistência em duas abas da planilha do Caramelo:

- `Feiras` (cabeçalho do evento):
    A id | B data | C status | D descricao | E produtos_json | F chat_id
    G voltou_json | H dinheiro | I pix | J data_fechamento | K notas
  status ∈ {rascunho, aberta, fechada, cancelada}
  produtos_json: [{"tamanho":"200g","qtd_levada":63,"preco":18.0}, ...]
                 (qtd_levada e/ou preco podem ser null durante o rascunho)
  voltou_json:   {"200g": 5, "500g": 1}   (preenchido no fechamento)

- `VendasFeira` (uma linha por venda):
    A id | B feira_id | C data | D cliente_nome | E tamanho | F qtde
    G preco_unit | H preco_total | I forma_pagamento | J status_pagamento
    K status | L notas
  forma_pagamento ∈ {dinheiro, pix, ""}  (vazio quando fiado / não definido)
  status_pagamento ∈ {pago, fiado}
  status ∈ {ativa, cancelada}   (cancelada = desfeita pelo botão Desfazer)

Abas dedicadas (nome de cliente em texto livre, sem cadastro) são propositais:
mantêm a feira leve e não colidem com o plano maior `Tema D`.
"""

import os
import re
import json
from datetime import datetime

from . import sheets


FEIRAS_SHEET = "Feiras"
VENDAS_SHEET = "VendasFeira"

FEIRAS_HEADER = [
    "id", "data", "status", "descricao", "produtos_json", "chat_id",
    "voltou_json", "dinheiro", "pix", "data_fechamento", "notas",
]
VENDAS_HEADER = [
    "id", "feira_id", "data", "cliente_nome", "tamanho", "qtde",
    "preco_unit", "preco_total", "forma_pagamento", "status_pagamento",
    "status", "notas",
]


def _spreadsheet_id() -> str:
    return os.environ["SPREADSHEET_ID"]


def norm_tamanho(s) -> str:
    """Normalize a size label: '200g'/'de 500'/'1 kg' -> '200g'/'500g'/'1kg'."""
    s = str(s or "").lower().strip()
    if not s or s == "padrão":
        return "padrão"
    m = re.search(r"(\d+[.,]?\d*)\s*(kg|g)?", s)
    if m:
        num = m.group(1).replace(",", ".")
        if num.endswith(".0"):
            num = num[:-2]
        unit = m.group(2) or "g"
        return f"{num}{unit}"
    return s


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
            spreadsheetId=spreadsheet_id, range=f"{FEIRAS_SHEET}!A1",
            valueInputOption="RAW", body={"values": [FEIRAS_HEADER]},
        ).execute()
    if VENDAS_SHEET not in titles:
        service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id, range=f"{VENDAS_SHEET}!A1",
            valueInputOption="RAW", body={"values": [VENDAS_HEADER]},
        ).execute()


# ============================================================================
# Feiras
# ============================================================================

def _row_to_feira(r: list) -> dict:
    g = lambda i: r[i] if len(r) > i else ""
    try:
        produtos = json.loads(g(4)) if g(4) else []
    except (json.JSONDecodeError, TypeError):
        produtos = []
    try:
        voltou = json.loads(g(6)) if g(6) else {}
    except (json.JSONDecodeError, TypeError):
        voltou = {}
    return {
        "id": g(0),
        "data": g(1),
        "status": g(2),
        "descricao": g(3),
        "produtos": produtos,
        "chat_id": g(5),
        "voltou": voltou,
        "dinheiro": _to_float(g(7)) if g(7) != "" else None,
        "pix": _to_float(g(8)) if g(8) != "" else None,
        "data_fechamento": g(9),
        "notas": g(10),
    }


def get_active_feira(spreadsheet_id: str, chat_id: int, service=None) -> dict | None:
    """Return the latest feira with status 'aberta' or 'rascunho' for this chat."""
    service = service or sheets.get_service()
    ensure_feira_sheets(spreadsheet_id, service=service)
    result = service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id, range=f"{FEIRAS_SHEET}!A2:K"
    ).execute()
    rows = result.get("values", [])
    chat_str = str(chat_id)
    for r in reversed(rows):
        if not r or not r[0]:
            continue
        f = _row_to_feira(r)
        if f["status"] in ("aberta", "rascunho") and (f["chat_id"] == chat_str or f["chat_id"] == ""):
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


def create_feira(
    spreadsheet_id: str,
    chat_id: int,
    produtos: list,
    status: str = "aberta",
    descricao: str = "",
    data: str = "",
    service=None,
) -> str:
    """Append a new feira (status 'aberta' or 'rascunho'). Returns FEIRA-NNN."""
    service = service or sheets.get_service()
    ensure_feira_sheets(spreadsheet_id, service=service)
    new_id = sheets._next_id_for_prefix(spreadsheet_id, f"{FEIRAS_SHEET}!A:A", "FEIRA", service=service)
    data = data or datetime.now().strftime("%Y-%m-%d")
    service.spreadsheets().values().append(
        spreadsheetId=spreadsheet_id,
        range=f"{FEIRAS_SHEET}!A:K",
        valueInputOption="USER_ENTERED",
        body={"values": [[
            new_id, data, status, descricao or "",
            json.dumps(produtos, ensure_ascii=False), str(chat_id),
            "", "", "", "", "",
        ]]},
    ).execute()
    return new_id


def update_feira_produtos(spreadsheet_id: str, feira_id: str, produtos: list,
                          status: str | None = None, service=None) -> None:
    """Rewrite the produtos_json (E) and optionally the status (C)."""
    service = service or sheets.get_service()
    row = _feira_row_number(spreadsheet_id, feira_id, service=service)
    if not row:
        raise ValueError(f"Feira {feira_id} não encontrada.")
    service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id, range=f"{FEIRAS_SHEET}!E{row}",
        valueInputOption="USER_ENTERED",
        body={"values": [[json.dumps(produtos, ensure_ascii=False)]]},
    ).execute()
    if status is not None:
        service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id, range=f"{FEIRAS_SHEET}!C{row}",
            valueInputOption="USER_ENTERED", body={"values": [[status]]},
        ).execute()


def update_closing(spreadsheet_id: str, feira_id: str, voltou: dict | None = None,
                   dinheiro=None, pix=None, service=None) -> None:
    """Write provided closing fields (G/H/I) without closing the feira.

    `voltou` is merged into the existing voltou_json so the user can inform it in
    pieces. None means "leave as is".
    """
    service = service or sheets.get_service()
    row = _feira_row_number(spreadsheet_id, feira_id, service=service)
    if not row:
        raise ValueError(f"Feira {feira_id} não encontrada.")
    if voltou:
        # merge with existing
        cur = service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id, range=f"{FEIRAS_SHEET}!G{row}"
        ).execute().get("values", [[""]])
        existing = {}
        if cur and cur[0] and cur[0][0]:
            try:
                existing = json.loads(cur[0][0])
            except json.JSONDecodeError:
                existing = {}
        existing.update({norm_tamanho(k): v for k, v in voltou.items()})
        service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id, range=f"{FEIRAS_SHEET}!G{row}",
            valueInputOption="USER_ENTERED",
            body={"values": [[json.dumps(existing, ensure_ascii=False)]]},
        ).execute()
    if dinheiro is not None:
        service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id, range=f"{FEIRAS_SHEET}!H{row}",
            valueInputOption="USER_ENTERED", body={"values": [[dinheiro]]},
        ).execute()
    if pix is not None:
        service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id, range=f"{FEIRAS_SHEET}!I{row}",
            valueInputOption="USER_ENTERED", body={"values": [[pix]]},
        ).execute()


def finalize_feira(spreadsheet_id: str, feira_id: str, service=None) -> None:
    """Mark a feira fechada and stamp the closing date."""
    service = service or sheets.get_service()
    row = _feira_row_number(spreadsheet_id, feira_id, service=service)
    if not row:
        raise ValueError(f"Feira {feira_id} não encontrada.")
    data_fech = datetime.now().strftime("%Y-%m-%d")
    service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id, range=f"{FEIRAS_SHEET}!C{row}",
        valueInputOption="USER_ENTERED", body={"values": [["fechada"]]},
    ).execute()
    service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id, range=f"{FEIRAS_SHEET}!J{row}",
        valueInputOption="USER_ENTERED", body={"values": [[data_fech]]},
    ).execute()


def cancel_feira(spreadsheet_id: str, feira_id: str, service=None) -> None:
    """Mark a feira cancelada."""
    service = service or sheets.get_service()
    row = _feira_row_number(spreadsheet_id, feira_id, service=service)
    if not row:
        return
    service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id, range=f"{FEIRAS_SHEET}!C{row}",
        valueInputOption="USER_ENTERED", body={"values": [["cancelada"]]},
    ).execute()


# ============================================================================
# Produtos helpers (operate on the in-memory produtos list)
# ============================================================================

def produtos_completos(produtos: list) -> bool:
    """True if every product has both a qty and a price set."""
    if not produtos:
        return False
    return all(p.get("qtd_levada") not in (None, "") and p.get("preco") not in (None, "")
               for p in produtos)

def produtos_missing_preco(produtos: list) -> list:
    return [p for p in produtos if p.get("preco") in (None, "")]


def find_produto(produtos: list, tamanho: str) -> dict | None:
    """Match a size to a product by normalized tamanho."""
    if not produtos:
        return None
    nt = norm_tamanho(tamanho)
    for p in produtos:
        if norm_tamanho(p.get("tamanho")) == nt:
            return p
    return None


def produto_principal(produtos: list) -> dict | None:
    """The product with the largest qty taken (the main line), as the default."""
    if not produtos:
        return None
    return max(produtos, key=lambda p: float(p.get("qtd_levada") or 0))


# ============================================================================
# Vendas
# ============================================================================

def _row_to_venda(r: list) -> dict:
    g = lambda i: r[i] if len(r) > i else ""
    return {
        "id": g(0), "feira_id": g(1), "data": g(2), "cliente_nome": g(3),
        "tamanho": g(4), "qtde": _to_float(g(5)), "preco_unit": _to_float(g(6)),
        "preco_total": _to_float(g(7)), "forma_pagamento": g(8),
        "status_pagamento": g(9), "status": g(10), "notas": g(11),
    }


def append_venda(spreadsheet_id: str, feira_id: str, qtde: float, preco_unit: float,
                 tamanho: str = "", cliente_nome: str = "", forma_pagamento: str = "",
                 status_pagamento: str = "pago", notas: str = "", service=None) -> tuple[str, dict]:
    """Append a sale row. Returns (VEN-NNN id, venda dict)."""
    service = service or sheets.get_service()
    ensure_feira_sheets(spreadsheet_id, service=service)
    new_id = sheets._next_id_for_prefix(spreadsheet_id, f"{VENDAS_SHEET}!A:A", "VEN", service=service)
    data = datetime.now().strftime("%Y-%m-%d")
    preco_total = round(float(qtde) * float(preco_unit), 2)
    row = [
        new_id, feira_id, data, cliente_nome or "", tamanho or "",
        qtde, preco_unit, preco_total,
        forma_pagamento or "", status_pagamento or "pago", "ativa", notas or "",
    ]
    service.spreadsheets().values().append(
        spreadsheetId=spreadsheet_id, range=f"{VENDAS_SHEET}!A:L",
        valueInputOption="USER_ENTERED", body={"values": [row]},
    ).execute()
    return new_id, _row_to_venda(row)


def _venda_row_number(spreadsheet_id: str, venda_id: str, service=None):
    service = service or sheets.get_service()
    result = service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id, range=f"{VENDAS_SHEET}!A:L"
    ).execute()
    rows = result.get("values", [])
    for i, r in enumerate(rows):
        if r and r[0] == venda_id:
            return i + 1, _row_to_venda(r)
    return None, None


def cancel_venda(spreadsheet_id: str, venda_id: str, service=None) -> bool:
    """Soft-cancel a venda (Desfazer button). Returns True if it acted."""
    service = service or sheets.get_service()
    row, v = _venda_row_number(spreadsheet_id, venda_id, service=service)
    if not row or (v and v["status"] == "cancelada"):
        return False
    service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id, range=f"{VENDAS_SHEET}!K{row}",
        valueInputOption="RAW", body={"values": [["cancelada"]]},
    ).execute()
    return True


def move_venda(spreadsheet_id: str, venda_id: str, tamanho: str, preco_unit: float,
               service=None) -> dict | None:
    """Change a venda's size + unit price (and recompute total). Returns updated dict."""
    service = service or sheets.get_service()
    row, v = _venda_row_number(spreadsheet_id, venda_id, service=service)
    if not row or not v:
        return None
    preco_total = round(v["qtde"] * float(preco_unit), 2)
    # E=tamanho, F=qtde, G=preco_unit, H=preco_total
    service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id, range=f"{VENDAS_SHEET}!E{row}",
        valueInputOption="USER_ENTERED", body={"values": [[tamanho]]},
    ).execute()
    service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id, range=f"{VENDAS_SHEET}!G{row}:H{row}",
        valueInputOption="USER_ENTERED", body={"values": [[preco_unit, preco_total]]},
    ).execute()
    v["tamanho"] = tamanho
    v["preco_unit"] = float(preco_unit)
    v["preco_total"] = preco_total
    return v


def get_vendas(spreadsheet_id: str, feira_id: str, service=None, include_cancelled=False) -> list[dict]:
    """Return all sale rows for a feira (active only by default)."""
    service = service or sheets.get_service()
    result = service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id, range=f"{VENDAS_SHEET}!A2:L"
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
    """Aggregate a feira's active sales into a closing balance (per size + cash)."""
    produtos = feira.get("produtos") or []
    voltou = feira.get("voltou") or {}

    # Per-product breakdown
    prod_rows = []
    # start from declared produtos; also include any size that only appears in vendas
    tamanhos = []
    for p in produtos:
        tamanhos.append(norm_tamanho(p.get("tamanho")))
    for v in vendas:
        nt = norm_tamanho(v["tamanho"]) if v["tamanho"] else "padrão"
        if nt not in tamanhos:
            tamanhos.append(nt)

    for nt in tamanhos:
        p = find_produto(produtos, nt) or {}
        vend = [v for v in vendas if (norm_tamanho(v["tamanho"]) if v["tamanho"] else "padrão") == nt]
        vendido = sum(v["qtde"] for v in vend)
        faturado = round(sum(v["preco_total"] for v in vend), 2)
        qtd_levada = p.get("qtd_levada")
        qtd_levada = float(qtd_levada) if qtd_levada not in (None, "") else None
        volt = voltou.get(nt)
        volt = float(volt) if volt not in (None, "") else None
        nao_contab = None
        if qtd_levada is not None and volt is not None:
            nao_contab = round(qtd_levada - vendido - volt, 2)
        prod_rows.append({
            "tamanho": nt,
            "preco": (float(p["preco"]) if p.get("preco") not in (None, "") else None),
            "qtd_levada": qtd_levada,
            "vendido": vendido,
            "voltou": volt,
            "nao_contabilizada": nao_contab,
            "faturado": faturado,
        })

    qtde_vendida = sum(v["qtde"] for v in vendas)
    faturado_total = round(sum(v["preco_total"] for v in vendas), 2)
    dinheiro = round(sum(v["preco_total"] for v in vendas
                         if v["status_pagamento"] == "pago" and v["forma_pagamento"] == "dinheiro"), 2)
    pix = round(sum(v["preco_total"] for v in vendas
                    if v["status_pagamento"] == "pago" and v["forma_pagamento"] == "pix"), 2)
    pago_sem_forma = round(sum(v["preco_total"] for v in vendas
                              if v["status_pagamento"] == "pago" and v["forma_pagamento"] not in ("dinheiro", "pix")), 2)
    fiado_total = round(sum(v["preco_total"] for v in vendas if v["status_pagamento"] == "fiado"), 2)
    pago_total = round(dinheiro + pix + pago_sem_forma, 2)
    fiados = [
        {"nome": v["cliente_nome"] or "(sem nome)", "valor": v["preco_total"],
         "qtde": v["qtde"], "tamanho": v["tamanho"]}
        for v in vendas if v["status_pagamento"] == "fiado"
    ]

    recebido_informado = None
    divergencia_caixa = None
    f_din = feira.get("dinheiro")
    f_pix = feira.get("pix")
    if f_din is not None or f_pix is not None:
        recebido_informado = round((f_din or 0) + (f_pix or 0), 2)
        divergencia_caixa = round(recebido_informado - pago_total, 2)

    return {
        "produtos": prod_rows,
        "qtde_vendida": qtde_vendida,
        "faturado_total": faturado_total,
        "dinheiro": dinheiro,
        "pix": pix,
        "pago_sem_forma": pago_sem_forma,
        "pago_total": pago_total,
        "fiado_total": fiado_total,
        "fiados": fiados,
        "n_vendas": len(vendas),
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
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return 0.0
