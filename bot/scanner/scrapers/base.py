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
