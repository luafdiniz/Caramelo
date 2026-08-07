"""Unit tests for dimension → volume mapping in scanner.extractor."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scanner.extractor import _derive_specs_from_dimensions, matches_search_intent


def test_derive_specs_from_dimensions_known():
    assert _derive_specs_from_dimensions("Forma para Pudim 16x6 cm c/ 6 un") == {"500ml", "0.5l"}
    assert _derive_specs_from_dimensions("Forma para Pudim 9x6,5x4 cm") == {"220ml", "0.22l"}
    assert _derive_specs_from_dimensions("Forma para Pudim 8x5x4 cm") == {"80ml", "0.08l"}


def test_derive_specs_from_dimensions_unknown_or_none():
    assert _derive_specs_from_dimensions("Forma Pudim generica") == set()
    assert _derive_specs_from_dimensions("") == set()
    assert _derive_specs_from_dimensions(None) == set()
    # Dimensão não catalogada → não deriva
    assert _derive_specs_from_dimensions("Forma 30x20 cm") == set()


def test_matches_search_intent_with_dimension_mapping():
    """Products from Maria Chocolate use dimensions in cm, not volumes.
    matches_search_intent should accept them when the mapping applies."""
    # 500ml na busca ↔ 16x6 cm no título
    assert matches_search_intent(
        "forma pudim 500ml plastilania",
        "Forma para Pudim 16x6 cm c/ 6 unidades - Plastilânia",
    )
    # 220ml na busca ↔ 9x6,5x4 cm no título
    assert matches_search_intent(
        "forma pudim 220ml plastilania",
        "Forma para Pudim 9x6,5x4 cm c/ 10 unidades - Plastilânia",
    )


def test_matches_search_intent_still_rejects_wrong_volume():
    """500ml ≠ 220ml — o mapping não pode virar falso positivo."""
    assert not matches_search_intent(
        "forma pudim 500ml plastilania",
        "Forma para Pudim 9x6,5x4 cm c/ 10 unidades - Plastilânia",  # esse é 220ml
    )
    # 1100ml não tem dimensão mapeada — nada bate
    assert not matches_search_intent(
        "forma pudim 1100ml plastilania",
        "Forma para Pudim 16x6 cm c/ 6 unidades - Plastilânia",
    )


def test_matches_search_intent_preserves_existing_behavior():
    """Buscas com volume nominal no título continuam funcionando."""
    assert matches_search_intent(
        "leite condensado 395g",
        "Leite Condensado Cemil 395g",
    )
    assert not matches_search_intent(
        "leite condensado 395g",
        "Leite Condensado 200g",
    )
