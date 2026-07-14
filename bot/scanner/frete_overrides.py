"""Per-store freight overrides — where the site's real checkout differs
from what the VTEX API returns.

Supernosso confirmed 2026-07-14 (Luiza's screenshots): the API returns SLA
"Agendada Del Rey R$ 10,08" but the actual cart at CEP 31.140-500 charges
R$ 19,90 fixed, free above R$ 500 subtotal (banner). Reality wins.
"""

from __future__ import annotations

from scanner.frete import SimulationResult


SUPERNOSSO_FIXED_FRETE = 19.90
SUPERNOSSO_FREE_THRESHOLD = 500.00

APOIO_FIXED_FRETE = 19.90
APOIO_FREE_THRESHOLD = 600.00  # Banner: "grátis em compras acima de R$ 600 para BH e região"


def apply(site_key: str, sim: SimulationResult) -> SimulationResult:
    """Return a possibly-adjusted SimulationResult that reflects the real
    checkout price for this store.
    """
    if sim is None:
        return sim
    if site_key == "supernosso":
        if sim.total_bruto >= SUPERNOSSO_FREE_THRESHOLD:
            sim.frete = 0.0
            sim.prazo = sim.prazo or "entrega grátis"
        else:
            sim.frete = SUPERNOSSO_FIXED_FRETE
            sim.prazo = sim.prazo or "entrega agendada"
        sim.total_final = round(sim.total_produto + sim.frete, 2)
    elif site_key == "apoio":
        # Confirmed via Luiza's cart (CEP 31.140-500 = Cachoeirinha/BH):
        # R$ 19,90 fixed, free above R$ 600 subtotal.
        if sim.total_bruto >= APOIO_FREE_THRESHOLD:
            sim.frete = 0.0
            sim.prazo = sim.prazo or "entrega grátis"
        else:
            sim.frete = APOIO_FIXED_FRETE
            sim.prazo = sim.prazo or "entrega agendada"
        sim.total_final = round(sim.total_produto + sim.frete, 2)
    # santoantonio: freight depends on weight/dimensions; API result is
    #               closer to real. Leave as-is.
    return sim
