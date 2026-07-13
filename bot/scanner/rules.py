"""Severity classification for observed prices.

Given a product result plus the historical prices we have for that scanner,
decide whether the current price warrants a notification, and at what severity.

Rules (all evaluated; the strongest wins):

    🔥 forte  preco_unid ≤ baseline × 0.90  AND  preco_unid < último  (>10% off)
    ⚠️ alvo   preco_unid ≤ preco_alvo (user-configured target)

Per Fila's request (2026-07-13): only imperdíveis. The prior "✨ boa" 5%
tier was removed — it created too much noise around routine price
fluctuation. Only ≥10% discounts fire the wire now.

`preco_unid` here is the *delivered* price (product + frete rateado per
unit). Runner.py substitutes preco_unidade with preco_unidade_com_frete
before calling classify() so all comparisons are apples-to-apples.

`baseline` is the median of the last 30 days of observations. This adapts to
long-term price inflation — a "great" price now is different from a great
price two years ago. Requiring `preco < último` blocks the "stable price at
baseline triggers alert" bug.

Fallback: with fewer than 10 observations, uses the old min/último logic so
we alert something before enough history exists to compute a stable median.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from statistics import median
from typing import Optional

from scanner.config import AlertaConfig
from scanner.scrapers.base import ProductResult


BASELINE_WINDOW_DAYS = 30
MIN_OBS_FOR_MEDIAN = 10
FORTE_RATIO = 0.90   # ≤ baseline × 0.90 (>10% off) — only tier that fires now

# Fallback constants (used before we have MIN_OBS_FOR_MEDIAN observations)
FALLBACK_FORTE_RATIO = 0.90


@dataclass
class Verdict:
    severity: Optional[str]     # 'forte' | 'alvo' | None
    reason: str
    baseline: Optional[float]   # median-30d (or min if fallback)
    ultimo_preco: Optional[float]
    preco_alvo: Optional[float]
    savings: Optional[float]    # baseline - preco_unid, when severity fired

    @property
    def notifica(self) -> bool:
        return self.severity is not None


def compute_baseline(historico: list[dict], now: Optional[datetime] = None) -> Optional[float]:
    """Median of preco_unidade observations within the last 30 days.

    `historico` items have keys `preco_unidade` and `timestamp` (ISO string).
    Returns None if fewer than MIN_OBS_FOR_MEDIAN qualifying observations.
    """
    if not historico:
        return None
    now = now or datetime.now()
    cutoff = now - timedelta(days=BASELINE_WINDOW_DAYS)
    recent_prices: list[float] = []
    for h in historico:
        pu = h.get("preco_unidade") or 0
        if pu <= 0:
            continue
        ts_raw = h.get("timestamp") or ""
        try:
            ts = datetime.fromisoformat(ts_raw)
        except ValueError:
            continue
        if ts >= cutoff:
            recent_prices.append(float(pu))
    if len(recent_prices) < MIN_OBS_FOR_MEDIAN:
        return None
    return float(median(recent_prices))


def classify(
    produto: ProductResult,
    historico: list[dict],
    alerta: AlertaConfig,
    now: Optional[datetime] = None,
) -> Verdict:
    """Return the severity of this observation, considering snooze."""
    if not produto.disponivel:
        return Verdict(None, "produto indisponível", None, None, alerta.preco_alvo, None)

    if alerta.marca_obrigatoria and not alerta.fallback_livre and not produto.marca_confirmada:
        return Verdict(None, "marca obrigatória não confirmada", None, None, alerta.preco_alvo, None)

    preco_unid = produto.preco_unidade
    ultimo = None
    if historico:
        last = historico[-1]
        pu = last.get("preco_unidade") or 0
        if pu > 0:
            ultimo = float(pu)

    now = now or datetime.now()

    # ⚠️ alvo — user-defined, always priority. Compare against preco_unid.
    if alerta.preco_alvo is not None and preco_unid <= alerta.preco_alvo:
        return Verdict(
            "alvo",
            f"preço/un R$ {preco_unid:.3f} ≤ alvo R$ {alerta.preco_alvo:.3f}",
            baseline=None,
            ultimo_preco=ultimo,
            preco_alvo=alerta.preco_alvo,
            savings=(alerta.preco_alvo - preco_unid),
        )

    baseline = compute_baseline(historico, now=now)

    # Fallback path (<10 obs): use min-histórico as reference.
    if baseline is None:
        prices = [float(h.get("preco_unidade") or 0) for h in historico if (h.get("preco_unidade") or 0) > 0]
        min_hist = min(prices) if prices else None

        if min_hist is None:
            return Verdict(None, "primeira observação — sem histórico",
                           None, ultimo, alerta.preco_alvo, None)
        if ultimo is None or preco_unid >= ultimo:
            return Verdict(None, "preço não caiu vs. último (fallback)",
                           min_hist, ultimo, alerta.preco_alvo, None)

        if preco_unid <= min_hist * FALLBACK_FORTE_RATIO:
            return Verdict("forte",
                f"preço/un R$ {preco_unid:.3f} ≤ mín histórico R$ {min_hist:.3f} × {FALLBACK_FORTE_RATIO} (fallback)",
                min_hist, ultimo, alerta.preco_alvo, min_hist - preco_unid)
        return Verdict(None, "sem oferta relevante (fallback)",
                       min_hist, ultimo, alerta.preco_alvo, None)

    # Median-30d path: require price drop vs. last observation to fire.
    if ultimo is None or preco_unid >= ultimo:
        return Verdict(None, "preço não caiu vs. último",
                       baseline, ultimo, alerta.preco_alvo, None)

    if preco_unid <= baseline * FORTE_RATIO:
        return Verdict("forte",
            f"preço/un R$ {preco_unid:.3f} ≤ habitual R$ {baseline:.3f} × {FORTE_RATIO}",
            baseline, ultimo, alerta.preco_alvo, baseline - preco_unid)

    return Verdict(None, "sem oferta relevante", baseline, ultimo, alerta.preco_alvo, None)


def best_of(results: list[ProductResult]) -> Optional[ProductResult]:
    """Return the product with the lowest preco_unidade among available ones."""
    disponiveis = [r for r in results if r.disponivel and r.preco > 0]
    if not disponiveis:
        return None
    return min(disponiveis, key=lambda r: (r.preco_unidade, r.preco))
