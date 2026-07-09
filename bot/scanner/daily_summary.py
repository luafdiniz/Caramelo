"""End-of-day summary: consolidate all offers detected today into one email.

Reads Precos_Observados for today, cross-references against Scanner_Alertas,
runs classify() on each obs to decide which counted as an offer, and emails
a single digest. If no offer fired today, skips the send entirely.

Runs 1x/day at 21h BRT (00 UTC) via .github/workflows/scanner-summary.yml.
"""

from __future__ import annotations

import os
import sys
from datetime import date, datetime

from lib import sheets
from scanner import config, email_notifier, history as history_mod, rules
from scanner.scrapers.base import ProductResult


def _spreadsheet_id() -> str:
    sid = os.environ.get("SPREADSHEET_ID")
    if not sid:
        raise RuntimeError("SPREADSHEET_ID env var not set")
    return sid


def _obs_to_product(obs: dict) -> ProductResult:
    return ProductResult(
        site=obs.get("site", ""),
        url=obs.get("url", ""),
        titulo=obs.get("titulo", ""),
        preco=float(obs.get("preco") or 0),
        preco_lista=float(obs.get("preco") or 0),
        marca_detectada=obs.get("marca_detectada", ""),
        qtde_unidades=int(obs.get("qtde_unidades") or 1),
        preco_unidade=float(obs.get("preco_unidade") or 0),
        disponivel=obs.get("disponivel", True),
        tem_oferta_clube=False,
        marca_confirmada=True,  # snooze/marca gate already applied at scan time
    )


def build_today_batch(now: datetime) -> list[email_notifier.OfferEntry]:
    sid = _spreadsheet_id()
    service = sheets.get_service()

    alertas = {a.scanner_id: a for a in config.get_alertas(sid, service=service)}
    produtos = {p["id"]: p["nome"] for p in sheets.get_produtos(sid, service=service)}

    today_iso = now.date().isoformat()
    entries: list[email_notifier.OfferEntry] = []

    for scanner_id, alerta in alertas.items():
        if not alerta.ativo:
            continue
        obs_list = sheets.get_precos_observados_by_scanner(sid, scanner_id, service=service)
        # Filter to today's obs
        today_obs = [o for o in obs_list if str(o.get("timestamp", ""))[:10] == today_iso]
        if not today_obs:
            continue

        # Build merged history WITHOUT today's obs for each classification
        full_hist = history_mod.get_full_history(sid, scanner_id, alerta.insumo_id, service=service)
        prev_hist = [h for h in full_hist if str(h.get("timestamp", ""))[:10] < today_iso]

        # Take the lowest preco_unidade from today (best of day)
        best_today = min(today_obs, key=lambda o: o.get("preco_unidade") or 999999)
        prod = _obs_to_product(best_today)
        verdict = rules.classify(prod, prev_hist, alerta, now=now)
        if verdict.notifica:
            entries.append(email_notifier.OfferEntry(
                alerta=alerta,
                produto=prod,
                verdict=verdict,
                insumo_nome=produtos.get(alerta.insumo_id, alerta.insumo_id),
            ))

    return entries


def run(dry_run: bool = False) -> int:
    now = datetime.now()
    entries = build_today_batch(now)
    print(f"daily_summary: {len(entries)} offer(s) today")
    for e in entries:
        print(f"  - {e.alerta.scanner_id} ({e.insumo_nome}): {e.verdict.severity}")
    email_notifier.send_daily_summary(entries, dry_run=dry_run)
    return len(entries)


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    run(dry_run=dry)
