"""Scanner cron entrypoint.

Flow per active alert:
    1. For each configured site, call the right scraper.
    2. Filter results by marca_obrigatoria (unless fallback_livre).
    3. Pick the best (lowest preco_unidade) across all sites.
    4. Append the observation to Precos_Observados.
    5. Load history for this scanner, run rules.classify().
    6. If a notification is warranted, send via notifier.
    7. Update Scanner_Alertas row (ultimo_preco / ultima_verif / status).

Usage:
    SPREADSHEET_ID=... \\
    GOOGLE_SERVICE_ACCOUNT_JSON=... \\
    TELEGRAM_BOT_TOKEN=... \\
    python -m scanner.runner [--dry-run]
"""

from __future__ import annotations

import os
import sys
import time
from datetime import datetime
from typing import Optional

from lib import sheets
from scanner import config, extractor, notifier, rules
from scanner.scrapers import mercadolivre, vtex
from scanner.scrapers.base import ProductResult


def _spreadsheet_id() -> str:
    sid = os.environ.get("SPREADSHEET_ID")
    if not sid:
        raise RuntimeError("SPREADSHEET_ID env var not set")
    return sid


def _scrape_site(
    site_key: str, termo: str, marca_obrigatoria: str
) -> list[ProductResult]:
    if site_key == "ML":
        return mercadolivre.search(termo, marca_obrigatoria)
    if site_key in vtex.HOSTNAMES:
        return vtex.search(site_key, termo, marca_obrigatoria)
    print(f"runner: unknown site_key {site_key!r} — skipping")
    return []


def _filter_by_marca(
    results: list[ProductResult], alerta: config.AlertaConfig
) -> list[ProductResult]:
    """Marca filter: without fallback, only confirmed matches survive."""
    if not alerta.marca_obrigatoria or alerta.fallback_livre:
        return results
    return [r for r in results if r.marca_confirmada]


def _filter_by_intent(
    results: list[ProductResult], termo_busca: str
) -> list[ProductResult]:
    """Drop results whose title misses required specs (220ml, 5kg) or
    product-type keywords (condensado, integral). Keeps the size/variant
    the user actually searched for."""
    return [r for r in results if extractor.matches_search_intent(termo_busca, r.titulo)]


def _get_insumo_nome(spreadsheet_id: str, insumo_id: str, produtos_cache: dict) -> str:
    if produtos_cache and insumo_id in produtos_cache:
        return produtos_cache[insumo_id]
    return insumo_id


def run(dry_run: bool = False) -> dict:
    """Run one scan cycle. Returns a summary dict."""
    sid = _spreadsheet_id()
    service = sheets.get_service()

    alertas = config.get_active_alertas(sid, service=service)
    if not alertas:
        print("runner: no active alerts, nothing to do")
        return {"scanned": 0, "notified": 0, "errors": 0}

    # Prefetch produtos for nice insumo names in messages
    try:
        produtos = sheets.get_produtos(sid, service=service)
        prod_names = {p["id"]: p["nome"] for p in produtos}
    except Exception as e:
        print(f"runner: get_produtos failed: {e}")
        prod_names = {}

    summary = {"scanned": 0, "notified": 0, "errors": 0}
    now = datetime.now()

    for alerta in alertas:
        summary["scanned"] += 1
        print(f"\n=== {alerta.scanner_id} ({alerta.insumo_id}) — {alerta.termo_busca!r} ===")

        # 1-3. scrape + filter + pick best per site, then pick global best
        all_results: list[ProductResult] = []
        for i, site_key in enumerate(alerta.sites):
            if i > 0:
                time.sleep(0.5)  # be nice to APIs between sites
            results = _scrape_site(site_key, alerta.termo_busca, alerta.marca_obrigatoria)
            filtered = _filter_by_intent(_filter_by_marca(results, alerta), alerta.termo_busca)
            site_best = rules.best_of(filtered)
            if site_best:
                print(f"  {site_key}: R$ {site_best.preco:.2f} ({site_best.preco_unidade:.3f}/un) — {site_best.titulo[:50]}")
                all_results.append(site_best)
            else:
                print(f"  {site_key}: no valid result")

        global_best = rules.best_of(all_results)
        if not global_best:
            # Nothing to record; mark status but keep scanning tomorrow
            if not dry_run:
                sheets.update_scanner_row(
                    sid, alerta.scanner_id,
                    {"ultima_verif": now.isoformat(timespec="seconds"),
                     "status": "SEM_RESULTADO"},
                    service=service,
                )
            summary["errors"] += 1
            continue

        # 4. record observation
        if not dry_run:
            try:
                sheets.append_preco_observado(
                    sid,
                    timestamp=now.isoformat(timespec="seconds"),
                    scanner_id=alerta.scanner_id,
                    site=global_best.site,
                    url=global_best.url,
                    preco=global_best.preco,
                    preco_unidade=global_best.preco_unidade,
                    qtde_unidades=global_best.qtde_unidades,
                    disponivel=global_best.disponivel,
                    marca_detectada=global_best.marca_detectada,
                    titulo=global_best.titulo,
                    service=service,
                )
            except Exception as e:
                print(f"  ! append_preco_observado failed: {e}")
                summary["errors"] += 1
                continue

        # 5. classify against history
        historico = sheets.get_precos_observados_by_scanner(sid, alerta.scanner_id, service=service)
        # exclude the observation we just wrote (last one)
        historico_precos_unid = [
            h["preco_unidade"] for h in historico[:-1] if h["preco_unidade"] > 0
        ] if not dry_run else [h["preco_unidade"] for h in historico if h["preco_unidade"] > 0]

        verdict = rules.classify(global_best, historico_precos_unid, alerta, now=now)
        print(f"  → {verdict.severity or 'sem alerta'}: {verdict.reason}")

        # 6. notify if warranted
        if verdict.notifica:
            insumo_nome = _get_insumo_nome(sid, alerta.insumo_id, prod_names)
            notifier.send_offer(alerta, global_best, verdict, insumo_nome=insumo_nome, dry_run=dry_run)
            summary["notified"] += 1

        # 7. update Scanner_Alertas
        if not dry_run:
            sheets.update_scanner_row(
                sid, alerta.scanner_id,
                {
                    "ultimo_preco": global_best.preco,
                    "ultima_verif": now.isoformat(timespec="seconds"),
                    "status": "OK",
                },
                service=service,
            )

    print(f"\n=== Summary: scanned={summary['scanned']} notified={summary['notified']} errors={summary['errors']} ===")
    return summary


def snooze_by_insumo(spreadsheet_id: str, insumo_id: str, service=None) -> list[str]:
    """Called from bot compra hook. For every active scanner tied to this
    insumo, set snooze_ate = now + duracao_snooze_dias. Returns list of
    scanner_ids that got snoozed."""
    from datetime import timedelta

    service = service or sheets.get_service()
    alertas = config.get_alertas(spreadsheet_id, service=service)
    now = datetime.now()
    snoozed = []
    for a in alertas:
        if not a.ativo or a.insumo_id != insumo_id:
            continue
        new_snooze = now + timedelta(days=a.duracao_snooze_dias)
        sheets.update_scanner_row(
            spreadsheet_id, a.scanner_id,
            {"snooze_ate": new_snooze.isoformat(timespec="seconds")},
            service=service,
        )
        snoozed.append(a.scanner_id)
    return snoozed


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    run(dry_run=dry)
