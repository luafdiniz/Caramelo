"""
Modo Feira — orquestração das mensagens do Telegram.

Liga o parser do Gemini (gemini.parse_feira_*) à camada de dados (feira.*) e
responde no chat. Suporta MAIS DE UM tamanho de pudim por feira (ex: 200g a
R$18 e 500g a R$45).

Enquanto há uma feira ativa (aberta ou em rascunho) para o chat, TODA mensagem
(texto / áudio transcrito / imagem) é interpretada no contexto da feira em vez
de compra.

Fluxo de abertura (2 etapas tolerantes):
- "saindo pra feira, 63 de 200g e 4 de 500g" → sem preços → vira RASCUNHO e o
  bot pergunta os preços.
- "18 o de 200g e 45 o de 500g" → completa o rascunho → feira ABERTA.

Vendas: registra na hora + botão "↩️ Desfazer". Quando a feira tem mais de um
tamanho, mostra também botões pra trocar o tamanho da venda (callback `vmove`).
"""

import os

from . import feira, gemini, telegram_client as tg


def _sid() -> str:
    return os.environ["SPREADSHEET_ID"]


def _esc(s) -> str:
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _fmt_qtd(n) -> str:
    if n is None:
        return "?"
    n = float(n)
    return str(int(n)) if n == int(n) else f"{n:g}".replace(".", ",")


def _produtos_resumo(produtos: list) -> str:
    parts = []
    for p in produtos:
        t = p.get("tamanho", "padrão")
        q = p.get("qtd_levada")
        pr = p.get("preco")
        seg = t
        if q not in (None, ""):
            seg += f" ({_fmt_qtd(q)} un)"
        if pr not in (None, ""):
            seg += f" a R$ {float(pr):.2f}"
        parts.append(seg)
    return " · ".join(parts)


# ============================================================================
# Estado
# ============================================================================

def has_active_feira(chat_id: int) -> bool:
    return feira.get_active_feira(_sid(), chat_id) is not None


# kept for the webhook's import name
def has_open_feira(chat_id: int) -> bool:
    return has_active_feira(chat_id)


# ============================================================================
# Abertura
# ============================================================================

def try_open_from_text(chat_id: int, text: str) -> bool:
    """Try to open a feira from a free-text message. Returns True if consumed."""
    if has_active_feira(chat_id):
        return False
    if "feira" not in text.lower():
        return False
    try:
        parsed = gemini.parse_feira_opening(text)
    except Exception:
        return False
    if not parsed.get("is_abertura"):
        return False
    return _start_opening(chat_id, parsed)


def open_via_command(chat_id: int, args: str) -> None:
    """/feira [descrição livre] — opens (or drafts) a feira from the args."""
    if has_active_feira(chat_id):
        f = feira.get_active_feira(_sid(), chat_id)
        if f["status"] == "rascunho":
            _ask_missing(chat_id, f)
        else:
            tg.send_message(
                chat_id,
                f"⚠️ Já tem uma feira aberta (<b>{f['id']}</b>). "
                f"Manda /fechar pra encerrar antes de abrir outra, ou /feira_status pro parcial.",
            )
        return
    parsed = {}
    if args.strip():
        try:
            parsed = gemini.parse_feira_opening(args)
        except Exception:
            parsed = {}
    if not parsed.get("produtos"):
        tg.send_message(
            chat_id,
            "🎪 <b>Abrir feira</b>\n\n"
            "Me conta quantos pudins de cada tamanho você tá levando e por quanto. Ex:\n"
            "<i>saindo pra feira, 63 de 200g a R$18 e 4 de 500g a R$45</i>\n\n"
            "Pode mandar por texto ou áudio. Se faltar o preço, eu pergunto depois.",
        )
        return
    _start_opening(chat_id, parsed)


