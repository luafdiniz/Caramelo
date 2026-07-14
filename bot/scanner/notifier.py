"""Format + send scanner offer alerts to Telegram.

Message format (per Luiza's request 2026-07-09):
- 3 elements in each message: link, current price, savings vs. usual price.
- Absolute values ("R$ 4,00 agora / habitual R$ 4,99 / você economiza R$ 0,99")
  rather than percentages — easier to read at a glance.

Recipients from ALERT_CHAT_IDS env (comma-separated, negatives OK for groups).
Returns the Telegram message_id from `sendMessage` so callers can persist and
delete later if needed.
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
    "forte": "🔥 OFERTA",
    "alvo": "⚠️ Preço-alvo atingido",
}


def _chat_ids() -> list[int]:
    raw = os.environ.get("ALERT_CHAT_IDS", "").strip()
    if not raw:
        raise RuntimeError(
            "ALERT_CHAT_IDS env var not configured — set it to a "
            "comma-separated list of Telegram chat IDs."
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
    ]

    lines.append(f"💰 <b>{_fmt_brl(produto.preco_unidade_com_frete or produto.preco_unidade)}</b> por unidade")

    # Freight breakdown (only when we actually consulted frete)
    if produto.preco_com_frete > 0:
        prazo = f" • {_esc(produto.frete_prazo_dias)} dias úteis" if produto.frete_prazo_dias else ""
        if produto.bulk_qtde > 1:
            emb = produto.qtde_unidades
            total_unids = emb * produto.bulk_qtde
            lines.append(
                f"📦 Comprando {produto.bulk_qtde} embalagens"
                + (f" (= {total_unids}un)" if emb > 1 else "")
                + f": produto {_fmt_brl(produto.preco * produto.bulk_qtde)} "
                + f"+ frete {_fmt_brl(produto.frete)} = "
                + f"<b>{_fmt_brl(produto.preco_com_frete)}</b>{prazo}"
            )
            if produto.preco_com_frete_1un and produto.preco_unidade_com_frete_1un > produto.preco_unidade_com_frete:
                lines.append(
                    f"↪️ Comprando 1 embalagem: {_fmt_brl(produto.preco_unidade_com_frete_1un)}/un "
                    f"(frete {_fmt_brl(produto.frete_1un)}) — comprar em volume dilui"
                )
        else:
            lines.append(
                f"📦 Produto {_fmt_brl(produto.preco)} + frete {_fmt_brl(produto.frete)} = "
                f"<b>{_fmt_brl(produto.preco_com_frete)}</b>{prazo}"
            )

    if verdict.baseline is not None:
        lines.append(f"📊 Preço habitual: {_fmt_brl(verdict.baseline)} por unidade")
    elif verdict.ultimo_preco is not None:
        lines.append(f"📊 Último preço: {_fmt_brl(verdict.ultimo_preco)} por unidade")

    if verdict.savings is not None and verdict.savings > 0:
        lines.append(f"💸 Você economiza {_fmt_brl(verdict.savings)} por unidade")

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
) -> list[int]:
    """Format and dispatch. Returns list of Telegram message_ids sent
    (empty list on dry_run or send failure). Persist to enable future delete."""
    text = build_message(alerta, produto, verdict, insumo_nome)
    if dry_run:
        print("---- DRY RUN telegram message ----")
        print(text)
        print("----------------------------------")
        return []

    message_ids: list[int] = []
    for cid in _chat_ids():
        try:
            resp = telegram_client.send_message(cid, text)
            mid = (resp or {}).get("result", {}).get("message_id")
            if mid:
                message_ids.append(int(mid))
        except Exception as e:
            print(f"notifier: send to {cid} failed: {e}")
    return message_ids


def send_heartbeat_alert(offline: list[dict], dry_run: bool = False) -> None:
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
