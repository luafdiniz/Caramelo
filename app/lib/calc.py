"""
Multi-directional calculator for receita ↔ produção ↔ preço.

Six presets cover the questions Luiza actually asks. Each preset is a small
pure function that takes a `CalcState` (everything that might matter) and
returns a new state with the derived fields filled in.

The equations are scalar and well-conditioned — no need for sympy or a
dependency graph engine. Substitution in the right order is enough.
"""

from __future__ import annotations
from dataclasses import dataclass, replace, field
from typing import Optional


PRESETS = [
    ("custo_e_margem",     "Custo unitário e margem"),
    ("preco_para_margem",  "Preço de venda pra atingir margem alvo"),
    ("qtde_para_faturar",  "Quantas unidades pra atingir meta de faturamento"),
    ("kg_com_orcamento",   "Quantos kg consigo produzir com um orçamento de insumos"),
    ("resultado_fornada",  "Faturamento e lucro de uma fornada inteira"),
    ("preco_kg_unid",      "Conversor: preço por kg ↔ preço por unidade"),
]
PRESET_LABELS = dict(PRESETS)
PRESET_KEYS = [k for k, _ in PRESETS]


@dataclass
class CalcState:
    # Inputs / outputs — every field is optional. None = "unknown".
    peso_base_receita: Optional[float] = None     # kg ou L de massa pronta
    peso_base_padrao: Optional[float] = None      # peso da receita cadastrada
    custo_ingredientes_padrao: Optional[float] = None  # custo da receita cadastrada inteira
    custo_embalagem_unit: Optional[float] = None  # R$/unidade vendida
    peso_unit: Optional[float] = None             # kg/unidade do tamanho
    qtde_unidades_produzidas: Optional[float] = None
    custo_ingredientes_total: Optional[float] = None
    custo_total: Optional[float] = None
    custo_unit: Optional[float] = None
    preco_venda_unit: Optional[float] = None
    preco_venda_kg: Optional[float] = None
    faturamento: Optional[float] = None
    lucro_total: Optional[float] = None
    lucro_unit: Optional[float] = None
    margem: Optional[float] = None                # fração (0.50 = 50%)
    markup: Optional[float] = None                # razão (3 = 3×)
    meta_faturamento: Optional[float] = None
    orcamento_insumos: Optional[float] = None

    warnings: list[str] = field(default_factory=list)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)


def _scale_ingredientes(s: CalcState) -> None:
    """Compute custo_ingredientes_total proportional to peso_base_receita."""
    if (
        s.peso_base_receita is None
        or s.peso_base_padrao in (None, 0)
        or s.custo_ingredientes_padrao is None
    ):
        return
    ratio = s.peso_base_receita / s.peso_base_padrao
    s.custo_ingredientes_total = s.custo_ingredientes_padrao * ratio


def _qtde_unidades(s: CalcState) -> None:
    if s.peso_base_receita is None or s.peso_unit in (None, 0):
        return
    s.qtde_unidades_produzidas = s.peso_base_receita / s.peso_unit


def _custo_total(s: CalcState) -> None:
    if (
        s.custo_ingredientes_total is None
        or s.custo_embalagem_unit is None
        or s.qtde_unidades_produzidas is None
    ):
        return
    s.custo_total = s.custo_ingredientes_total + s.custo_embalagem_unit * s.qtde_unidades_produzidas
    if s.qtde_unidades_produzidas > 0:
        s.custo_unit = s.custo_total / s.qtde_unidades_produzidas


def _resultado(s: CalcState) -> None:
    if s.preco_venda_unit is None or s.qtde_unidades_produzidas is None:
        return
    s.faturamento = s.preco_venda_unit * s.qtde_unidades_produzidas
    if s.custo_total is not None:
        s.lucro_total = s.faturamento - s.custo_total
        if s.qtde_unidades_produzidas > 0:
            s.lucro_unit = s.lucro_total / s.qtde_unidades_produzidas
        if s.preco_venda_unit > 0 and s.lucro_unit is not None:
            s.margem = s.lucro_unit / s.preco_venda_unit
        if s.custo_unit and s.custo_unit > 0:
            s.markup = s.preco_venda_unit / s.custo_unit
    if s.peso_unit and s.peso_unit > 0:
        s.preco_venda_kg = s.preco_venda_unit / s.peso_unit