def _start_opening(chat_id: int, parsed: dict) -> bool:
    """Create the feira (aberta if complete, rascunho if prices missing)."""
    produtos = _clean_produtos(parsed.get("produtos") or [])
    descricao = parsed.get("descricao") or ""
    if not produtos:
        tg.send_message(
            chat_id,
            "🎪 Me diz quantos pudins (e de que tamanho) você tá levando. Ex:\n"
            "<i>63 de 200g e 4 de 500g</i>",
        )
        return True
    if feira.produtos_completos(produtos):
        feira_id = feira.create_feira(_sid(), chat_id, produtos, status="aberta", descricao=descricao)
        _send_aberta(chat_id, feira_id, produtos, descricao)
    else:
        feira_id = feira.create_feira(_sid(), chat_id, produtos, status="rascunho", descricao=descricao)
        f = {"id": feira_id, "produtos": produtos, "status": "rascunho"}
        _ask_missing(chat_id, f)
    return True


def _complete_draft(chat_id: int, f: dict, text: str) -> bool:
    """A rascunho exists — interpret the message as more opening info (prices/qtys)."""
    try:
        parsed = gemini.parse_feira_opening(text)
    except Exception:
        parsed = {}
    novos = _clean_produtos(parsed.get("produtos") or [])
    if not novos:
        _ask_missing(chat_id, f)
        return True
    merged = _merge_produtos(f["produtos"], novos)
    if feira.produtos_completos(merged):
        feira.update_feira_produtos(_sid(), f["id"], merged, status="aberta")
        _send_aberta(chat_id, f["id"], merged, f.get("descricao", ""))
    else:
        feira.update_feira_produtos(_sid(), f["id"], merged)
        f = {**f, "produtos": merged}
        _ask_missing(chat_id, f)
    return True


def _ask_missing(chat_id: int, f: dict) -> None:
    faltando = feira.produtos_missing_preco(f["produtos"])
    tamanhos = ", ".join(p.get("tamanho", "padrão") for p in faltando)
    tg.send_message(
        chat_id,
        f"🎪 Anotei: <b>{_produtos_resumo(f['produtos'])}</b>.\n\n"
        f"Só falta o <b>preço</b> de: <b>{tamanhos}</b>.\n"
        f"Manda assim: <i>18 o de 200g e 45 o de 500g</i>.",
    )


def _send_aberta(chat_id: int, feira_id: str, produtos: list, descricao: str) -> None:
    desc_line = f"\n📍 {_esc(descricao)}" if descricao else ""
    tg.send_message(
        chat_id,
        f"🎪 <b>Feira aberta!</b> ({feira_id}){desc_line}\n"
        f"Levando: <b>{_produtos_resumo(produtos)}</b>.\n\n"
        f"Agora é só ir avisando as vendas — texto, áudio ou foto. Ex:\n"
        f"• <i>vendi 2 de 200g pro fulano</i>\n"
        f"• <i>vendi 1 de 500g no pix</i>\n"
        f"• <i>vendi 2 agora</i> (sem nome)\n"
        f"• <i>vendi 2, a maria vai voltar pra pagar</i> (fiado)\n\n"
        f"Se não falar o tamanho, eu assumo o principal e você troca num toque.\n"
        f"No fim: /fechar.",
    )


# ============================================================================
# Mensagens durante a feira
# ============================================================================

def handle_text(chat_id: int, text: str) -> bool:
    f = feira.get_active_feira(_sid(), chat_id)
    if not f:
        return False
    if f["status"] == "rascunho":
        return _complete_draft(chat_id, f, text)
    try:
        parsed = gemini.parse_feira_message(text, produtos=f["produtos"])
    except Exception as e:
        tg.send_message(chat_id, f"❌ Não consegui interpretar: <code>{_esc(e)}</code>")
        return True
    return _dispatch(chat_id, f, parsed)


def handle_image(chat_id: int, image_bytes: bytes) -> bool:
    f = feira.get_active_feira(_sid(), chat_id)
    if not f:
        return False
    if f["status"] == "rascunho":
        tg.send_message(chat_id, "🎪 Primeiro me manda os preços pra abrir a feira (ex: <i>18 o de 200g e 45 o de 500g</i>).")
        return True
    try:
        parsed = gemini.parse_feira_image(image_bytes, produtos=f["produtos"])
    except Exception as e:
        # Comum durante feira aberta: usuário manda foto de NF-e/comprovante
        # de compra ao invés de anotação de venda; Gemini não classifica em
        # nenhum intent e o parse falha. Ao invés de mostrar exceção crua,
        # oferecer opção de registrar como compra.
        print(f"feira_flow.handle_image: parse_feira_image falhou: {e}")
        tg.send_message(
            chat_id,
            "🤔 Não entendi essa imagem no contexto da feira. Se for anotação de venda, "
            "manda como texto (ex: <i>vendi 2 de 200g</i>). Se for uma nota fiscal, "
            "encerra a feira com /fechar e reenvia a foto — aí ela vira compra.",
        )
        return True
    return _dispatch(chat_id, f, parsed)


