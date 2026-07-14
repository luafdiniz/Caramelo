"""Email delivery via Gmail SMTP.

Uses App Password auth (2FA required on the Gmail account). One consolidated
message per scan — even if 5 alerts fire in one run, recipients get 1 email
with 5 cards, not 5 emails.

Env vars:
    EMAIL_FROM           — Gmail address (e.g. caramelobeaga@gmail.com)
    EMAIL_APP_PASSWORD   — 16-char App Password from myaccount.google.com/apppasswords
    EMAIL_TO             — comma-separated recipient addresses

HTML uses table-based layout (no <style> in <head>) so Gmail renders it
consistently on desktop and mobile.
"""

from __future__ import annotations

import html
import os
import smtplib
import ssl
from dataclasses import dataclass
from datetime import datetime
from email.message import EmailMessage
from typing import Optional

from scanner.config import AlertaConfig
from scanner.rules import Verdict
from scanner.scrapers.base import ProductResult


SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587


@dataclass
class OfferEntry:
    alerta: AlertaConfig
    produto: ProductResult
    verdict: Verdict
    insumo_nome: str


_SITE_LABEL = {
    "supernosso": "Supernosso",
    "apoio": "Apoio Entrega",
    "santoantonio": "Santo Antônio",
    "ML": "Mercado Livre",
}

_SEVERITY_LABEL = {
    "forte": ("🔥 OFERTA", "#e64a19"),
    "alvo": ("⚠️ Preço-alvo atingido", "#f9a825"),
}


def _env(name: str) -> Optional[str]:
    v = os.environ.get(name, "").strip()
    return v or None


def _recipients() -> list[str]:
    raw = _env("EMAIL_TO") or ""
    return [x.strip() for x in raw.split(",") if x.strip()]


def _fmt_brl(v: Optional[float]) -> str:
    if v is None:
        return "—"
    return f"R$ {v:.2f}".replace(".", ",")


def _esc(s: str) -> str:
    return html.escape(s or "", quote=True)


def _card_html(entry: OfferEntry) -> str:
    label, color = _SEVERITY_LABEL.get(entry.verdict.severity or "", ("🔔 Oferta", "#555"))
    site = _SITE_LABEL.get(entry.produto.site, entry.produto.site)

    nome = _esc(entry.insumo_nome or entry.alerta.insumo_id)
    titulo = _esc(entry.produto.titulo[:120])

    p = entry.produto
    # Best delivered price from the curve (the qtde_bulk row is what the classifier uses)
    bulk_row = next((c for c in p.frete_curve if c["qtde"] == p.bulk_qtde), None) or (
        p.frete_curve[0] if p.frete_curve else None
    )
    preco_delivered = bulk_row["preco_unid_delivered"] if bulk_row else p.preco_unidade
    label_qtde = bulk_row["qtde"] if bulk_row else 1
    unids = "un" if p.qtde_unidades > 1 else ""
    preco_line = (
        f"<b style='font-size:22px;color:#111'>{_fmt_brl(preco_delivered)}</b>"
        f" <span style='color:#666'>por unidade comprando {label_qtde} {unids}embalagens</span>"
    )

    curve_html = ""
    if p.frete_curve:
        emb_word_pl = "embalagens" if p.qtde_unidades > 1 else "unidades"
        rows = []
        for pt in p.frete_curve:
            q = pt["qtde"]
            frete_v = pt["frete"]
            unid = pt["preco_unid_delivered"]
            frete_tag = "<span style='color:#2e7d32;font-weight:600'>frete grátis</span>" \
                if frete_v == 0 and q > 1 else f"frete {_fmt_brl(frete_v)}"
            label = f"{q} {emb_word_pl if q > 1 else ('embalagem' if p.qtde_unidades > 1 else 'unidade')}"
            rows.append(
                f"<tr>"
                f"<td style='padding:4px 8px;color:#555;font-size:13px'>{label}</td>"
                f"<td style='padding:4px 8px;font-weight:600;font-size:14px'>{_fmt_brl(unid)}/un</td>"
                f"<td style='padding:4px 8px;color:#888;font-size:12px'>{frete_tag}</td>"
                f"</tr>"
            )
        curve_html = (
            f"<div style='margin-top:12px;font-size:13px;color:#333;font-weight:600'>"
            f"📦 Preço/un dependendo do carrinho:</div>"
            f"<table style='margin-top:6px;border-collapse:collapse'>{''.join(rows)}</table>"
        )
        zeros = [pt for pt in p.frete_curve if pt["frete"] == 0 and pt["qtde"] > 1]
        if zeros:
            first_zero = min(zeros, key=lambda x: x["qtde"])
            curve_html += (
                f"<div style='margin-top:6px;color:#2e7d32;font-size:13px;font-weight:600'>"
                f"💡 A partir de {first_zero['qtde']} {emb_word_pl} o frete zera</div>"
            )

    lines_meta = []
    if entry.verdict.severity == "alvo":
        if entry.verdict.savings is not None and entry.verdict.savings > 0:
            lines_meta.append(f"💸 <b>{_fmt_brl(entry.verdict.savings)}</b> abaixo do seu preço-alvo por unidade")
    elif entry.verdict.baseline is not None:
        lines_meta.append(f"📊 Preço habitual (últimos 30 dias): <b>{_fmt_brl(entry.verdict.baseline)}</b>/un")
        if entry.verdict.savings and entry.verdict.savings > 0:
            lines_meta.append(f"💸 <b>{_fmt_brl(entry.verdict.savings)}</b>/un mais barato que o habitual")
    elif entry.verdict.ultimo_preco is not None:
        lines_meta.append(f"📊 Último preço observado: <b>{_fmt_brl(entry.verdict.ultimo_preco)}</b>/un")

    flags_html = ""
    if entry.produto.tem_oferta_clube:
        flags_html += "<div style='background:#fff3cd;padding:8px;border-radius:4px;margin-top:8px;font-size:13px'>💳 Tem oferta melhor no clube — verificar login</div>"
    if not entry.produto.marca_confirmada and entry.alerta.marca_obrigatoria:
        flags_html += (
            f"<div style='background:#ffebee;padding:8px;border-radius:4px;margin-top:8px;font-size:13px'>"
            f"⚠️ Marca <b>{_esc(entry.alerta.marca_obrigatoria)}</b> não confirmada — conferir antes de comprar"
            f"</div>"
        )

    return f"""
<table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%"
       style="margin-bottom:16px;border:1px solid #e0e0e0;border-radius:8px;background:#fff">
  <tr>
    <td style="padding:16px 20px;border-left:4px solid {color};">
      <div style="font-size:13px;font-weight:bold;color:{color};letter-spacing:0.5px">
        {label}
      </div>
      <div style="font-size:18px;color:#111;margin-top:4px;font-weight:600">{nome}</div>
      <div style="font-size:13px;color:#888;margin-top:2px">{titulo}</div>
      <div style="margin-top:14px">{preco_line}</div>
      {curve_html}
      <div style="font-size:14px;color:#333;margin-top:10px;line-height:1.6">
        {"<br>".join(lines_meta)}
      </div>
      <div style="font-size:13px;color:#666;margin-top:10px">📍 {_esc(site)}</div>
      {flags_html}
      <div style="margin-top:14px">
        <a href="{_esc(entry.produto.url)}"
           style="display:inline-block;background:{color};color:#fff;padding:10px 20px;
                  border-radius:4px;text-decoration:none;font-size:14px;font-weight:500">
          Ver oferta →
        </a>
      </div>
    </td>
  </tr>
</table>
"""


