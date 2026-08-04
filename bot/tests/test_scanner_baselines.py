"""Unit tests for scanner.baselines — pure aggregation, no live I/O."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from unittest.mock import patch

from scanner import baselines
from scanner.baselines import (
    Baselines, Reference,
    _from_antiga, _fornecedor_short, _parse_brl,
)
from scanner.config import AlertaConfig


# --- _parse_brl -------------------------------------------------------------

def test_parse_brl_basic_variants():
    assert _parse_brl("R$ 1,32") == 1.32
    assert _parse_brl("1,32") == 1.32
    assert _parse_brl("1.32") == 1.32
    assert _parse_brl("R$ 1.234,56") == 1234.56
    assert _parse_brl("") is None
    assert _parse_brl(None) is None
    assert _parse_brl("--") is None


def test_parse_brl_ignores_currency_symbols():
    assert _parse_brl("  R$  10,50  ") == 10.50
    assert _parse_brl("R$1") == 1.0


# --- _fornecedor_short ------------------------------------------------------

def test_fornecedor_short_ml_variants():
    assert _fornecedor_short("Mercado Livre (EmbalaiadoSP)") == "ML EmbalaiadoSP"
    assert _fornecedor_short("Mercado Livre") == "ML"
    assert _fornecedor_short("Loja Santo Antonio") == "Loja Santo Antonio"
    assert _fornecedor_short("") == "?"


# --- _from_antiga -----------------------------------------------------------

def _fake_insumos():
    """Fixture: 3 rows for FORMA QUADRADA 220ML at different fornecedores.

    Mirrors the real antiga sheet: F-006 (Maria Chocolate), F-010 (ML Mimmos),
    F-011 (Santo Antônio). Only F-011 has col L populated (menor histórico).
    """
    return {
        "F-006": {
            "codigo": "F-006", "produto": "FORMA QUADRADA 220ML",
            "marca": "PLASTILANIA", "fornecedor": "Maria Chocolate",
            "valor_por_unidade": 1.49, "menor_historico": None,
        },
        "F-010": {
            "codigo": "F-010", "produto": "FORMA QUADRADA 220ML",
            "marca": "?", "fornecedor": "Mercado Livre (Mimmos Express)",
            "valor_por_unidade": 1.21, "menor_historico": None,
        },
        "F-011": {
            "codigo": "F-011", "produto": "FORMA QUADRADA 220ML",
            "marca": "PLASTILANIA", "fornecedor": "Loja Santo Antonio",
            "valor_por_unidade": 1.32, "menor_historico": 1.05,
        },
    }


def test_from_antiga_picks_min_across_fornecedores():
    codigos = ["F-006", "F-010", "F-011"]
    ultima, menor = _from_antiga(codigos, _fake_insumos())
    # ultima = MIN(1.49, 1.21, 1.32) = 1.21 from F-010
    assert ultima is not None
    assert ultima.valor == 1.21
    assert "F-010" in ultima.origem
    assert "ML Mimmos Express" in ultima.origem
    # menor = only F-011 has col L populated
    assert menor is not None
    assert menor.valor == 1.05
    assert "F-011" in menor.origem


def test_from_antiga_ignores_unknown_codes():
    codigos = ["F-006", "F-999", "F-XXX"]
    ultima, _ = _from_antiga(codigos, _fake_insumos())
    assert ultima is not None
    assert ultima.valor == 1.49  # only F-006 found


def test_from_antiga_empty_when_all_unknown():
    codigos = ["F-999", "F-XXX"]
    ultima, menor = _from_antiga(codigos, _fake_insumos())
    assert ultima is None
    assert menor is None


def test_from_antiga_no_codigos():
    ultima, menor = _from_antiga([], _fake_insumos())
    assert ultima is None
    assert menor is None


# --- get_references end-to-end ---------------------------------------------

def _alerta_with(codigos, insumo_id="FOR-005"):
    return AlertaConfig(
        scanner_id="SCA-TEST", insumo_id=insumo_id, ativo=True,
        termo_busca="x", sites=["ML"],
        marca_obrigatoria="PLASTILANIA", fallback_livre=False,
        duracao_snooze_dias=30, preco_alvo=None,
        ultimo_preco=None, ultima_verif=None, status="",
        snooze_ate=None, qtde_bulk=10, codigos_planilha=codigos,
    )


def test_get_references_menor_from_bot_compras_beats_antiga():
    """When nossa Compras has a cheaper record than antiga col. L, that wins."""
    with patch("scanner.baselines._from_nossa_compras") as mock_compras:
        mock_compras.return_value = Reference(0.98, "Compra 2026-07-15")
        b = baselines.get_references(
            _alerta_with(["F-006", "F-010", "F-011"]),
            spreadsheet_id="fake",
            service=object(),
            antiga_id="fake_antiga",
            _antiga_cache=_fake_insumos(),
        )
    assert b.ultima_compra.valor == 1.21
    assert b.menor_historico.valor == 0.98
    assert "Compra 2026-07-15" in b.menor_historico.origem


def test_get_references_antiga_wins_when_bot_is_higher():
    with patch("scanner.baselines._from_nossa_compras") as mock_compras:
        mock_compras.return_value = Reference(2.00, "Compra 2026-07-15")
        b = baselines.get_references(
            _alerta_with(["F-006", "F-010", "F-011"]),
            spreadsheet_id="fake",
            service=object(),
            antiga_id="fake_antiga",
            _antiga_cache=_fake_insumos(),
        )
    assert b.menor_historico.valor == 1.05
    assert "F-011" in b.menor_historico.origem


def test_get_references_no_codigos_still_returns_bot_compras():
    """No mapping in Scanner_Alertas → ultima_compra=None but bot Compras
    still contributes to menor_historico. Keeps the alert useful before the
    codigos_planilha column is filled in."""
    with patch("scanner.baselines._from_nossa_compras") as mock_compras:
        mock_compras.return_value = Reference(0.98, "Compra 2026-07-15")
        b = baselines.get_references(
            _alerta_with([]),
            spreadsheet_id="fake",
            service=object(),
            antiga_id="fake_antiga",
            _antiga_cache=_fake_insumos(),
        )
    assert b.ultima_compra is None
    assert b.menor_historico.valor == 0.98


def test_get_references_no_bot_compras_ok():
    with patch("scanner.baselines._from_nossa_compras", return_value=None):
        b = baselines.get_references(
            _alerta_with(["F-006", "F-011"]),
            spreadsheet_id="fake",
            service=object(),
            antiga_id="fake_antiga",
            _antiga_cache=_fake_insumos(),
        )
    assert b.ultima_compra.valor == 1.32  # MIN(1.49, 1.32)
    assert b.menor_historico.valor == 1.05
