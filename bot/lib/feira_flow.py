"""
Modo Feira — orquestração das mensagens do Telegram.

Liga o parser do Gemini (gemini.parse_feira_*) à camada de dados (feira.*) e
responde no chat. Enquanto há uma feira aberta para o chat, TODA mensagem
(texto / áudio transcrito / imagem) é interpretada como venda/fechamento/status
em vez de compra.

UX escolhida: registra a venda na hora e responde com um resumo curto + botão
"↩️ Desfazer" (callback `vundo:VEN-NNN`). Sem perguntas no meio — feito pro
ritmo da feira.
"""

import os

from . import feira, gemini, telegram_client as tg


def _sid() -> str:
    return os.environ["SPREADSHEET_ID"]


def _esc(s) -> str:
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _fmt_qtd(n) -> str:
    """30.0 -> '30', 2.5 -> '2,5'."""
    n = float(n)
    return str(int(n)) if n == int(n) else f"{n:g}".replace(".", ",")


# ============================================================================
# Abertura
# ============================================================================

def has_open_feira(chat_id: int) -> bool:
    return feira.get_open_feira(_sid(), chat_id) is not None


def try_open_from_text(chat_id: int, text: str) -> bool:
    """
    Try to open a feira from a free-text message ("saindo pra feira, 30 a R$18").

    Returns True if it opened a feira (or handled the request), False if the
    message wasn't a feira opening (caller should fall through to other handlers).
    """
    if has_open_feira(chat_id):
        # Already in a feira — this message isn't an opening; let the message
        # handler deal with it.
        return False
    # Cheap guard: only spend a Gemini call (and risk a false "open") when the
    # message actually mentions a feira. She always says "feira" when leaving;
    # the explicit /feira command covers any other phrasing.
    if "feira" not in text.lower():
        return False
    try:
        parsed = gemini.parse_feira_opening(text)
    except Exception:
        return False
    if not parsed.get("is_abertura"):
        return False
    return _open(chat_id, parsed)


def open_via_command(chat_id: int, args: str) -> None:
    """/feira [descrição livre] — opens a feira, parsing qty/price from args."""
    existing = feira.get_open_feira(_sid(), chat_id)
    if existing:
        tg.send_message(
            chat_id,
            f"⚠️ Já tem uma feira aberta (<b>{existing['id']}</b>). "
            f"Manda /fechar pra encerrar antes de abrir outra, ou /feira_status pra ver o parcial.",
        )
        return
    if args.strip():
        try:
            parsed = gemini.parse_feira_opening(args)
        except Exception:
            parsed = {}
    else:
        parsed = {}
    if not parsed.get("qtd_levada") and not parsed.get("preco_unit"):
        tg.send_message(
            chat_id,
            "🎪 <b>Abrir feira</b>\n\n"
            "Me conta quantos pudins você tá levando e por quanto. Ex:\n"
            "<i>tamo saindo pra feira, levando 30 pudins a R$18</i>\n\n"
            "Pode mandar por texto ou áudio.",
        )
        return
    _open(chat_id, parsed)


def _open(chat_id: int, parsed: dict) -> bool:
    qtd = parsed.get("qtd_levada")
    preco = parsed.get("preco_unit")
    descricao = parsed.get("descricao") or ""
    if not preco:
        tg.send_message(
            chat_id,
            "🎪 Quase! Só me fala o <b>preço</b> de cada pudim pra eu abrir a feira "
            "(ex: <i>a R$18</i>).",
        )
        return True
    qtd = float(qtd) if qtd else 0.0
    feira_id = feira.open_feira(
        _sid(), chat_id, qtd_levada=qtd, preco_unit=float(preco),
        descricao=descricao,
    )
    levados = f"{_fmt_qtd(qtd)} pudins" if qtd else "pudins (qtde não informada)"
    desc_line = f"\n📍 {_esc(descricao)}" if descricao else ""
    tg.send_message(
        chat_id,
        f"🎪 <b>Feira aberta!</b> ({feira_id}){desc_line}\n"
        f"Levando: <b>{levados}</b> a <b>R$ {float(preco):.2f}</b> cada.\n\n"
        f"Agora é só ir me avisando das vendas — por texto, áudio ou foto. Ex:\n"
        f"• <i>vendi 2 pro fulano</i>\n"
        f"• <i>vendi 2 agora</i> (sem nome)\n"
        f"• <i>vendi 2, a maria vai voltar pra pagar</i> (fiado)\n"
        f"• <i>vendi 3 pro joão no pix</i>\n\n"
        f"No fim: /fechar (ou me diz quantos voltaram e quanto recebeu).",
    )
    return True