def _build_email_html(entries: list[OfferEntry], subject_title: str, intro: str = "") -> str:
    cards = "\n".join(_card_html(e) for e in entries)
    intro_html = f"<p style='color:#555;font-size:14px;margin:0 0 20px'>{_esc(intro)}</p>" if intro else ""
    return f"""<!doctype html>
<html><body style="margin:0;padding:20px;background:#f5f5f5;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Arial,sans-serif">
  <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="max-width:600px;margin:0 auto">
    <tr><td>
      <h1 style="font-size:22px;color:#111;margin:0 0 6px">🍮 Scanner Caramelo</h1>
      <div style="font-size:14px;color:#666;margin-bottom:20px">{_esc(subject_title)}</div>
      {intro_html}
      {cards}
      <div style="text-align:center;color:#999;font-size:12px;margin-top:24px">
        Enviado pelo bot Caramelo •
        <a href="https://docs.google.com/spreadsheets/d/{os.environ.get('SPREADSHEET_ID','')}"
           style="color:#999">ver histórico</a>
      </div>
    </td></tr>
  </table>
</body></html>"""


def _send_smtp(subject: str, html_body: str, recipients: list[str], dry_run: bool) -> None:
    sender = _env("EMAIL_FROM")
    password = _env("EMAIL_APP_PASSWORD")

    if dry_run:
        print(f"---- DRY RUN email ----")
        print(f"From: {sender}")
        print(f"To: {', '.join(recipients)}")
        print(f"Subject: {subject}")
        print(f"HTML body: {len(html_body)} chars")
        print("-----------------------")
        return

    if not sender or not password:
        print("email_notifier: EMAIL_FROM or EMAIL_APP_PASSWORD missing — skipping")
        return
    if not recipients:
        print("email_notifier: no EMAIL_TO recipients — skipping")
        return

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = f"Scanner Caramelo <{sender}>"
    msg["To"] = ", ".join(recipients)
    msg.set_content("Esta mensagem tem conteúdo HTML — abra num cliente compatível.")
    msg.add_alternative(html_body, subtype="html")

    ctx = ssl.create_default_context()
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as s:
        s.ehlo()
        s.starttls(context=ctx)
        s.ehlo()
        s.login(sender, password)
        s.send_message(msg)


def send_scan_batch(entries: list[OfferEntry], dry_run: bool = False) -> None:
    """Send one email consolidating all offers found in a single scan."""
    if not entries:
        return
    n = len(entries)
    subject = f"🔥 {n} nova{'s' if n > 1 else ''} oferta{'s' if n > 1 else ''} — Scanner Caramelo"
    when = datetime.now().strftime("%d/%m %Hh%M")
    intro = f"Scan de {when} encontrou {n} oferta{'s' if n > 1 else ''}:"
    html_body = _build_email_html(entries, subject_title=when, intro=intro)
    _send_smtp(subject, html_body, _recipients(), dry_run=dry_run)


def send_daily_summary(entries: list[OfferEntry], dry_run: bool = False) -> None:
    """Send end-of-day summary of all offers detected today.

    Called by scanner.daily_summary. Skipped when entries is empty (no
    'preço estável, nada aconteceu' spam)."""
    if not entries:
        print("daily summary: no offers today, skipping")
        return
    n = len(entries)
    today = datetime.now().strftime("%d/%m/%Y")
    subject = f"📊 Resumo do dia — {n} oferta{'s' if n > 1 else ''} • Scanner Caramelo"
    intro = f"Hoje ({today}) o scanner encontrou {n} oferta{'s' if n > 1 else ''}:"
    html_body = _build_email_html(entries, subject_title=f"Resumo {today}", intro=intro)
    _send_smtp(subject, html_body, _recipients(), dry_run=dry_run)
