"""
Testes para `sheets.distribute_frete_desconto`.

Mesma convenção dos outros tests do bot/: script standalone, sem pytest.
Roda como:

    bot/.venv/bin/python bot/tests/test_frete_desconto.py

Cobre:
- Sem frete/desconto (retorna preco_total raw).
- 1 item + frete (paga frete inteiro).
- 2 itens com preços diferentes (rateio proporcional).
- 2 itens iguais (rateio 50/50).
- desconto > subtotal+frete (ValueError).
- subtotal=0 (brindes) com frete (split igualitário entre N).
- Lista vazia (retorna []).
- Rateio com sobra de centavo (snap a cents + última linha absorve).
"""

import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.sheets import distribute_frete_desconto


_passed = 0
_failed = 0


def check(condition: bool, label: str):
    global _passed, _failed
    if condition:
        _passed += 1
        print(f"  PASS  {label}")
    else:
        _failed += 1
        print(f"  FAIL  {label}")


def approx(a: float, b: float, tol: float = 0.005) -> bool:
    """Compara floats com tolerância de meio centavo."""
    return abs(a - b) < tol


def test_no_frete_no_desconto():
    print("\n[test_no_frete_no_desconto] sem ajustes → preco_total raw")
    items = [{"preco_total": 30.00}, {"preco_total": 70.00}]
    out = distribute_frete_desconto(items, frete=0, desconto=0)
    check(out == [30.00, 70.00], f"out == [30.00, 70.00] (got {out})")


def test_single_item_with_frete():
    print("\n[test_single_item_with_frete] 1 item paga frete inteiro")
    items = [{"preco_total": 50.00}]
    out = distribute_frete_desconto(items, frete=10, desconto=0)
    check(out == [60.00], f"out == [60.00] (got {out})")


def test_two_items_proportional():
    print("\n[test_two_items_proportional] 30/70 + frete 10 → 33 e 77")
    items = [{"preco_total": 30.00}, {"preco_total": 70.00}]
    out = distribute_frete_desconto(items, frete=10, desconto=0)
    # 30 + 3 = 33; 70 + 7 = 77
    check(approx(out[0], 33.00), f"out[0] ≈ 33.00 (got {out[0]})")
    check(approx(out[1], 77.00), f"out[1] ≈ 77.00 (got {out[1]})")
    check(approx(sum(out), 110.00), f"sum == 110.00 (got {sum(out)})")


def test_two_equal_items_split_50_50():
    print("\n[test_two_equal_items_split_50_50] 50/50 + frete 10 → 55 cada")
    items = [{"preco_total": 50.00}, {"preco_total": 50.00}]
    out = distribute_frete_desconto(items, frete=10, desconto=0)
    check(approx(out[0], 55.00), f"out[0] ≈ 55.00 (got {out[0]})")
    check(approx(out[1], 55.00), f"out[1] ≈ 55.00 (got {out[1]})")


def test_desconto_too_big_raises():
    print("\n[test_desconto_too_big_raises] desconto > subtotal+frete → ValueError")
    items = [{"preco_total": 10.00}, {"preco_total": 10.00}]
    try:
        distribute_frete_desconto(items, frete=0, desconto=100)
    except ValueError as e:
        check(True, f"ValueError levantado: {e}")
        msg = str(e).lower()
        check("desconto" in msg, "mensagem menciona 'desconto'")
        return
    check(False, "deveria ter levantado ValueError")


def test_zero_subtotal_with_frete():
    print("\n[test_zero_subtotal_with_frete] brindes (subtotal=0) + frete=10 / N")
    items = [{"preco_total": 0}, {"preco_total": 0}, {"preco_total": 0}, {"preco_total": 0}]
    out = distribute_frete_desconto(items, frete=10, desconto=0)
    # 10/4 = 2.50 cada
    for i, v in enumerate(out):
        check(approx(v, 2.50), f"out[{i}] ≈ 2.50 (got {v})")
    check(approx(sum(out), 10.00), f"sum == 10.00 (got {sum(out)})")


def test_empty_list():
    print("\n[test_empty_list] lista vazia → []")
    out = distribute_frete_desconto([], frete=10, desconto=5)
    check(out == [], f"out == [] (got {out})")


def test_cents_snap_with_remainder():
    print("\n[test_cents_snap_with_remainder] 3 itens iguais + frete 10 → snap a cents")
    # 10 / 3 = 3.3333... cada → snap a 3.33, sobra 1 centavo absorvido pela última
    items = [{"preco_total": 10.00}, {"preco_total": 10.00}, {"preco_total": 10.00}]
    out = distribute_frete_desconto(items, frete=10, desconto=0)
    # Cada valor é float com 2 casas
    for i, v in enumerate(out):
        # nenhum valor deve ter mais que 2 casas decimais reais
        check(round(v, 2) == v, f"out[{i}] = {v} arredondado a 2 casas")
    # Soma EXATA: 30 + 10 = 40.00 (centavos batem)
    check(round(sum(out), 2) == 40.00, f"sum == 40.00 exato (got {sum(out)})")
    # As duas primeiras linhas devem ser 13.33; a última absorve a sobra → 13.34
    check(out[0] == 13.33, f"out[0] == 13.33 (got {out[0]})")
    check(out[1] == 13.33, f"out[1] == 13.33 (got {out[1]})")
    check(out[2] == 13.34, f"out[2] == 13.34 (last absorbs cent) (got {out[2]})")


def test_only_desconto():
    print("\n[test_only_desconto] desconto sem frete → rateio negativo proporcional")
    items = [{"preco_total": 30.00}, {"preco_total": 70.00}]
    out = distribute_frete_desconto(items, frete=0, desconto=10)
    # 30 - 3 = 27; 70 - 7 = 63
    check(approx(out[0], 27.00), f"out[0] ≈ 27.00 (got {out[0]})")
    check(approx(out[1], 63.00), f"out[1] ≈ 63.00 (got {out[1]})")
    check(round(sum(out), 2) == 90.00, f"sum == 90.00 (got {sum(out)})")


def main():
    tests = [
        test_no_frete_no_desconto,
        test_single_item_with_frete,
        test_two_items_proportional,
        test_two_equal_items_split_50_50,
        test_desconto_too_big_raises,
        test_zero_subtotal_with_frete,
        test_empty_list,
        test_cents_snap_with_remainder,
        test_only_desconto,
    ]
    for t in tests:
        try:
            t()
        except Exception:
            global _failed
            _failed += 1
            print(f"  CRASH  {t.__name__}")
            traceback.print_exc()

    print("\n" + "=" * 50)
    print(f"Resultado: {_passed} passed, {_failed} failed")
    print("=" * 50)
    sys.exit(0 if _failed == 0 else 1)


if __name__ == "__main__":
    main()
