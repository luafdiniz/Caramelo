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

import math

from lib import sheets
from scanner import (
    config, email_notifier, extractor, frete as frete_mod,
    frete_overrides, history as history_mod, notifier, rules,
)
from scanner.scrapers import mercadolivre, vtex
from scanner.scrapers.base import ProductResult


def _apply_frete(produto: ProductResult, qtde_bulk: int = 1) -> ProductResult:
    """Consult freight for this product at BOTH qtde=1 (comparison) and
    qtde=qtde_bulk (realistic cart). Populates all *_com_frete fields
    and overwrites preco_unidade with the bulk delivered price so
    downstream rules operate on the realistic cart cost."""
    produto.bulk_qtde = max(int(qtde_bulk or 1), 1)

    if produto.site not in vtex.HOSTNAMES or not produto.sku_id:
        # No freight source available
        produto.frete = 0.0
        produto.preco_com_frete = produto.preco
        produto.preco_unidade_com_frete = produto.preco_unidade
        produto.frete_1un = 0.0
        produto.preco_com_frete_1un = produto.preco
        produto.preco_unidade_com_frete_1un = produto.preco_unidade
        return produto

    seller = produto.seller_id or "1"

    # First pass: simulate the bulk_qtde cart just to learn the effective
    # per-unit rate after promotional discounts. We keep this result and
    # feed it into the final curve so we don't call the same qtde twice.
    threshold = frete_overrides.get_free_threshold(produto.site)
    bulk_sim = None
    if threshold and produto.preco > 0:
        bulk_sim = frete_mod.simulate_cart(
            produto.site, produto.sku_id, produto.bulk_qtde, seller_id=seller,
        )

    extras: list[int] = [2]
    if bulk_sim and bulk_sim.total_produto > 0 and produto.bulk_qtde > 0:
        rate_effective = bulk_sim.total_produto / produto.bulk_qtde
        if rate_effective > 0 and threshold:
            breakpoint_est = math.ceil(threshold / rate_effective)
            extras.append(breakpoint_est)
            extras.append(breakpoint_est + 1)

    grid_qs = frete_mod.default_grid(produto.bulk_qtde, extra=extras)
    # Skip bulk_qtde in the curve call — we already have bulk_sim from above.
    remaining_qs = [q for q in grid_qs if q != produto.bulk_qtde] if bulk_sim else grid_qs
    sims = frete_mod.simulate_curve(
        produto.site, produto.sku_id, seller_id=seller, quantities=remaining_qs,
    )
    if bulk_sim:
        sims.append(bulk_sim)
        sims.sort(key=lambda s: s.quantity_used)

    unids_por_emb = produto.qtde_unidades if produto.qtde_unidades > 0 else 1

    # Build the curve dicts — total_produto here is AFTER promo discounts,
    # so the delivered/un price already reflects "50% no 2°" and similar.
    curve_dicts: list[dict] = []
    for sim in sims:
        total_unids = unids_por_emb * sim.quantity_used
        preco_unid = round(sim.total_final / total_unids, 4) if total_unids else sim.total_final
        curve_dicts.append({
            "qtde": sim.quantity_used,
            "frete": sim.frete,
            "preco_total": sim.total_final,
            "preco_produto_com_desconto": sim.total_produto,
            "desconto": sim.total_descontos,
            "preco_unid_delivered": preco_unid,
            "prazo": sim.prazo,
        })
    produto.frete_curve = curve_dicts

    by_q = {c["qtde"]: c for c in curve_dicts}
    one = by_q.get(1) or curve_dicts[0]
    produto.frete_1un = one["frete"]
    produto.preco_com_frete_1un = one["preco_total"]
    produto.preco_unidade_com_frete_1un = one["preco_unid_delivered"]

    bulk = by_q.get(produto.bulk_qtde) or curve_dicts[-1]
    produto.frete = bulk["frete"]
    produto.frete_prazo_dias = bulk.get("prazo") or one.get("prazo") or ""
    produto.preco_com_frete = bulk["preco_total"]
    produto.preco_unidade_com_frete = bulk["preco_unid_delivered"]

    # Guard: if the freight sim came back empty (WAF/network), the bulk
    # row can be zeroed out. Leaving preco_unidade at 0 would trigger a
    # false-positive ⚠️ alvo (0 ≤ preco_alvo) or 🔥 forte. Keep the raw
    # per-unit shelf price instead so classify() falls back to "no drop".
    if produto.preco_unidade_com_frete > 0:
        produto.preco_unidade = produto.preco_unidade_com_frete
    return produto


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
    email_batch: list[email_notifier.OfferEntry] = []

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

        # Apply freight to each site's candidate BEFORE picking global best —
        # this reorders results by delivered price. Free-shipping thresholds
        # are respected by the store's API. bulk_qtde comes from the alert.
        for r in all_results:
            _apply_frete(r, qtde_bulk=alerta.qtde_bulk)
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
                    frete=global_best.frete,
                    preco_com_frete=global_best.preco_com_frete,
                    service=service,
                )
            except Exception as e:
                print(f"  ! append_preco_observado failed: {e}")
                summary["errors"] += 1
                continue

        # 5. classify against merged history (scans + compras from NF-e/bot)
        full_hist = history_mod.get_full_history(
            sid, alerta.scanner_id, alerta.insumo_id, service=service,
        )
        # In prod path we already wrote this scan's obs; drop the last scan
        # so we don't compare against ourselves.
        if not dry_run and full_hist and full_hist[-1].get("source") == "scan":
            full_hist = full_hist[:-1]

        verdict = rules.classify(global_best, full_hist, alerta, now=now)
        print(f"  → {verdict.severity or 'sem alerta'}: {verdict.reason}")

        # 6. notify if warranted
        if verdict.notifica:
            insumo_nome = _get_insumo_nome(sid, alerta.insumo_id, prod_names)
            notifier.send_offer(alerta, global_best, verdict, insumo_nome=insumo_nome, dry_run=dry_run)
            email_batch.append(email_notifier.OfferEntry(
                alerta=alerta, produto=global_best, verdict=verdict, insumo_nome=insumo_nome,
            ))
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

    # 8. one consolidated email per scan (skipped if nothing fired)
    if email_batch:
        try:
            email_notifier.send_scan_batch(email_batch, dry_run=dry_run)
        except Exception as e:
            print(f"email batch send failed (non-fatal): {e}")

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
