"""Shared types across scrapers."""

from dataclasses import dataclass, field


@dataclass
class ProductResult:
    site: str
    url: str
    titulo: str
    preco: float
    preco_lista: float
    marca_detectada: str
    qtde_unidades: int
    preco_unidade: float
    disponivel: bool
    tem_oferta_clube: bool
    marca_confirmada: bool
    sku_id: str = ""
    seller_id: str = "1"
    # Freight fields — populated by runner after picking best_of.
    # Primary values (bulk cart of qtde_bulk unidades — the realistic cart):
    frete: float = 0.0
    preco_com_frete: float = 0.0
    preco_unidade_com_frete: float = 0.0
    frete_prazo_dias: str = ""
    bulk_qtde: int = 1
    # Comparison values (1 unit cart — for showing "diluição" in notifs):
    frete_1un: float = 0.0
    preco_com_frete_1un: float = 0.0
    preco_unidade_com_frete_1un: float = 0.0
    # Freight curve: list of {"qtde", "frete", "preco_unid_delivered", ...}
    # dicts, sorted by qtde. Enables the "how much do I need to buy to zero
    # the freight?" breakdown in notifications.
    frete_curve: list[dict] = field(default_factory=list)
    # Names of active promotional teasers (e.g. "50% no 2°"). Empty when
    # the shelf has no conditional promo.
    promocoes: list[str] = field(default_factory=list)
    # Base measure extracted from the title (e.g. 0.395kg from "395g").
    # Enables displaying "R$/kg" alongside "R$/un".
    medida_valor: float = 0.0
    medida_unidade: str = ""
