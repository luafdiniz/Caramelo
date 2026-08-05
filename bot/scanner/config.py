"""Scanner config loader.

Reads Scanner_Alertas tab and parses each row into an AlertaConfig. All I/O
lives here — the rest of the scanner works with plain dataclasses.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from lib import sheets


VALID_SITES = {"ML", "supernosso", "apoio", "santoantonio"}


@dataclass
class AlertaConfig:
    scanner_id: str
    insumo_id: str
    ativo: bool
    termo_busca: str
    sites: list[str]
    marca_obrigatoria: str
    fallback_livre: bool
    duracao_snooze_dias: int
    preco_alvo: Optional[float]
    ultimo_preco: Optional[float]
    ultima_verif: Optional[datetime]
    status: str
    snooze_ate: Optional[datetime]
    qtde_bulk: int = 1
    # Códigos da planilha antiga ("CUSTOS PUDIM - 2025") que mapeiam pra este
    # scanner. Ex: FOR-005 (220ml) → ["F-006", "F-010", "F-011"] (mesma forma
    # em 3 fornecedores diferentes). Usado por scanner.baselines pra buscar
    # última compra + menor histórico cross-fornecedor.
    codigos_planilha: list[str] = field(default_factory=list)
    # Override do termo_busca só pra ML — o /products/search do catálogo
    # unificado é sensível à ordem das palavras. Ex: "pote quadrado 220ml
    # plastilania" não acha, mas "plastilania 220ml" acha. Vazio = usa
    # `termo_busca`.
    ml_query: str = ""


def _parse_bool(v) -> bool:
    return str(v or "").strip().upper() == "TRUE"


def _parse_float(v) -> Optional[float]:
    s = str(v or "").strip()
    if not s:
        return None
    try:
        return float(s.replace(",", "."))
    except ValueError:
        return None


def _parse_int(v, default: int = 30) -> int:
    s = str(v or "").strip()
    if not s:
        return default
    try:
        return int(float(s))
    except ValueError:
        return default


def _parse_iso_datetime(v) -> Optional[datetime]:
    s = str(v or "").strip()
    if not s:
        return None
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None


def get_alertas(spreadsheet_id: str, service=None) -> list[AlertaConfig]:
    """Load every row of Scanner_Alertas, active or not."""
    service = service or sheets.get_service()
    result = service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id, range="Scanner_Alertas!A2:P"
    ).execute()
    rows = result.get("values", [])
    out: list[AlertaConfig] = []
    for r in rows:
        if not r or not r[0]:
            continue
        r = list(r) + [""] * (16 - len(r))
        sites_raw = r[4] or ""
        sites = [s.strip() for s in sites_raw.split(",") if s.strip() in VALID_SITES]
        codigos = [c.strip() for c in (r[14] or "").split(",") if c.strip()]
        out.append(AlertaConfig(
            scanner_id=r[0],
            insumo_id=r[1],
            ativo=_parse_bool(r[2]),
            termo_busca=(r[3] or "").strip(),
            sites=sites,
            marca_obrigatoria=(r[5] or "").strip().upper(),
            fallback_livre=_parse_bool(r[6]),
            duracao_snooze_dias=_parse_int(r[7], default=30),
            preco_alvo=_parse_float(r[8]),
            ultimo_preco=_parse_float(r[9]),
            ultima_verif=_parse_iso_datetime(r[10]),
            status=(r[11] or "").strip(),
            snooze_ate=_parse_iso_datetime(r[12]),
            qtde_bulk=_parse_int(r[13], default=1),
            codigos_planilha=codigos,
            ml_query=(r[15] or "").strip(),
        ))
    return out


def get_active_alertas(spreadsheet_id: str, service=None) -> list[AlertaConfig]:
    return [a for a in get_alertas(spreadsheet_id, service) if a.ativo]


def is_in_snooze(alerta: AlertaConfig, now: Optional[datetime] = None) -> bool:
    if not alerta.snooze_ate:
        return False
    return (now or datetime.now()) < alerta.snooze_ate
