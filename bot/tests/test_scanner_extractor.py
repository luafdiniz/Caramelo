"""Tests for scanner extractor helpers. Runs as `python tests/test_scanner_extractor.py`."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scanner.extractor import (
    extract_qtde_unidades,
    brand_confirmed_in,
    preco_por_unidade,
)


def _check(name, cond, detail=""):
    if cond:
        print(f"  PASS  {name}")
    else:
        print(f"  FAIL  {name}  {detail}")
        raise AssertionError(f"{name}: {detail}")


def test_qtde_variants():
    cases = [
        ("Pote Quadrado Com Lacre 220ml 10 Unidades PLASTILÂNIA", 10),
        ("Pote Quadrado 220ml 200 Unidades PLASTILÂNIA", 200),
        ("Forma Para Pudim Com Tampa 1100ml 5 Unidades PLASTILÂNIA", 5),
        ("Forma Redonda 500ml 20un Plastilania", 20),
        ("Pack 12 Formas de Pudim", 12),
        ("Kit c/ 6 Formas Aluminio", 6),
        ("Caixa com 100 potes 220ml", 100),
        ("Pacote com 25 forminhas", 25),
    ]
    for titulo, expected in cases:
        got = extract_qtde_unidades(titulo)
        _check(f"qtde({titulo[:40]!r}) == {expected}", got == expected, f"got {got}")


def test_qtde_defaults_to_1():
    for titulo in ["Leite Condensado Nestlé 395g", "Leite Integral 1L", "", None, "Doçúcar União 1kg"]:
        got = extract_qtde_unidades(titulo)
        _check(f"qtde({titulo!r}) == 1", got == 1, f"got {got}")


def test_qtde_no_bogus_matches():
    _check("no match no pudim 220ml", extract_qtde_unidades("Pudim 220ml Plastilania") == 1)
    _check("no match sku", extract_qtde_unidades("Produto SKU 12345") == 1)


def test_brand():
    _check("plastilania no titulo", brand_confirmed_in("PLASTILANIA", "Pote 220ml 10un PLASTILÂNIA"))
    _check("plastilania ausente", not brand_confirmed_in("PLASTILANIA", "Pote generico 220ml"))
    _check("plastilania via api field", brand_confirmed_in("PLASTILANIA", "Pote 220ml", marca_detectada="PLASTILÂNIA"))
    _check("marca vazia sempre true", brand_confirmed_in("", "Qualquer coisa"))
    _check("normaliza acentos", brand_confirmed_in("plastilânia", "10un PLASTILANIA"))
    _check("porto alegre", brand_confirmed_in("PORTO ALEGRE", "Leite Longa Vida Porto Alegre 1L"))


def _close(a, b, eps=1e-3):
    return abs(a - b) < eps


def test_preco_unidade():
    _check("caixa 200", _close(preco_por_unidade(269.99, 200), 1.3499))
    _check("pacote 10", _close(preco_por_unidade(14.49, 10), 1.449))
    _check("unitário", _close(preco_por_unidade(6.49, 1), 6.49))
    _check("zero guard", _close(preco_por_unidade(10.0, 0), 10.0))


if __name__ == "__main__":
    print("test_qtde_variants")
    test_qtde_variants()
    print("test_qtde_defaults_to_1")
    test_qtde_defaults_to_1()
    print("test_qtde_no_bogus_matches")
    test_qtde_no_bogus_matches()
    print("test_brand")
    test_brand()
    print("test_preco_unidade")
    test_preco_unidade()
    print("\nAll tests passed.")