# ============================================================================
# Mensagens durante a feira (texto / imagem)
# ============================================================================

def handle_text(chat_id: int, text: str) -> bool:
    """Handle a text message when a feira is open. Returns True if consumed."""
    f = feira.get_open_feira(_sid(), chat_id)
    if not f:
        return False
    try:
        parsed = gemini.parse_feira_message(text, preco_default=f["preco_unit"])
    except Exception as e:
        tg.send_message(chat_id, f"❌ Não consegui interpretar: <code>{_esc(e)}</code>")
        return True
    return _dispatch(chat_id, f, parsed, raw=text)


def handle_image(chat_id: int, image_bytes: bytes) -> bool:
    """Handle a photo when a feira is open. Returns True if consumed."""
    f = feira.get_open_feira(_sid(), chat_id)
    if not f:
        return False
    try:
        parsed = gemini.parse_feira_image(image_bytes, preco_default=f["preco_unit"])
    except Exception as e:
        tg.send_message(chat_id, f"❌ Não consegui ler a imagem: <code>{_esc(e)}</code>")
        return True
    return _dispatch(chat_id, f, parsed, raw="(imagem)")


def _dispatch(chat_id: int, f: dict, parsed: dict, raw: str) -> bool:
    intent = parsed.get("intent", "outro")
    if intent == "venda":
        return _register_venda(chat_id, f, parsed)
    if intent == "fechamento":
        return _handle_fechamento(chat_id, f, parsed)
    if intent == "status":
        send_status(chat_id, f)
        return True
    # outro
    tg.send_message(
        chat_id,
        "🤔 Não entendi se foi uma venda. Tenta assim: <i>vendi 2 pro fulano</i>.\n"
        "Pra ver o parcial: /feira_status · pra encerrar: /fechar",
    )
    return True


def _register_venda(chat_id: int, f: dict, parsed: dict) -> bool:
    qtde = parsed.get("qtde")
    if not qtde or float(qtde) <= 0:
        tg.send_message(
            chat_id,
            "🤔 Quantos pudins foram? Tenta: <i>vendi 2 pro fulano</i>.",
        )
        return True
    qtde = float(qtde)
    preco_unit = parsed.get("preco_unit") or f["preco_unit"]
    preco_unit = float(preco_unit)
    cliente = (parsed.get("cliente_nome") or "").strip()
    pago = parsed.get("pago", True)
    forma = (parsed.get("forma_pagamento") or "").strip().lower()
    if forma not in ("dinheiro", "pix"):
        forma = ""
    status_pgto = "pago" if pago else "fiado"
    if not pago:
        forma = ""  # fiado não tem forma ainda
    notas = (parsed.get("notas") or "").strip()

    ven_id, venda = feira.append_venda(
        _sid(), f["id"], qtde=qtde, preco_unit=preco_unit,
        cliente_nome=cliente, forma_pagamento=forma,
        status_pagamento=status_pgto, notas=notas,
    )

    total = venda["preco_total"]
    quem = _esc(cliente) if cliente else "<i>sem nome</i>"
    if status_pgto == "fiado":
        pgto_str = "🔴 <b>FIADO</b> (vai pagar depois)"
    elif forma == "dinheiro":
        pgto_str = "💵 dinheiro"
    elif forma == "pix":
        pgto_str = "📲 pix"
    else:
        pgto_str = "✅ pago"

    tg.send_message_with_buttons(
        chat_id,
        f"✅ <b>{_fmt_qtd(qtde)} pudim(ns)</b> → {quem} · "
        f"R$ {total:.2f} · {pgto_str}",
        [[{"text": "↩️ Desfazer", "callback_data": f"vundo:{ven_id}"}]],
    )
    return True


