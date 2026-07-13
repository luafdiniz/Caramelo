"""Unit tests for scanner.rules — pure functions, no I/O."""

import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scanner.rules import classify, best_of, compute_baseline
from scanner.config import AlertaConfig
from scanner.scrapers.base import ProductResult


def _pr(preco=10.0, preco_unid=1.0, qtde=10, disp=True, marca_ok=True, clube=False):
    return ProductResult(
        site="supernosso", url="https://x", titulo="teste",
        preco=preco, preco_lista=preco, marca_detectada="X",
        qtde_unidades=qtde, preco_unidade=preco_unid,
        disponivel=disp, tem_oferta_clube=clube, marca_confirmada=marca_ok,
    )


def _alerta(marca="X", fallback=False, preco_alvo=None):
    return AlertaConfig(
        scanner_id="SCA-TEST", insumo_id="INS-1", ativo=True,
        termo_busca="x", sites=["supernosso"],
        marca_obrigatoria=marca, fallback_livre=fallback,
        duracao_snooze_dias=30,
        preco_alvo=preco_alvo, ultimo_preco=None, ultima_verif=None,
        status="", snooze_ate=None,
    )


def _hist(prices_and_days_ago, now):
    return [
        {"preco_unidade": p, "timestamp": (now - timedelta(days=d)).isoformat()}
        for p, d in prices_and_days_ago
    ]


def _check(name, cond, detail=""):
    if cond:
        print(f"  PASS  {name}")
    else:
        print(f"  FAIL  {name}  {detail}")
        raise AssertionError(f"{name}: {detail}")


NOW = datetime(2026, 8, 1, 12, 0, 0)


def test_baseline_none_with_few_obs():
    hist = _hist([(5.0, 1), (5.0, 2), (5.0, 3)], NOW)
    _check("baseline None <10 obs", compute_baseline(hist, now=NOW) is None)


def test_baseline_median_of_recent_30d():
    hist = _hist([(3.0, 45), (4.0, 44), (5.0, 43)] + [(6.0, d) for d in range(1, 15)], NOW)
    b = compute_baseline(hist, now=NOW)
    _check("baseline ignores old obs", b == 6.0, f"got {b}")


def test_indisponivel_nao_notifica():
    v = classify(_pr(disp=False), _hist([(6.0, d) for d in range(1, 15)], NOW),
                 _alerta(), now=NOW)
    _check("indisponivel", v.severity is None)


def test_marca_nao_confirmada_sem_fallback():
    v = classify(_pr(marca_ok=False), _hist([(6.0, d) for d in range(1, 15)], NOW),
                 _alerta(fallback=False), now=NOW)
    _check("marca_obrig_no_fallback", v.severity is None)


def test_alvo_com_baseline():
    hist = _hist([(6.0, d) for d in range(1, 15)], NOW)
    v = classify(_pr(preco=4.0, preco_unid=0.4, qtde=10),
                 hist, _alerta(preco_alvo=0.5), now=NOW)
    _check("alvo dispara", v.severity == "alvo")


def test_alvo_sem_historico():
    v = classify(_pr(preco=4.0, preco_unid=0.4), [], _alerta(preco_alvo=0.5), now=NOW)
    _check("alvo primeira obs", v.severity == "alvo")


def test_primeira_obs_sem_alvo_nao_notifica():
    v = classify(_pr(), [], _alerta(), now=NOW)
    _check("primeira sem alvo", v.severity is None)


def test_preco_estavel_nao_dispara():
    hist = _hist([(1.0, d) for d in range(1, 15)], NOW)
    v = classify(_pr(preco_unid=1.0), hist, _alerta(), now=NOW)
    _check("preço estável não dispara", v.severity is None)


def test_fallback_preco_igual_min_nao_dispara():
    hist = _hist([(1.0, 1), (1.0, 2), (1.0, 3)], NOW)
    v = classify(_pr(preco_unid=1.0), hist, _alerta(), now=NOW)
    _check("fallback preço = min não dispara", v.severity is None)


def test_fallback_forte_quando_10pct_off():
    hist = _hist([(1.0, 1), (1.0, 2), (1.0, 3)], NOW)
    v = classify(_pr(preco_unid=0.85), hist, _alerta(), now=NOW)
    _check("fallback forte 15% off", v.severity == "forte")


def test_fallback_5pct_off_nao_dispara():
    """5% off não dispara mais (Fila's request: só imperdíveis)."""
    hist = _hist([(1.0, 1), (1.0, 2), (1.0, 3)], NOW)
    v = classify(_pr(preco_unid=0.95), hist, _alerta(), now=NOW)
    _check("fallback 5% off não dispara", v.severity is None)


def test_forte_10pct_off_baseline():
    hist = _hist([(5.0, d) for d in range(1, 15)], NOW)
    v = classify(_pr(preco_unid=4.5), hist, _alerta(), now=NOW)
    _check("forte: 10% off baseline", v.severity == "forte")


def test_5pct_off_baseline_nao_dispara():
    hist = _hist([(5.0, d) for d in range(1, 15)], NOW)
    v = classify(_pr(preco_unid=4.75), hist, _alerta(), now=NOW)
    _check("5% off baseline não dispara", v.severity is None)


def test_no_drop_no_alert():
    hist = _hist([(5.0, d) for d in range(1, 14)] + [(4.5, 1)], NOW)
    v = classify(_pr(preco_unid=4.5), hist, _alerta(), now=NOW)
    _check("não dispara sem queda vs último", v.severity is None)


def test_baseline_adapts_to_inflation():
    hist = _hist([(4.99, d) for d in range(60, 40, -1)]
                 + [(5.30, d) for d in range(40, 20, -1)]
                 + [(5.50, d) for d in range(15, 1, -1)], NOW)
    v = classify(_pr(preco_unid=4.90), hist, _alerta(), now=NOW)
    _check("preço adapta a inflação (forte)", v.severity == "forte",
           f"got {v.severity}")


def test_best_of_escolhe_menor():
    r1 = _pr(preco=100, preco_unid=1.00)
    r2 = _pr(preco=50, preco_unid=0.50)
    _check("best_of menor", best_of([r1, r2]) is r2)


def test_best_of_ignora_indisponivel():
    r1 = _pr(preco_unid=0.10, disp=False)
    r2 = _pr(preco_unid=0.50, disp=True)
    _check("best_of ignora indisponivel", best_of([r1, r2]) is r2)


def test_best_of_vazio():
    _check("best_of vazio", best_of([]) is None)


if __name__ == "__main__":
    tests = [t for t in globals() if t.startswith("test_")]
    for t in tests:
        print(t); globals()[t]()
    print(f"\nAll {len(tests)} tests passed.")
