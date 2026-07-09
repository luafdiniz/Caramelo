"""Unit tests for scanner.rules — pure functions, no I/O."""

import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scanner.rules import classify, best_of, Verdict
from scanner.config import AlertaConfig
from scanner.scrapers.base import ProductResult


def _pr(preco=10.0, preco_unid=1.0, qtde=10, disp=True, marca_ok=True, clube=False):
    return ProductResult(
        site="supernosso", url="https://x", titulo="teste",
        preco=preco, preco_lista=preco, marca_detectada="X",
        qtde_unidades=qtde, preco_unidade=preco_unid,
        disponivel=disp, tem_oferta_clube=clube, marca_confirmada=marca_ok,
    )


def _alerta(marca="X", fallback=False, preco_alvo=None, snooze_ate=None):
    return AlertaConfig(
        scanner_id="SCA-TEST", insumo_id="INS-1", ativo=True,
        termo_busca="x", sites=["supernosso"],
        marca_obrigatoria=marca, fallback_livre=fallback,
        duracao_snooze_dias=30,
        preco_alvo=preco_alvo, ultimo_preco=None, ultima_verif=None,
        status="", snooze_ate=snooze_ate,
    )


def _check(name, cond, detail=""):
    if cond:
        print(f"  PASS  {name}")
    else:
        print(f"  FAIL  {name}  {detail}")
        raise AssertionError(f"{name}: {detail}")


def test_indisponivel_nao_notifica():
    v = classify(_pr(disp=False), [1.0], _alerta())
    _check("indisponivel", v.severity is None)


def test_marca_nao_confirmada_sem_fallback():
    v = classify(_pr(marca_ok=False), [1.0], _alerta(fallback=False))
    _check("marca_obrig_no_fallback", v.severity is None)


def test_marca_nao_confirmada_com_fallback_passa_pela_marca():
    # Preço/un igual ao mínimo → 'forte' mesmo com marca não confirmada
    v = classify(_pr(preco_unid=1.0, marca_ok=False), [1.0], _alerta(fallback=True))
    _check("fallback deixa marca passar", v.severity == "forte")


def test_primeira_observacao_sem_alvo_nao_notifica():
    v = classify(_pr(), [], _alerta())
    _check("primeira sem alvo", v.severity is None)


def test_primeira_observacao_com_alvo_pode_notificar():
    v = classify(_pr(preco=8.0), [], _alerta(preco_alvo=10.0))
    _check("primeira com alvo hit", v.severity == "alvo")


def test_forte_bate_com_5pct_do_min():
    hist = [1.00, 1.10, 1.20]
    v = classify(_pr(preco_unid=1.05), hist, _alerta())
    _check("forte dentro de 5% do min", v.severity == "forte")


def test_boa_10pct_abaixo_do_ultimo():
    # min=5, último=10. 8.5 ≤ 10×0.9=9.0 (boa) mas 8.5 > 5×1.05=5.25 (não forte)
    hist = [5.00, 5.00, 10.00]
    v = classify(_pr(preco_unid=8.5), hist, _alerta())
    _check("boa: 10% abaixo do último", v.severity == "boa")


def test_alvo_supera_boa():
    hist = [1.00]
    # preço 0.5 é ≤ alvo 1.0 → 'alvo' — mesmo se seria 'boa' também
    v = classify(_pr(preco=0.5, preco_unid=0.05, qtde=10), hist, _alerta(preco_alvo=1.0))
    _check("alvo tem prioridade sobre boa", v.severity in ("alvo","forte"))


def test_snooze_silencia_boa_mas_deixa_forte():
    # min=5, último=10. 8.0 → boa (não forte). 5.2 → forte (dentro 5% do min).
    hist = [5.00, 5.00, 10.00]
    future = datetime.now() + timedelta(days=10)
    v = classify(_pr(preco_unid=8.0), hist, _alerta(snooze_ate=future))
    _check("boa silenciada por snooze", v.severity is None)

    v = classify(_pr(preco_unid=5.2), hist, _alerta(snooze_ate=future))
    _check("forte passa apesar do snooze", v.severity == "forte")


def test_snooze_expirado_libera_boa():
    hist = [5.00, 5.00, 10.00]  # min=5, último=10 — 8.0 é boa mas não forte
    past = datetime.now() - timedelta(days=1)
    v = classify(_pr(preco_unid=8.0), hist, _alerta(snooze_ate=past))
    _check("snooze expirado libera boa", v.severity == "boa")


def test_best_of_escolhe_menor_preco_unid():
    r1 = _pr(preco=100, preco_unid=1.00)
    r2 = _pr(preco=50, preco_unid=0.50)
    r3 = _pr(preco=200, preco_unid=0.40)
    _check("best_of menor preco_unid", best_of([r1, r2, r3]) is r3)


def test_best_of_ignora_indisponivel():
    r1 = _pr(preco_unid=0.10, disp=False)
    r2 = _pr(preco_unid=0.50, disp=True)
    _check("best_of ignora indisponivel", best_of([r1, r2]) is r2)


def test_best_of_vazio_retorna_None():
    _check("best_of vazio", best_of([]) is None)


if __name__ == "__main__":
    print("test_indisponivel_nao_notifica"); test_indisponivel_nao_notifica()
    print("test_marca_nao_confirmada_sem_fallback"); test_marca_nao_confirmada_sem_fallback()
    print("test_marca_nao_confirmada_com_fallback_passa_pela_marca"); test_marca_nao_confirmada_com_fallback_passa_pela_marca()
    print("test_primeira_observacao_sem_alvo_nao_notifica"); test_primeira_observacao_sem_alvo_nao_notifica()
    print("test_primeira_observacao_com_alvo_pode_notificar"); test_primeira_observacao_com_alvo_pode_notificar()
    print("test_forte_bate_com_5pct_do_min"); test_forte_bate_com_5pct_do_min()
    print("test_boa_10pct_abaixo_do_ultimo"); test_boa_10pct_abaixo_do_ultimo()
    print("test_alvo_supera_boa"); test_alvo_supera_boa()
    print("test_snooze_silencia_boa_mas_deixa_forte"); test_snooze_silencia_boa_mas_deixa_forte()
    print("test_snooze_expirado_libera_boa"); test_snooze_expirado_libera_boa()
    print("test_best_of_escolhe_menor_preco_unid"); test_best_of_escolhe_menor_preco_unid()
    print("test_best_of_ignora_indisponivel"); test_best_of_ignora_indisponivel()
    print("test_best_of_vazio_retorna_None"); test_best_of_vazio_retorna_None()
    print("\nAll rules tests passed.")
