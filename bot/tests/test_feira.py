"""
Testes para a lógica pura do Modo Feira (multi-produto).

Mesma convenção dos outros tests do bot/: script standalone, sem pytest.
Roda como:

    bot/.venv/bin/python bot/tests/test_feira.py

Cobre: balanço por tamanho (vendido/voltou/não-contabilizado), split
dinheiro/pix/fiado, divergência de caixa, normalização de tamanho, match de
produto, completude e merge de produtos. Nenhuma chamada de rede.
"""

import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.feira import (
    compute_balanco, _to_float, norm_tamanho, find_produto,
    produtos_completos, produtos_missing_preco, produto_principal,
)
from lib.feira_flow import _merge_produtos, _clean_produtos


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


def _venda(qtde, preco_unit, tamanho="200g", forma="", pago="pago", nome="", status="ativa"):
    return {
        "id": "VEN-x", "feira_id": "FEIRA-1", "data": "2026-06-27",
        "cliente_nome": nome, "tamanho": tamanho, "qtde": qtde,
        "preco_unit": preco_unit, "preco_total": round(qtde * preco_unit, 2),
        "forma_pagamento": forma, "status_pagamento": pago,
        "status": status, "notas": "",
    }


def _feira(produtos, voltou=None, dinheiro=None, pix=None):
    return {"id": "FEIRA-1", "produtos": produtos, "voltou": voltou or {},
            "dinheiro": dinheiro, "pix": pix}


def test_balanco_multiproduto():
    f = _feira([
        {"tamanho": "200g", "qtd_levada": 63, "preco": 18.0},
        {"tamanho": "500g", "qtd_levada": 4, "preco": 45.0},
    ])
    vendas = [
        _venda(2, 18, "200g", forma="dinheiro", nome="Fulano"),
        _venda(3, 18, "200g", forma="pix"),
        _venda(1, 45, "500g", pago="fiado", nome="Maria"),
    ]
    b = compute_balanco(f, vendas)
    check(b["faturado_total"] == 135.0, "faturado 2*18+3*18+1*45 = 135")
    check(b["dinheiro"] == 36.0, "dinheiro 36")
    check(b["pix"] == 54.0, "pix 3*18=54")
    check(b["fiado_total"] == 45.0, "fiado 45 (500g da Maria)")
    p200 = next(p for p in b["produtos"] if p["tamanho"] == "200g")
    p500 = next(p for p in b["produtos"] if p["tamanho"] == "500g")
    check(p200["vendido"] == 5, "200g vendeu 5")
    check(p500["vendido"] == 1, "500g vendeu 1")
    check(len(b["fiados"]) == 1 and b["fiados"][0]["tamanho"] == "500g", "fiado é da Maria, 500g")


def test_reconciliacao_por_tamanho():
    f = _feira(
        [{"tamanho": "200g", "qtd_levada": 63, "preco": 18.0},
         {"tamanho": "500g", "qtd_levada": 4, "preco": 45.0}],
        voltou={"200g": 58, "500g": 2},
    )
    # 200g: vendeu 5, voltou 58 -> 63-5-58=0. 500g: vendeu 1, voltou 2 -> 4-1-2=1 (cortesia/produção)
    vendas = [_venda(5, 18, "200g", forma="dinheiro"), _venda(1, 45, "500g", forma="pix")]
    b = compute_balanco(f, vendas)
    p200 = next(p for p in b["produtos"] if p["tamanho"] == "200g")
    p500 = next(p for p in b["produtos"] if p["tamanho"] == "500g")
    check(p200["nao_contabilizada"] == 0.0, "200g bate certinho")
    check(p500["nao_contabilizada"] == 1.0, "500g sobra 1 não contabilizado (deu pra produção)")


def test_divergencia_caixa():
    f = _feira([{"tamanho": "200g", "qtd_levada": 10, "preco": 18.0}],
               dinheiro=40, pix=18)
    vendas = [_venda(1, 18, "200g", forma="dinheiro"), _venda(1, 18, "200g", forma="pix")]
    b = compute_balanco(f, vendas)
    check(b["recebido_informado"] == 58.0, "informado 58")
    check(b["divergencia_caixa"] == 22.0, "divergência +22 (40 din informado vs 18 registrado)")


def test_pago_sem_forma():
    f = _feira([{"tamanho": "200g", "qtd_levada": 10, "preco": 18.0}])
    vendas = [_venda(1, 18, "200g", forma="", pago="pago")]
    b = compute_balanco(f, vendas)
    check(b["pago_sem_forma"] == 18.0, "pago sem forma 18")
    check(b["dinheiro"] == 0.0 and b["pix"] == 0.0, "din/pix zerados")
    check(b["pago_total"] == 18.0, "pago_total inclui sem-forma")


def test_norm_tamanho():
    check(norm_tamanho("200g") == "200g", "'200g' -> 200g")
    check(norm_tamanho("de 500") == "500g", "'de 500' -> 500g")
    check(norm_tamanho("1 kg") == "1kg", "'1 kg' -> 1kg")
    check(norm_tamanho("200 g") == "200g", "'200 g' -> 200g")
    check(norm_tamanho("") == "padrão", "vazio -> padrão")


def test_find_e_principal():
    prods = [{"tamanho": "200g", "qtd_levada": 63, "preco": 18.0},
             {"tamanho": "500g", "qtd_levada": 4, "preco": 45.0}]
    check(find_produto(prods, "500g")["preco"] == 45.0, "find 500g")
    check(find_produto(prods, "de 200")["preco"] == 18.0, "find por 'de 200'")
    check(find_produto(prods, "1kg") is None, "find inexistente -> None")
    check(produto_principal(prods)["tamanho"] == "200g", "principal = maior qtde (200g)")


def test_completude_e_merge():
    incompleto = [{"tamanho": "200g", "qtd_levada": 63, "preco": None},
                  {"tamanho": "500g", "qtd_levada": 4, "preco": None}]
    check(not produtos_completos(incompleto), "sem preço -> incompleto")
    check(len(produtos_missing_preco(incompleto)) == 2, "2 sem preço")
    novos = _clean_produtos([{"tamanho": "200g", "preco": 18}, {"tamanho": "500g", "preco": 45}])
    merged = _merge_produtos(incompleto, novos)
    check(produtos_completos(merged), "após merge dos preços -> completo")
    p200 = next(p for p in merged if p["tamanho"] == "200g")
    check(p200["qtd_levada"] == 63 and p200["preco"] == 18.0, "merge preserva qtd e preenche preço")


def test_to_float():
    check(_to_float("36,00") == 36.0, "'36,00' -> 36.0")
    check(_to_float("1.234,56") == 1234.56, "'1.234,56' -> 1234.56")
    check(_to_float("R$ 18") == 18.0, "'R$ 18' -> 18.0")
    check(_to_float("") == 0.0 and _to_float(None) == 0.0, "vazio/None -> 0.0")


def main():
    print("=== test_feira ===")
    for fn in [
        test_balanco_multiproduto, test_reconciliacao_por_tamanho,
        test_divergencia_caixa, test_pago_sem_forma, test_norm_tamanho,
        test_find_e_principal, test_completude_e_merge, test_to_float,
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
