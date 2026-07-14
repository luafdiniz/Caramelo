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

    # If there's a promo AND we have the 2-unit point in the curve, the
    # per-unit price at qtde=2 is the "promo effect isolated from freight" —
    # highly readable for the "50% no 2°" pattern.
    if produto.promocoes:
        promo_str = ", ".join(produto.promocoes)
        promo_row = next((c for c in produto.frete_curve if c["qtde"] == 2), None)
        if promo_row:
            preco_produto_2un = (promo_row["preco_produto_com_desconto"]) / 2
            lines.append(
                f"🎁 Promoção <b>{_esc(promo_str)}</b>: em pares "
                f"<b>{_fmt_brl(preco_produto_2un)}</b>/un só o produto"
            )
        else:
            lines.append(f"🎁 Promoção ativa: <b>{_esc(promo_str)}</b>")
        lines.append("")

    # Freight curve: how much you actually pay per unit at each cart size.
    # Consecutive rows where freight is already zero get collapsed so we
    # don't show 84/85 both marked "sem frete" — just the first one.
    if produto.frete_curve:
        lines.append("<b>📦 Total pago por unidade (produto + frete):</b>")
        emb_word = "embalagem" if produto.qtde_unidades > 1 else "unidade"
        emb_word_pl = "embalagens" if produto.qtde_unidades > 1 else "unidades"

        prev_was_free = False
        for pt in produto.frete_curve:
            q = pt["qtde"]
            unid = pt["preco_unid_delivered"]
            is_free = pt["frete"] == 0 and q > 1
            if is_free and prev_was_free:
                continue
            prev_was_free = is_free
            free_tag = "  ✓ sem frete" if is_free else ""
            label = f"{q} {emb_word if q == 1 else emb_word_pl}"
            lines.append(f"  {label:<18} → <b>{_fmt_brl(unid)}</b>/un{free_tag}")
        zeros = [pt for pt in produto.frete_curve if pt["frete"] == 0 and pt["qtde"] > 1]
        if zeros:
            first_zero = min(zeros, key=lambda p: p["qtde"])
            lines.append(f"💡 Frete zera a partir de <b>{first_zero['qtde']}</b> {emb_word_pl}")

    if verdict.severity == "alvo":
        if verdict.savings is not None and verdict.savings > 0:
            lines.append("")
            lines.append(f"💸 <b>{_fmt_brl(verdict.savings)}</b> abaixo do seu preço-alvo por unidade")
    elif verdict.baseline is not None:
        lines.append("")
        lines.append(f"📊 Preço habitual (últimos 30 dias): {_fmt_brl(verdict.baseline)}/un")
        if verdict.savings is not None and verdict.savings > 0:
            lines.append(f"💸 <b>{_fmt_brl(verdict.savings)}</b>/un mais barato que o habitual")
    elif verdict.ultimo_preco is not None:
        lines.append("")
        lines.append(f"📊 Comparado ao último preço observado: {_fmt_brl(verdict.ultimo_preco)}/un")

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