def _sanity(s: CalcState) -> None:
    if s.lucro_total is not None and s.lucro_total < 0:
        s.warn("⚠️ Lucro negativo — está vendendo no prejuízo.")
    if s.margem is not None and s.margem < 0:
        s.warn("⚠️ Margem negativa.")
    if s.margem is not None and s.margem > 0.95:
        s.warn("⚠️ Margem acima de 95% — confere se custo/preço estão certos.")
    if (
        s.custo_total is not None
        and s.faturamento is not None
        and s.custo_total > s.faturamento
    ):
        s.warn("⚠️ Custo total acima do faturamento — vai dar prejuízo.")
    if s.qtde_unidades_produzidas is not None and s.qtde_unidades_produzidas % 1 != 0:
        sobra_g = (s.qtde_unidades_produzidas % 1) * (s.peso_unit or 0) * 1000
        if sobra_g > 1:
            s.warn(f"Sobra ~{sobra_g:.0f} g de massa depois das unidades inteiras.")


# --- Presets ----------------------------------------------------------------

def solve_custo_e_margem(s: CalcState) -> CalcState:
    """Default: dado um Tamanho cadastrado, calcula custo, lucro e margem."""
    s = replace(s)
    _scale_ingredientes(s)
    _qtde_unidades(s)
    _custo_total(s)
    _resultado(s)
    _sanity(s)
    return s


def solve_preco_para_margem(s: CalcState, margem_alvo: float) -> CalcState:
    """Inverso da E9 + E7: dado custo_unit e margem alvo, devolve preço unitário."""
    s = replace(s)
    _scale_ingredientes(s)
    _qtde_unidades(s)
    _custo_total(s)
    if s.custo_unit is None:
        s.warn("Falta custo unitário (preencha receita + peso_unit).")
        return s
    if margem_alvo >= 1:
        s.warn("Margem alvo precisa ser < 100%.")
        return s
    s.preco_venda_unit = s.custo_unit / (1 - margem_alvo)
    _resultado(s)
    _sanity(s)
    return s


def solve_qtde_para_faturar(s: CalcState) -> CalcState:
    """Quantas unidades pra atingir meta_faturamento, dado preco_venda_unit."""
    s = replace(s)
    if s.meta_faturamento is None or not s.preco_venda_unit:
        s.warn("Preencha meta de faturamento e preço de venda unitário.")
        return s
    s.qtde_unidades_produzidas = s.meta_faturamento / s.preco_venda_unit
    if s.peso_unit:
        s.peso_base_receita = s.qtde_unidades_produzidas * s.peso_unit
    _scale_ingredientes(s)
    _custo_total(s)
    _resultado(s)
    _sanity(s)
    return s


def solve_kg_com_orcamento(s: CalcState) -> CalcState:
    """Quantos kg de massa cabem em orcamento_insumos."""
    s = replace(s)
    if (
        s.orcamento_insumos is None
        or s.peso_base_padrao in (None, 0)
        or s.custo_ingredientes_padrao in (None, 0)
    ):
        s.warn("Preencha orçamento e dados da receita base.")
        return s
    custo_por_kg = s.custo_ingredientes_padrao / s.peso_base_padrao
    if custo_por_kg <= 0:
        s.warn("Custo da receita base inválido.")
        return s
    s.peso_base_receita = s.orcamento_insumos / custo_por_kg
    _scale_ingredientes(s)
    _qtde_unidades(s)
    _custo_total(s)
    _resultado(s)
    _sanity(s)
    return s


def solve_resultado_fornada(s: CalcState) -> CalcState:
    """Dado peso_base_receita + preço unitário + tamanho, fatura/lucro da fornada."""
    s = replace(s)
    _scale_ingredientes(s)
    _qtde_unidades(s)
    _custo_total(s)
    _resultado(s)
    _sanity(s)
    return s


def solve_preco_kg_unid(s: CalcState) -> CalcState:
    """Conversor simples: preco_venda_kg ↔ preco_venda_unit dado peso_unit."""
    s = replace(s)
    if s.peso_unit in (None, 0):
        s.warn("Preencha o peso unitário pra fazer a conversão.")
        return s
    if s.preco_venda_unit is not None and s.preco_venda_kg is None:
        s.preco_venda_kg = s.preco_venda_unit / s.peso_unit
    elif s.preco_venda_kg is not None and s.preco_venda_unit is None:
        s.preco_venda_unit = s.preco_venda_kg * s.peso_unit
    return s


SOLVERS = {
    "custo_e_margem":     solve_custo_e_margem,
    "preco_para_margem":  solve_preco_para_margem,
    "qtde_para_faturar":  solve_qtde_para_faturar,
    "kg_com_orcamento":   solve_kg_com_orcamento,
    "resultado_fornada":  solve_resultado_fornada,
    "preco_kg_unid":      solve_preco_kg_unid,
}
