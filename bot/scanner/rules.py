"""Severity classification for observed prices.

Given a product result plus the historical prices we have for that scanner,
decide whether the current price warrants a notification, and at what severity.

Rules (all evaluated; the strongest wins):

    🔥 forte   preco_unid ≤ mínimo histórico × 1.05  (near the best we've seen)
    ✨ boa     preco_unid ≤ último preço × 0.90       (10%+ off the last time we bought)
    ⚠️ alvo    preco ≤ preco_alvo                     (user-configured target hit)

Snooze filters only the intermediate '✨ boa' tier — 🔥 forte and ⚠️ alvo always
notify. Rationale: after a big purchase we don't want to be bugged with small
discounts, but a rare deep discount should still ring.

The caller passes the observed ProductResult plus a compact history
(list of past preco_unidade for this scanner). No I/O here — this module is
pure data → decision.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from scanner.config import AlertaConfig
from scanner.scrapers.base import ProductResult


FORTE_THRESHOLD_RATIO = 1.05   # ≤ min × 1.05
BOA_DESCONTO_RATIO = 0.90      # ≤ last × 0.90


@dataclass
class Verdict:
    severity: Optional[str]  # 'forte' | 'boa' | 'alvo' | None
    reason: str
    min_historico: Optional[float]
    ultimo_preco: Optional[float]
    preco_alvo: Optional[float]

    @property
    def notifica(self) -> bool:
        return self.severity is not None


def classify(
    produto: ProductResult,
    historico_precos_unid: list[float],
    alerta: AlertaConfig,
    now: Optional[datetime] = None,
) -> Verdict:
    """Return the severity of this observation, considering snooze.

    `historico_precos_unid` is the list of past preco_unidade values recorded
    for this scanner (from Precos_Observados). Empty on the first scan.
    """
    if not produto.disponivel:
        return Verdict(None, "produto indisponível", None, None, alerta.preco_alvo)

    # Brand gate: for a scanner without fallback, an unconfirmed brand match
    # never fires — irrelevant even at a great price.
    if alerta.marca_obrigatoria and not alerta.fallback_livre and not produto.marca_confirmada:
        return Verdict(None, "marca obrigatória não confirmada", None, None, alerta.preco_alvo)

    preco_unid = produto.preco_unidade
    min_hist = min(historico_precos_unid) if historico_precos_unid else None
    ultimo = historico_precos_unid[-1] if historico_precos_unid else None

    # 🔥 forte: near best we've seen.
    forte = min_hist is not None and preco_unid <= min_hist * FORTE_THRESHOLD_RATIO

    # ✨ boa: meaningful discount vs previous.
    boa = ultimo is not None and preco_unid <= ultimo * BOA_DESCONTO_RATIO

    # ⚠️ alvo: user-set target hit. Compared against preco_unidade so that
    # `preco_alvo` in Scanner_Alertas is always "target price per unit" —
    # same currency as forte/boa/history, works whether the listing is a
    # single item or a 200-pack.
    alvo = alerta.preco_alvo is not None and preco_unid <= alerta.preco_alvo

    # First observation ever: don't spam. Wait for context to build.
    if min_hist is None and not alvo:
        return Verdict(None, "primeira observação — sem histórico", None, None, alerta.preco_alvo)

    # Snooze filter: 'boa' silenced, others pass through.
    now = now or datetime.now()
    in_snooze = alerta.snooze_ate is not None and now < alerta.snooze_ate

    if forte:
        return Verdict("forte",
            f"preço/un R$ {preco_unid:.3f} ≤ mín histórico R$ {min_hist:.3f} × {FORTE_THRESHOLD_RATIO}",
            min_hist, ultimo, alerta.preco_alvo)
    if alvo:
        return Verdict("alvo",
            f"preço/un R$ {preco_unid:.3f} ≤ alvo R$ {alerta.preco_alvo:.3f}",
            min_hist, ultimo, alerta.preco_alvo)
    if boa and not in_snooze:
        return Verdict("boa",
            f"preço/un R$ {preco_unid:.3f} ≤ último R$ {ultimo:.3f} × {BOA_DESCONTO_RATIO}",
            min_hist, ultimo, alerta.preco_alvo)
    if boa and in_snooze:
        return Verdict(None,
            f"oferta boa silenciada por snooze até {alerta.snooze_ate}",
            min_hist, ultimo, alerta.preco_alvo)

    return Verdict(None, "sem oferta relevante", min_hist, ultimo, alerta.preco_alvo)


def best_of(results: list[ProductResult]) -> Optional[ProductResult]:
    """Given N results (multiple sizes/sellers), return the one with lowest
    preco_unidade among products that are available. Ties broken by preco."""
    disponiveis = [r for r in results if r.disponivel and r.preco > 0]
    if not disponiveis:
        return None
    return min(disponiveis, key=lambda r: (r.preco_unidade, r.preco))
