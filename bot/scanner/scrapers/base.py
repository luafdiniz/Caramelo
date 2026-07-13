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
    # Freight fields — populated by runner after picking best_of. Default 0
    # means "no freight consulted yet"; the classifier falls back to
    # preco_unidade in that case.
    frete: float = 0.0
    preco_com_frete: float = 0.0
    preco_unidade_com_frete: float = 0.0
    frete_prazo_dias: str = ""