def _dispatch(chat_id: int, f: dict, parsed: dict) -> bool:
    intent = (parsed or {}).get("intent", "outro")
    if intent == "venda":
        return _register_venda(chat_id, f, parsed)
    if intent == "fechamento":
        return _handle_fechamento(chat_id, f, parsed)
    if intent == "status":
        send_status(chat_id, f)
        return True
    tg.send_message(
        chat_id,
        "🤔 Não entendi se foi uma venda. Tenta: <i>vendi 2 de 200g pro fulano</i>.\n"
        "Se for uma nota fiscal, encerra com /fechar e reenvia.\n"
        "Parcial: /feira_status · encerrar: /fechar",
    )
    return True


def _register_venda(chat_id: int, f: dict, parsed: dict) -> bool:
    qtde = parsed.get("qtde")
    if not qtde or float(qtde) <= 0:
        tg.send_message(chat_id, "🤔 Quantos pudins foram? Ex: <i>vendi 2 de 200g pro fulano</i>.")
        return True
    qtde = float(qtde)

    produtos = f["produtos"]
    tam_req = parsed.get("tamanho") or ""
    prod = feira.find_produto(produtos, tam_req) if tam_req else None
    assumed = False
    if not prod:
        prod = feira.produto_principal(produtos)
        assumed = bool(tam_req) or len(produtos) > 1
    tamanho = feira.norm_tamanho(prod.get("tamanho")) if prod else feira.norm_tamanho(tam_req)
    preco_unit = parsed.get("preco_unit") or (prod.get("preco") if prod else None) or 0
    preco_unit = float(preco_unit)

    cliente = (parsed.get("cliente_nome") or "").strip()
    pago = parsed.get("pago", True)
    forma = (parsed.get("forma_pagamento") or "").strip().lower()
    if forma not in ("dinheiro", "pix"):
        forma = ""
    status_pgto = "pago" if pago else "fiado"
    if not pago:
        forma = ""
    notas = (parsed.get("notas") or "").strip()

    ven_id, venda = feira.append_venda(
        _sid(), f["id"], qtde=qtde, preco_unit=preco_unit, tamanho=tamanho,
        cliente_nome=cliente, forma_pagamento=forma,
        status_pagamento=status_pgto, notas=notas,
    )

    total = venda["preco_total"]
    quem = _esc(cliente) if cliente else "<i>sem nome</i>"
    if status_pgto == "fiado":
        pgto_str = "🔴 <b>FIADO</b>"
    elif forma == "dinheiro":
        pgto_str = "💵 dinheiro"
    elif forma == "pix":
        pgto_str = "📲 pix"
    else:
        pgto_str = "✅ pago"
    assume_str = " <i>(assumi esse tamanho)</i>" if assumed else ""

    buttons = [[{"text": "↩️ Desfazer", "callback_data": f"vundo:{ven_id}"}]]
    # quick-switch buttons for the other sizes
    outros = [p for p in produtos if feira.norm_tamanho(p.get("tamanho")) != tamanho]
    if outros:
        row = []
        for p in outros:
            t = feira.norm_tamanho(p.get("tamanho"))
            pr = p.get("preco")
            label = f"↔️ Era {t}" + (f" (R${float(pr):.0f})" if pr else "")
            row.append({"text": label, "callback_data": f"vmove:{ven_id}:{t}"})
        buttons.append(row)

    tg.send_message_with_buttons(
        chat_id,
        f"✅ <b>{_fmt_qtd(qtde)}× {tamanho}</b>{assume_str} → {quem} · "
        f"R$ {total:.2f} · {pgto_str}",
        buttons,
    )
    return True


