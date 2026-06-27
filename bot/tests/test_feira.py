"""
Testes para a lógica pura do Modo Feira (`feira.compute_balanco` e `_to_float`).

Mesma convenção dos outros tests do bot/: script standalone, sem pytest.
Roda como:

    bot/.venv/bin/python bot/tests/test_feira.py

Cobre balanço: faturado, split dinheiro/pix, fiado, reconciliação de estoque
(levou − vendeu − voltou) e divergência de caixa (informado vs registrado).
Nenhuma chamada de rede — compute_balanco e _to_float são puros.
"""

import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.feira import compute_balanco, _to_float


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


def _venda(qtde, preco_unit, forma="", pago="pago", nome="", status="ativa"):
    return {
        "id": "VEN-x", "feira_id": "FEIRA-1", "data": "2026-06-27",
        "cliente_nome": nome, "qtde": qtde, "preco_unit": preco_unit,
        "preco_total": round(qtde * preco_unit, 2),
        "forma_pagamento": forma, "status_pagamento": pago,
        "status": status, "notas": "",
    }


def test_balanco_basico():
    feira = {"id": "FEIRA-1", "qtd_levada": 30, "preco_unit": 18.0,
             "qtd_voltou": None, "dinheiro": None, "pix": None}
    vendas = [
        _venda(2, 18, forma="dinheiro", nome="Fulano"),
        _venda(2, 18, forma="pix"),
        _venda(2, 18, pago="fiado", nome="Beltrano"),
    ]
    b = compute_balanco(feira, vendas)
    check(b["qtde_vendida"] == 6, "qtde vendida soma 6")
    check(b["faturado_total"] == 108.0, "faturado 6×18 = 108")
    check(b["dinheiro"] == 36.0, "dinheiro = 36")
    check(b["pix"] == 36.0, "pix = 36")
    check(b["fiado_total"] == 36.0, "fiado = 36")
    check(b["pago_total"] == 72.0, "pago total = 72 (fiado fora)")
    check(len(b["fiados"]) == 1 and b["fiados"][0]["nome"] == "Beltrano", "1 fiado: Beltrano")
    # estoque ainda sem fechamento
    check(b["qtd_voltou"] is None, "qtd_voltou None sem fechamento")
    check(b["qtd_nao_contabilizada"] is None, "sem reconciliação sem voltou")


def test_reconciliacao_estoque():
    # levou 30, vendeu 6, disse que voltaram 22 → 2 não batem (brinde/perda)
    feira = {"id": "FEIRA-1", "qtd_levada": 30, "preco_unit": 18.0,
             "qtd_voltou": 22, "dinheiro": None, "pix": None}
    vendas = [_venda(6, 18, forma="dinheiro")]
    b = compute_balanco(feira, vendas)
    check(b["qtd_nao_contabilizada"] == 2.0, "30 - 6 - 22 = 2 não contabilizados")


def test_estoque_bate():
    feira = {"id": "FEIRA-1", "qtd_levada": 30, "preco_unit": 18.0,
             "qtd_voltou": 24, "dinheiro": None, "pix": None}
    vendas = [_venda(6, 18, forma="pix")]
    b = compute_balanco(feira, vendas)
    check(b["qtd_nao_contabilizada"] == 0.0, "30 - 6 - 24 = 0 bate certinho")


def test_divergencia_caixa():
    # registrado pago: 36 din + 36 pix = 72. Informado: 40 + 36 = 76 → +4
    feira = {"id": "FEIRA-1", "qtd_levada": 30, "preco_unit": 18.0,
             "qtd_voltou": None, "dinheiro": 40, "pix": 36}
    vendas = [
        _venda(2, 18, forma="dinheiro"),
        _venda(2, 18, forma="pix"),
    ]
    b = compute_balanco(feira, vendas)
    check(b["recebido_informado"] == 76.0, "informado = 76")
    check(b["divergencia_caixa"] == 4.0, "divergência +4 (informado a mais)")


def test_pago_sem_forma():
    # venda paga mas sem forma anotada entra em pago_total, não em din/pix
    feira = {"id": "FEIRA-1", "qtd_levada": 10, "preco_unit": 18.0,
             "qtd_voltou": None, "dinheiro": None, "pix": None}
    vendas = [_venda(1, 18, forma="", pago="pago")]
    b = compute_balanco(feira, vendas)
    check(b["pago_sem_forma"] == 18.0, "pago sem forma = 18")
    check(b["dinheiro"] == 0.0 and b["pix"] == 0.0, "din/pix zerados")
    check(b["pago_total"] == 18.0, "pago_total inclui sem-forma")


def test_to_float():
    check(_to_float("36,00") == 36.0, "pt-BR vírgula '36,00' -> 36.0")
    check(_to_float("1.234,56") == 1234.56, "pt-BR milhar '1.234,56' -> 1234.56")
    check(_to_float("R$ 18") == 18.0, "'R$ 18' -> 18.0")
    check(_to_float("18.50") == 18.5, "ponto decimal '18.50' -> 18.5")
    check(_to_float("") == 0.0, "vazio -> 0.0")
    check(_to_float(None) == 0.0, "None -> 0.0")
    check(_to_float("abc") == 0.0, "lixo -> 0.0")


def main():
    print("=== test_feira ===")
    for fn in [
        test_balanco_basico,
        test_reconciliacao_estoque,
        test_estoque_bate,
        test_divergencia_caixa,
        test_pago_sem_forma,
        test_to_float,
    ]:
        print(f"\n{fn.__name__}:")
        try:
            fn()
        except Exception:
            global _failed
            _failed += 1
            print(f"  FAIL  {fn.__name__} raised:")
            traceback.print_exc()
    print(f"\n{_passed} passed, {_failed} failed")
    sys.exit(1 if _failed else 0)


if __name__ == "__main__":
    main()
