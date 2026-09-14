"""Weekly proof-of-life digest.

The scanner only sends a message when a price *drops* (rules.classify) or when
a scanner goes stale (heartbeat). Stable prices therefore mean total silence —
which repeatedly left Luiza unsure whether the scanner was alive or broken.

This digest fixes that: once a week it confirms the scanner ran and lists the
cheapest delivered unit price seen for each active insumo over the last 7 days.
It always sends (unlike daily_summary, which only fires when an offer hit).

Runs 1x/week (Mon 08h BRT / 11 UTC) via .github/workflows/scanner-weekly-summary.yml.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta

from lib import sheets
from scanner import config, notifier
from scanner.history import _normalize_timestamp


WINDOW_DAYS = 7

_MESES = ["jan", "fev", "mar", "abr", "mai", "jun",
          "jul", "ago", "set", "out", "nov", "dez"]


def _spreadsheet_id() -> str:
    sid = os.environ.get("SPREADSHEET_ID")
    if not sid:
        raise RuntimeError("SPREADSHEET_ID env var not set")
    return sid


def _fmt_periodo(start: datetime, end: datetime) -> str:
    """'08–14/set' (same month) or '28/ago–03/set' (crossing months)."""
    if start.month == end.month:
        return f"{start.day:02d}–{end.day:02d}/{_MESES[end.month - 1]}"
    return (f"{start.day:02d}/{_MESES[start.month - 1]}–"
            f"{end.day:02d}/{_MESES[end.month - 1]}")


def build_rows(now: datetime) -> tuple[list[dict], int]:
    """Return (rows, total_scans) for the last WINDOW_DAYS.

    One row per active scanner with the cheapest delivered unit price in the
    window; `sem_dados=True` when nothing was observed (a red flag)."""
    sid = _spreadsheet_id()
    service = sheets.get_service()

    alertas = [a for a in config.get_alertas(sid, service=service) if a.ativo]
    produtos = {p["id"]: p["nome"] for p in sheets.get_produtos(sid, service=service)}
    cutoff = now - timedelta(days=WINDOW_DAYS)

    rows: list[dict] = []
    total_scans = 0
    for a in alertas:
        obs_list = sheets.get_precos_observados_by_scanner(sid, a.scanner_id, service=service)
        window = []
        for o in obs_list:
            ts_raw = _normalize_timestamp(o.get("timestamp"))
            try:
                ts = datetime.fromisoformat(ts_raw)
            except ValueError:
                continue
            if ts >= cutoff and (o.get("preco_unidade") or 0) > 0:
                window.append(o)

        total_scans += len(window)
        nome = produtos.get(a.insumo_id, a.insumo_id)
        if not window:
            rows.append({"insumo_nome": nome, "sem_dados": True})
            continue
        best = min(window, key=lambda o: o["preco_unidade"])
        rows.append({
            "insumo_nome": nome,
            "preco_unidade": best["preco_unidade"],
            "site": best.get("site", ""),
            "scans": len(window),
            "sem_dados": False,
        })
    return rows, total_scans


def run(dry_run: bool = False) -> int:
    now = datetime.now()
    rows, total_scans = build_rows(now)
    periodo = _fmt_periodo(now - timedelta(days=WINDOW_DAYS), now)
    print(f"weekly_summary: {len(rows)} insumo(s), {total_scans} scan(s) na janela")
    for r in rows:
        if r.get("sem_dados"):
            print(f"  - {r['insumo_nome']}: SEM DADOS")
        else:
            print(f"  - {r['insumo_nome']}: R$ {r['preco_unidade']:.2f}/un ({r['site']})")
    notifier.send_weekly_summary(rows, periodo, total_scans, dry_run=dry_run)
    return len(rows)


if __name__ == "__main__":
    run(dry_run="--dry-run" in sys.argv)
