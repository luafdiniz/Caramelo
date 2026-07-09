"""Daily heartbeat check.

Alerts when any active scanner hasn't recorded a fresh observation in more
than STALE_HOURS. Catches silent breakage (site layout changes, service
account auth expiring, cron misfires) that the main runner cannot self-detect.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta

from lib import sheets
from scanner import config, notifier


STALE_HOURS = 36


def _spreadsheet_id() -> str:
    sid = os.environ.get("SPREADSHEET_ID")
    if not sid:
        raise RuntimeError("SPREADSHEET_ID env var not set")
    return sid


def check(dry_run: bool = False) -> list[dict]:
    """Return list of stale scanners (also notifies unless dry_run)."""
    sid = _spreadsheet_id()
    service = sheets.get_service()

    alertas = config.get_active_alertas(sid, service=service)
    threshold = datetime.now() - timedelta(hours=STALE_HOURS)

    offline: list[dict] = []
    for a in alertas:
        if a.ultima_verif is None or a.ultima_verif < threshold:
            offline.append({
                "scanner_id": a.scanner_id,
                "termo": a.termo_busca,
                "ultima_verif": a.ultima_verif.isoformat(timespec="seconds") if a.ultima_verif else "nunca",
            })

    if offline:
        print(f"heartbeat: {len(offline)} scanner(s) offline")
        for o in offline:
            print(f"  - {o['scanner_id']} ({o['termo']}) — last: {o['ultima_verif']}")
        notifier.send_heartbeat_alert(offline, dry_run=dry_run)
    else:
        print("heartbeat: all scanners fresh")

    return offline


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    check(dry_run=dry)