def _handle_fechamento(chat_id: int, f: dict, parsed: dict) -> bool:
    voltou_list = parsed.get("voltou") or []
    voltou = {}
    for item in voltou_list:
        t = feira.norm_tamanho(item.get("tamanho"))
        q = item.get("qtde")
        if q is not None:
            voltou[t] = float(q)
    din = parsed.get("dinheiro")
    pix = parsed.get("pix")
    if voltou or din is not None or pix is not None:
        feira.update_closing(
            _sid(), f["id"],
            voltou=voltou or None,
            dinheiro=float(din) if din is not None else None,
            pix=float(pix) if pix is not None else None,
        )
        f = feira.get_active_feira(_sid(), chat_id) or f

    vendas = feira.get_vendas(_sid(), f["id"])
    bal = feira.compute_balanco(f, vendas)
    tg.send_message_with_buttons(
        chat_id,
        _format_balanco(f, bal, parcial=True) + "\n\nConfere os números. Quando tiver certo, encerra.",
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
    f = feira.get_active_feira(_sid(), chat_id)
    if not f:
        tg.send_message(chat_id, "Nenhuma feira aberta. Abre uma com /feira.")
        return
    if f["status"] == "rascunho":
        _ask_missing(chat_id, f)
        return
    send_status(chat_id, f)


def send_status(chat_id: int, f: dict) -> None:
    vendas = feira.get_vendas(_sid(), f["id"])
    bal = feira.compute_balanco(f, vendas)
    tg.send_message(chat_id, _format_balanco(f, bal, parcial=True))


def close_command(chat_id: int) -> None:
    f = feira.get_active_feira(_sid(), chat_id)
    if not f:
        tg.send_message(chat_id, "Nenhuma feira aberta pra fechar.")
        return
    if f["status"] == "rascunho":
        tg.send_message(chat_id, "Essa feira nem abriu ainda. Manda os preços, ou /cancel pra descartar.")
        return
    vendas = feira.get_vendas(_sid(), f["id"])
    bal = feira.compute_balanco(f, vendas)
    falta = []
    if any(p["voltou"] is None and p["qtd_levada"] for p in bal["produtos"]):
        falta.append("quantos pudins voltaram de cada tamanho")
    if bal["recebido_informado"] is None:
        falta.append("quanto recebeu em dinheiro e no pix")
    falta_line = ""
    if falta:
        falta_line = (
            "\n\n💡 Pra conferir o caixa, me diz " + " e ".join(falta) +
            " (ex: <i>voltaram 5 de 200g e 1 de 500g, recebi 200 no dinheiro e 150 no pix</i>)."
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
    f = feira.get_active_feira(_sid(), chat_id)
    if not f:
        return False
    feira.cancel_feira(_sid(), f["id"])
    tg.send_message(chat_id, f"🚫 Feira {f['id']} cancelada (vendas já registradas ficam na planilha).")
    return True


# ============================================================================
# Callbacks
# ============================================================================

def handle_callback(chat_id: int, message_id: int, parts: list, callback_query_id: str) -> bool:
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
    if action == "vmove":
        ven_id, tamanho = parts[1], parts[2]
        f = feira.get_active_feira(_sid(), chat_id)
        prod = feira.find_produto(f["produtos"], tamanho) if f else None
        preco = float(prod["preco"]) if prod and prod.get("preco") else 0.0
        v = feira.move_venda(_sid(), ven_id, tamanho, preco)
        tg.answer_callback_query(callback_query_id, "Trocado" if v else "Não achei a venda")
        if v:
            buttons = [[{"text": "↩️ Desfazer", "callback_data": f"vundo:{ven_id}"}]]
            outros = [p for p in (f["produtos"] if f else []) if feira.norm_tamanho(p.get("tamanho")) != tamanho]
            if outros:
                row = []
                for p in outros:
                    t = feira.norm_tamanho(p.get("tamanho"))
                    pr = p.get("preco")
                    label = f"↔️ Era {t}" + (f" (R${float(pr):.0f})" if pr else "")
                    row.append({"text": label, "callback_data": f"vmove:{ven_id}:{t}"})
                buttons.append(row)
            quem = _esc(v["cliente_nome"]) if v["cliente_nome"] else "<i>sem nome</i>"
            tg.edit_message_text(
                chat_id, message_id,
                f"✅ <b>{_fmt_qtd(v['qtde'])}× {tamanho}</b> → {quem} · R$ {v['preco_total']:.2f}",
                reply_markup={"inline_keyboard": buttons},
            )
        return True
    if action == "vcont":
        tg.answer_callback_query(callback_query_id, "")
        tg.edit_message_text(chat_id, message_id, "👍 Bora continuar vendendo!", reply_markup=None)
        return True
    if action == "vfecha":
        feira_id = parts[1]
        tg.answer_callback_query(callback_query_id, "")
        f = feira.get_active_feira(_sid(), chat_id)
        if not f or f["id"] != feira_id or f["status"] != "aberta":
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
# Helpers de produto + balanço
# ============================================================================

def _clean_produtos(produtos: list) -> list:
    """Normalize tamanho and coerce qtd/preco to float|None."""
    out = []
    for p in produtos:
        if not isinstance(p, dict):
            continue
        q = p.get("qtd_levada")
        pr = p.get("preco")
        out.append({
            "tamanho": feira.norm_tamanho(p.get("tamanho")),
            "qtd_levada": float(q) if q not in (None, "") else None,
            "preco": float(pr) if pr not in (None, "") else None,
        })
    return out


def _merge_produtos(base: list, novos: list) -> list:
    """Fill missing qtd/preco in `base` from `novos`, matching by tamanho; add new sizes."""
    by_tam = {feira.norm_tamanho(p["tamanho"]): dict(p) for p in base}
    for n in novos:
        t = feira.norm_tamanho(n["tamanho"])
        if t in by_tam:
            if by_tam[t].get("qtd_levada") in (None, "") and n.get("qtd_levada") not in (None, ""):
                by_tam[t]["qtd_levada"] = n["qtd_levada"]
            if by_tam[t].get("preco") in (None, "") and n.get("preco") not in (None, ""):
                by_tam[t]["preco"] = n["preco"]
        else:
            by_tam[t] = dict(n)
    return list(by_tam.values())


def _format_balanco(f: dict, bal: dict, parcial: bool) -> str:
    titulo = "📊 <b>Parcial da feira</b>" if parcial else "📊 <b>Balanço final</b>"
    lines = [f"{titulo} ({f['id']})", ""]

    lines.append("<b>Pudins:</b>")
    for p in bal["produtos"]:
        seg = f"   {p['tamanho']}: vendeu <b>{_fmt_qtd(p['vendido'])}</b>"
        if p["qtd_levada"] is not None:
            seg = f"   {p['tamanho']}: levou {_fmt_qtd(p['qtd_levada'])} · vendeu <b>{_fmt_qtd(p['vendido'])}</b>"
        if p["voltou"] is not None:
            seg += f" · voltou {_fmt_qtd(p['voltou'])}"
        lines.append(seg)
        if p["nao_contabilizada"] is not None and abs(p["nao_contabilizada"]) >= 0.01:
            n = p["nao_contabilizada"]
            if n > 0:
                lines.append(f"      ⚠️ {_fmt_qtd(n)} não batem (brinde, perda ou venda não anotada?)")
            else:
                lines.append(f"      ⚠️ {_fmt_qtd(-n)} a mais que o levado — confere a qtde.")

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
            tam = f" {fi['tamanho']}" if fi["tamanho"] else ""
            lines.append(f"   • {_esc(fi['nome'])} — {_fmt_qtd(fi['qtde'])}×{tam} · R$ {fi['valor']:.2f}")

    if bal["recebido_informado"] is not None:
        lines.append("")
        lines.append(f"🧾 Você informou ter recebido: R$ {bal['recebido_informado']:.2f}")
        d = bal["divergencia_caixa"]
        if abs(d) < 0.01:
            lines.append("   ✅ Bate com o pago registrado.")
        elif d > 0:
            lines.append(f"   ⚠️ R$ {d:.2f} a mais que o registrado como pago.")
        else:
            lines.append(f"   ⚠️ Faltam R$ {-d:.2f} em relação ao registrado como pago.")

    return "\n".join(lines)