def _handle_fechamento(chat_id: int, f: dict, parsed: dict) -> bool:
    """User is wrapping up: store whatever closing info came, show running balance."""
    qv = parsed.get("qtd_voltou")
    din = parsed.get("dinheiro")
    pix = parsed.get("pix")
    if qv is not None or din is not None or pix is not None:
        feira.update_closing(
            _sid(), f["id"],
            qtd_voltou=float(qv) if qv is not None else None,
            dinheiro=float(din) if din is not None else None,
            pix=float(pix) if pix is not None else None,
        )
        # reload to reflect the just-written fields
        f = feira.get_open_feira(_sid(), chat_id) or f

    vendas = feira.get_vendas(_sid(), f["id"])
    bal = feira.compute_balanco(f, vendas)
    tg.send_message_with_buttons(
        chat_id,
        _format_balanco(f, bal, parcial=True)
        + "\n\nConfere os números. Quando estiver tudo certo, é só encerrar.",
        [
            [{"text": "🏁 Encerrar feira", "callback_data": f"vfecha:{f['id']}"}],
            [{"text": "Continuar vendendo", "callback_data": f"vcont:{f['id']}"}],
        ],
    )
    return True


# ============================================================================
# Comandos
# ============================================================================

def status_command(chat_id: int) -> None:
    f = feira.get_open_feira(_sid(), chat_id)
    if not f:
        tg.send_message(chat_id, "Nenhuma feira aberta. Abre uma com /feira.")
        return
    send_status(chat_id, f)


def send_status(chat_id: int, f: dict) -> None:
    vendas = feira.get_vendas(_sid(), f["id"])
    bal = feira.compute_balanco(f, vendas)
    tg.send_message(chat_id, _format_balanco(f, bal, parcial=True))


def close_command(chat_id: int) -> None:
    """/fechar — show the balance and offer to finalize."""
    f = feira.get_open_feira(_sid(), chat_id)
    if not f:
        tg.send_message(chat_id, "Nenhuma feira aberta pra fechar.")
        return
    vendas = feira.get_vendas(_sid(), f["id"])
    bal = feira.compute_balanco(f, vendas)
    falta = []
    if bal["qtd_voltou"] is None and bal["qtd_levada"]:
        falta.append("quantos pudins voltaram")
    if bal["recebido_informado"] is None:
        falta.append("quanto você recebeu em dinheiro e no pix")
    falta_line = ""
    if falta:
        falta_line = (
            "\n\n💡 Se quiser conferir o caixa, me diz " + " e ".join(falta) +
            " (ex: <i>voltaram 5, recebi 200 no dinheiro e 150 no pix</i>)."
        )
    tg.send_message_with_buttons(
        chat_id,
        _format_balanco(f, bal, parcial=True) + falta_line,
        [
            [{"text": "🏁 Encerrar feira", "callback_data": f"vfecha:{f['id']}"}],
            [{"text": "Continuar vendendo", "callback_data": f"vcont:{f['id']}"}],
        ],
    )


def cancel_open_feira(chat_id: int) -> bool:
    """Used by /cancel — abort an open feira. Returns True if one was open."""
    f = feira.get_open_feira(_sid(), chat_id)
    if not f:
        return False
    feira.cancel_feira(_sid(), f["id"])
    tg.send_message(chat_id, f"🚫 Feira {f['id']} cancelada (as vendas ficam registradas na planilha).")
    return True


# ============================================================================
# Callbacks
# ============================================================================

