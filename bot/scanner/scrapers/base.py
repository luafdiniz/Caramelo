"""Shared types across scrapers."""

from dataclasses import dataclass


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
