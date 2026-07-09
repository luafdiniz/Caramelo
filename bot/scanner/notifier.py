"""Format + send scanner offer alerts to Telegram.

Assumes the Caramelo Telegram bot token is in TELEGRAM_BOT_TOKEN env var
(same env the bot uses). Recipients come from ALERT_CHAT_IDS env
(comma-separated). Group chat IDs are negative, so we parse via int()
instead of isdigit().
"""

from __future__ import annotations

import html
import os
from typing import Optional

from lib import telegram_client
from scanner.config import AlertaConfig
from scanner.rules import Verdict
from scanner.scrapers.base import ProductResult


_SITE_LABEL = {
    "supernosso": "Supernosso",
    "apoio": "Apoio Entrega",
    "santoantonio": "Santo Antônio",
    "ML": "Mercado Livre",
}

_SEVERITY_HEADER = {
    "forte": "🔥 OFERTA FORTE",
    "boa": "✨ Oferta boa",
    "alvo": "⚠️ Preço-alvo atingido",
}


def _chat_ids() -> list[int]:
    raw = os.environ.get("ALERT_CHAT_IDS", "").strip()
    if not raw:
        raise RuntimeError(
            "ALERT_CHAT_IDS env var not configured — set it to a "
            "comma-separated list of Telegram chat IDs (personal chats "
            "are positive integers, groups are negative)."
        )
    ids: list[int] = []
    for x in raw.split(","):
        x = x.strip()
        if not x:
            continue
        try:
            ids.append(int(x))
        except ValueError:
            print(f"notifier: ignoring invalid chat_id {x!r}")
    if not ids:
        raise RuntimeError("ALERT_CHAT_IDS parsed to empty list")
    return ids


def _fmt_brl(value: Optional[float]) -> str:
    if value is None:
        return "—"
    return f"R$ {value:.2f}".replace(".", ",")


def _fmt_brl_precise(value: float) -> str:
    return f"R$ {value:.3f}".replace(".", ",")


def _esc(s: str) -> str:
    return html.escape(s or "", quote=False)


def build_message(
    alerta: AlertaConfig,
    produto: ProductResult,
    verdict: Verdict,
    insumo_nome: str = "",
) -> str:
    header = _SEVERITY_HEADER.get(verdict.severity or "", "🔔 Oferta")
    nome = insumo_nome or alerta.insumo_id
    site_label = _SITE_LABEL.get(produto.site, produto.site)

    lines = [
        f"<b>{header}</b> — {_esc(nome)}",
        f"<i>{_esc(produto.titulo[:80])}</i>",
        "",
        f"💰 Preço: <b>{_fmt_brl(produto.preco)}</b>"
        + (f" ({produto.qtde_unidades}un = {_fmt_brl_precise(produto.preco_unidade)}/un)"
           if produto.qtde_unidades > 1 else ""),
    ]

    hist_bits = []
    if verdict.min_historico is not None:
        hist_bits.append(f"mín: {_fmt_brl_precise(verdict.min_historico)}/un")
    if verdict.ultimo_preco is not None:
        hist_bits.append(f"últ: {_fmt_brl_precise(verdict.ultimo_preco)}/un")
    if hist_bits:
        lines.append(f"📊 Histórico: {' | '.join(hist_bits)}")

    lines.append(f"📍 {_esc(site_label)}")

    flags = []
    if produto.tem_oferta_clube:
        flags.append("💳 tem oferta melhor no clube (verificar login)")
    if not produto.marca_confirmada and alerta.marca_obrigatoria:
        flags.append(f"⚠️ marca <b>{_esc(alerta.marca_obrigatoria)}</b> não confirmada — conferir antes de comprar")
    if flags:
        lines.append("")
        lines.extend(flags)

    lines.append("")
    lines.append(f"🔗 <a href=\"{_esc(produto.url)}\">Ver oferta</a>")
    lines.append(f"Silenciar: <code>/scanner snooze {_esc(alerta.scanner_id)}</code>")

    return "\n".join(lines)


def send_offer(
    alerta: AlertaConfig,
    produto: ProductResult,
    verdict: Verdict,
    insumo_nome: str = "",
    dry_run: bool = False,
) -> None:
    """Format and dispatch. In dry_run mode prints instead of sending."""
    text = build_message(alerta, produto, verdict, insumo_nome)
    if dry_run:
        print("---- DRY RUN telegram message ----")
        print(text)
        print("----------------------------------")
        return
    for cid in _chat_ids():
        try:
            telegram_client.send_message(cid, text)
        except Exception as e:
            print(f"notifier: send to {cid} failed: {e}")


def send_heartbeat_alert(offline: list[dict], dry_run: bool = False) -> None:
    """Notify when scanners haven't updated in a while.

    `offline` items: [{"scanner_id": ..., "termo": ..., "ultima_verif": ...}]
    """
    if not offline:
        return
    lines = ["<b>⚠️ Scanner sem sinal</b>", ""]
    for row in offline:
        lines.append(
            f"• <code>{_esc(row['scanner_id'])}</code> "
            f"({_esc(row.get('termo',''))}) — última verif: {_esc(str(row.get('ultima_verif','?')))}"
        )
    text = "\n".join(lines)
    if dry_run:
        print(text)
        return
    for cid in _chat_ids():
        try:
            telegram_client.send_message(cid, text)
        except Exception as e:
            print(f"heartbeat notifier: send to {cid} failed: {e}")