def handle_callback(chat_id: int, message_id: int, parts: list, callback_query_id: str) -> bool:
    """Handle feira-related button presses. Returns True if it owned the action."""
    action = parts[0]
    if action == "vundo":
        ven_id = parts[1]
        ok = feira.cancel_venda(_sid(), ven_id)
        tg.answer_callback_query(callback_query_id, "Desfeito" if ok else "Já estava desfeito")
        tg.edit_message_text(
            chat_id, message_id,
            ("↩️ Venda desfeita." if ok else "Essa venda já tinha sido desfeita."),
            reply_markup=None,
        )
        return True
    if action == "vcont":
        tg.answer_callback_query(callback_query_id, "")
        tg.edit_message_text(chat_id, message_id, "👍 Bora continuar vendendo!", reply_markup=None)
        return True
    if action == "vfecha":
        feira_id = parts[1]
        tg.answer_callback_query(callback_query_id, "")
        f = feira.get_open_feira(_sid(), chat_id)
        if not f or f["id"] != feira_id:
            tg.edit_message_text(chat_id, message_id, "Essa feira já não está aberta.", reply_markup=None)
            return True
        feira.finalize_feira(_sid(), feira_id)
        vendas = feira.get_vendas(_sid(), feira_id)
        bal = feira.compute_balanco(f, vendas)
        tg.edit_message_text(
            chat_id, message_id,
            "🏁 <b>Feira encerrada!</b>\n\n" + _format_balanco(f, bal, parcial=False),
            reply_markup=None,
        )
        return True
    return False


# ============================================================================
# Formatação do balanço
# ============================================================================

def _format_balanco(f: dict, bal: dict, parcial: bool) -> str:
    titulo = "📊 <b>Parcial da feira</b>" if parcial else "📊 <b>Balanço final</b>"
    lines = [
        f"{titulo} ({f['id']})",
        f"Pudins: levou <b>{_fmt_qtd(bal['qtd_levada'])}</b> · "
        f"vendeu <b>{_fmt_qtd(bal['qtde_vendida'])}</b>"
        + (f" · voltou <b>{_fmt_qtd(bal['qtd_voltou'])}</b>" if bal["qtd_voltou"] is not None else ""),
    ]
    if bal["qtd_nao_contabilizada"] is not None and abs(bal["qtd_nao_contabilizada"]) >= 0.01:
        n = bal["qtd_nao_contabilizada"]
        if n > 0:
            lines.append(f"⚠️ <b>{_fmt_qtd(n)}</b> não batem (levou − vendeu − voltou). Brinde, perda ou venda não anotada?")
        else:
            lines.append(f"⚠️ Contas batem com <b>{_fmt_qtd(-n)}</b> a mais vendidos que o levado. Confere a qtde levada.")

    lines.append("")
    lines.append(f"💰 <b>Faturado: R$ {bal['faturado_total']:.2f}</b> ({bal['n_vendas']} venda(s))")
    lines.append(f"   💵 Dinheiro: R$ {bal['dinheiro']:.2f}")
    lines.append(f"   📲 Pix: R$ {bal['pix']:.2f}")
    if bal["pago_sem_forma"] > 0:
        lines.append(f"   ✅ Pago (forma não anotada): R$ {bal['pago_sem_forma']:.2f}")
    if bal["fiado_total"] > 0:
        lines.append(f"   🔴 Fiado (a receber): R$ {bal['fiado_total']:.2f}")

    if bal["fiados"]:
        lines.append("")
        lines.append("<b>Quem ficou devendo:</b>")
        for fi in bal["fiados"]:
            lines.append(f"   • {_esc(fi['nome'])} — {_fmt_qtd(fi['qtde'])} pudim(ns) · R$ {fi['valor']:.2f}")

    if bal["recebido_informado"] is not None:
        lines.append("")
        lines.append(f"🧾 Você informou ter recebido: R$ {bal['recebido_informado']:.2f}")
        d = bal["divergencia_caixa"]
        if abs(d) < 0.01:
            lines.append("   ✅ Bate certinho com o pago registrado.")
        elif d > 0:
            lines.append(f"   ⚠️ R$ {d:.2f} a mais do que o registrado como pago.")
        else:
            lines.append(f"   ⚠️ Faltam R$ {-d:.2f} em relação ao registrado como pago.")

    return "\n".join(lines)
