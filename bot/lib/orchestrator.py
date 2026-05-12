"""
Orchestrator: photo → parse → match → interactive resolution → write to Sheets.

Interactive flow:
1. Photo arrives → Gemini parses → matcher enriches
2. If fornecedor doesn't match, ask: [Use sugestão] [Criar novo] [Cancelar]
3. For each unmatched item, ask: [Use sugestão] [Criar novo] [Pular]
4. After all resolved, write to Compras and confirm

State is kept in the hidden _BotState tab. Keys we use in the state dict:
- "fornecedor", "data", "total", "itens", "observacoes"  (raw from Gemini)
- "fornecedor_match" (best match or None)
- "step": "review_supplier" | "review_item" | "ready_save" | "done"
- "current_item_index": index of the item currently being reviewed
- "resolved_supplier_id": final FORN-NNN to use
- "items_resolved": list parallel to "itens" with {"action": "use"|"create"|"skip", "produto_id": "..."}
"""

import os
from datetime import datetime
from . import gemini, sheets, matcher, state, aliases, telegram_client as tg


SPREADSHEET_ID = None


def _spreadsheet_id() -> str:
    global SPREADSHEET_ID
    if SPREADSHEET_ID is None:
        SPREADSHEET_ID = os.environ["SPREADSHEET_ID"]
    return SPREADSHEET_ID


def _esc(s) -> str:
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


CONFIDENCE_EMOJI = {"alta": "✅", "media": "⚠️", "baixa": "❓"}


# ============================================================================
# Photo handler — entrypoint
# ============================================================================

def handle_photo(chat_id: int, file_id: str, image_bytes: bytes) -> None:
    tg.send_message(chat_id, "📸 Recebi a nota, processando...")

    try:
        receipt = gemini.parse_receipt(image_bytes)
    except Exception as e:
        tg.send_message(chat_id, f"❌ Erro ao processar a imagem: <code>{_esc(e)}</code>")
        return

    service = sheets.get_service()
    produtos = sheets.get_produtos(_spreadsheet_id(), service=service)
    fornecedores = sheets.get_fornecedores(_spreadsheet_id(), service=service)

    enriched = matcher.enrich_receipt(receipt, produtos, fornecedores)

    # Apply alias memory BEFORE fuzzy match consideration:
    # if there's a saved alias for this exact text, use it (auto-resolve)
    sup_alias_id = aliases.check(_spreadsheet_id(), "FORNECEDOR", enriched.get("fornecedor", ""), service=service)
    if sup_alias_id:
        # Validate the alias still points to an existing fornecedor
        forn = next((f for f in fornecedores if f["id"] == sup_alias_id), None)
        if forn:
            enriched["fornecedor_match"] = {**forn, "match_score": 100, "match_confidence": "alta", "from_alias": True}

    for item in enriched.get("itens", []):
        item_alias_id = aliases.check(_spreadsheet_id(), "PRODUTO", item.get("descricao", ""), service=service)
        if item_alias_id == "SKIP":
            item["alias_skip"] = True
        elif item_alias_id:
            prod = next((p for p in produtos if p["id"] == item_alias_id), None)
            if prod:
                item["produto_match"] = {**prod, "match_score": 100, "match_confidence": "alta", "from_alias": True}

    # Initialize state
    enriched["step"] = "review_supplier"
    enriched["current_item_index"] = 0
    enriched["resolved_supplier_id"] = None
    enriched["items_resolved"] = [None] * len(enriched.get("itens", []))

    state_id = state.save_state(_spreadsheet_id(), enriched, chat_id=chat_id, service=service)

    # Send overview first
    tg.send_message(chat_id, _format_overview(enriched))

    # Start interactive flow
    _next_step(chat_id, state_id, enriched, service=service)


# ============================================================================
# Callback handler — dispatch button clicks
# ============================================================================

def handle_callback(chat_id: int, message_id: int, callback_data: str, callback_query_id: str) -> None:
    parts = callback_data.split(":")
    action = parts[0]
    state_id = parts[1] if len(parts) > 1 else ""

    service = sheets.get_service()
    payload = state.load_state(_spreadsheet_id(), state_id, service=service)

    if not payload:
        tg.answer_callback_query(callback_query_id, "Esta confirmação já não está válida.")
        tg.edit_message_text(chat_id, message_id, "⏱ Esta confirmação não está mais válida.", reply_markup=None)
        return

    if action == "cancel":
        state.delete_state(_spreadsheet_id(), state_id, service=service)
        tg.answer_callback_query(callback_query_id, "Cancelado")
        tg.edit_message_text(chat_id, message_id, "❌ Cancelado, nada foi salvo.", reply_markup=None)
        return

    tg.answer_callback_query(callback_query_id, "")

    # Supplier decisions
    if action == "fuse":  # fornecedor: use suggestion
        forn_id = payload["fornecedor_match"]["id"]
        payload["resolved_supplier_id"] = forn_id
        # Save alias for future auto-match (unless it came from an alias already)
        learned = ""
        if not payload["fornecedor_match"].get("from_alias"):
            saved = aliases.save(_spreadsheet_id(), "FORNECEDOR", payload.get("fornecedor", ""), forn_id, service=service)
            if saved:
                learned = "\n📚 <i>Aprendi: dessa nota em diante, esse texto vira esse fornecedor automaticamente.</i>"
        tg.edit_message_text(
            chat_id, message_id,
            f"✓ Fornecedor: <b>{_esc(payload['fornecedor_match']['nome'])}</b>{learned}",
            reply_markup=None,
        )
    elif action == "fcreate":  # fornecedor: create new
        nome = payload.get("fornecedor", "DESCONHECIDO")
        new_id = sheets.create_fornecedor(_spreadsheet_id(), nome, service=service)
        payload["resolved_supplier_id"] = new_id
        aliases.save(_spreadsheet_id(), "FORNECEDOR", nome, new_id, service=service)
        tg.edit_message_text(
            chat_id, message_id,
            f"✓ Criei fornecedor <b>{new_id}</b> — {_esc(nome)}\n"
            f"📚 <i>Aprendi: dessa nota em diante, esse texto vira esse fornecedor.</i>",
            reply_markup=None,
        )
    elif action == "iuse":  # item: use suggestion
        idx = int(parts[2])
        item = payload["itens"][idx]
        produto_id = item["produto_match"]["id"]
        payload["items_resolved"][idx] = {"action": "use", "produto_id": produto_id}
        learned = ""
        if not item["produto_match"].get("from_alias"):
            saved = aliases.save(_spreadsheet_id(), "PRODUTO", item.get("descricao", ""), produto_id, service=service)
            if saved:
                learned = "\n📚 <i>Aprendi essa associação.</i>"
        tg.edit_message_text(
            chat_id, message_id,
            f"✓ Item {idx+1}: <b>{_esc(item['produto_match']['nome'])}</b>{learned}",
            reply_markup=None,
        )
    elif action == "icreate":  # item: create new product
        # callback_data: icreate:state_id:idx[:categoria]
        idx = int(parts[2])
        item = payload["itens"][idx]
        # Use explicit categoria from callback if present, else from Gemini, else default ALI
        if len(parts) > 3 and parts[3] in ("ALI", "FOR", "EMB", "EQP", "OPR"):
            categoria = parts[3]
        else:
            categoria = item.get("categoria") or "ALI"
            if categoria == "OUTRO":
                categoria = "ALI"  # safe fallback if user didn't disambiguate
        unidade = "UN"
        nome = item.get("descricao", "?")
        marca = item.get("marca")
        full_nome = f"{nome} ({marca})" if marca else nome
        new_id = sheets.create_produto(
            _spreadsheet_id(), full_nome, categoria, unidade=unidade, service=service
        )
        payload["items_resolved"][idx] = {"action": "create", "produto_id": new_id}
        aliases.save(_spreadsheet_id(), "PRODUTO", item.get("descricao", ""), new_id, service=service)
        tg.edit_message_text(
            chat_id, message_id,
            f"✓ Criei produto <b>{new_id}</b> — {_esc(full_nome)}\n"
            f"📚 <i>Aprendi essa associação.</i>",
            reply_markup=None,
        )
    elif action == "iskip":  # item: don't add
        idx = int(parts[2])
        item = payload["itens"][idx]
        payload["items_resolved"][idx] = {"action": "skip"}
        # Learn the skip so future receipts with same text auto-ignore
        saved = aliases.save(_spreadsheet_id(), "PRODUTO", item.get("descricao", ""), "SKIP", service=service)
        learned = "\n📚 <i>Aprendi: dessa nota em diante esse item é auto-ignorado.</i>" if saved else ""
        tg.edit_message_text(
            chat_id, message_id,
            f"⏭ Item {idx+1} ignorado: <i>{_esc(item.get('descricao', '?'))}</i>{learned}",
            reply_markup=None,
        )
    elif action == "save":  # final save
        _finalize(chat_id, message_id, payload, state_id, service=service)
        return
    else:
        return

    # Persist updated state and proceed
    state.delete_state(_spreadsheet_id(), state_id, service=service)
    new_state_id = state.save_state(_spreadsheet_id(), payload, chat_id=chat_id, service=service)
    _next_step(chat_id, new_state_id, payload, service=service)


# ============================================================================
# Step machine
# ============================================================================

def _next_step(chat_id: int, state_id: str, payload: dict, service=None) -> None:
    """Send the next prompt based on current state."""
    # 1. Resolve supplier
    if payload.get("resolved_supplier_id") is None:
        # Auto-resolve if we have an alias-backed match (100% confidence, learned previously)
        forn_match = payload.get("fornecedor_match")
        if forn_match and forn_match.get("from_alias"):
            payload["resolved_supplier_id"] = forn_match["id"]
            tg.send_message(
                chat_id,
                f"🤖 Fornecedor reconhecido automaticamente: <b>{_esc(forn_match['nome'])}</b> (via memória)",
            )
            state.delete_state(_spreadsheet_id(), state_id, service=service)
            new_id = state.save_state(_spreadsheet_id(), payload, chat_id=chat_id, service=service)
            _next_step(chat_id, new_id, payload, service=service)
            return
        _ask_supplier(chat_id, state_id, payload)
        return

    # 2. Resolve each item
    itens = payload.get("itens", [])
    resolved = payload.get("items_resolved", [])
    for idx, item in enumerate(itens):
        if resolved[idx] is None:
            prod = item.get("produto_match")

            # Alias-backed SKIP — user previously trained this text to be ignored
            if item.get("alias_skip"):
                payload["items_resolved"][idx] = {"action": "skip", "reason": "alias_skip"}
                tg.send_message(
                    chat_id,
                    f"🤖 Item {idx+1} ignorado: <i>{_esc(item.get('descricao', '?'))}</i> (via memória)",
                )
                state.delete_state(_spreadsheet_id(), state_id, service=service)
                new_id = state.save_state(_spreadsheet_id(), payload, chat_id=chat_id, service=service)
                _next_step(chat_id, new_id, payload, service=service)
                return

            # Alias-backed PRODUTO — auto-use the learned mapping
            if prod and prod.get("from_alias"):
                payload["items_resolved"][idx] = {"action": "use", "produto_id": prod["id"]}
                tg.send_message(
                    chat_id,
                    f"🤖 Item {idx+1} reconhecido: <b>{_esc(prod['nome'])}</b> (via memória)",
                )
                state.delete_state(_spreadsheet_id(), state_id, service=service)
                new_id = state.save_state(_spreadsheet_id(), payload, chat_id=chat_id, service=service)
                _next_step(chat_id, new_id, payload, service=service)
                return

            # Auto-resolve high-confidence fuzzy match
            if prod and prod.get("match_confidence") == "alta":
                payload["items_resolved"][idx] = {"action": "use", "produto_id": prod["id"]}
                state.delete_state(_spreadsheet_id(), state_id, service=service)
                new_id = state.save_state(_spreadsheet_id(), payload, chat_id=chat_id, service=service)
                _next_step(chat_id, new_id, payload, service=service)
                return

            _ask_item(chat_id, state_id, payload, idx)
            return

    # 3. All resolved — show final save button
    _ask_final(chat_id, state_id, payload)


def _ask_supplier(chat_id: int, state_id: str, payload: dict) -> None:
    forn_match = payload.get("fornecedor_match")
    raw_name = payload.get("fornecedor", "?")

    if forn_match:
        text = (
            f"🏪 <b>Fornecedor</b>\n"
            f"Nota diz: <code>{_esc(raw_name)}</code>\n"
            f"Sugestão ({forn_match.get('match_score', 0):.0f}% confiança): "
            f"<b>{_esc(forn_match['id'])} — {_esc(forn_match['nome'])}</b>\n\n"
            f"O que faço?"
        )
        buttons = [
            [{"text": f"✓ Usar {forn_match['id']}", "callback_data": f"fuse:{state_id}"}],
            [{"text": "➕ Criar novo", "callback_data": f"fcreate:{state_id}"}],
            [{"text": "❌ Cancelar tudo", "callback_data": f"cancel:{state_id}"}],
        ]
    else:
        text = (
            f"🏪 <b>Fornecedor não reconhecido</b>\n"
            f"Nota diz: <code>{_esc(raw_name)}</code>\n\n"
            f"Crio um novo fornecedor com esse nome?"
        )
        buttons = [
            [{"text": "➕ Criar novo", "callback_data": f"fcreate:{state_id}"}],
            [{"text": "❌ Cancelar tudo", "callback_data": f"cancel:{state_id}"}],
        ]

    tg.send_message_with_buttons(chat_id, text, buttons)


CATEGORIA_LABEL = {
    "ALI": "🍯 Alimento (entra na receita)",
    "FOR": "🥣 Forma",
    "EMB": "📦 Embalagem",
    "EQP": "🔧 Equipamento (durável)",
    "OPR": "🧻 Operacional (papel toalha, palito, etc.)",
}


def _ask_item(chat_id: int, state_id: str, payload: dict, idx: int) -> None:
    item = payload["itens"][idx]
    prod = item.get("produto_match")
    desc = item.get("descricao", "?")
    marca = item.get("marca")
    categoria = item.get("categoria", "?")
    qtd_e = item.get("qtde_embalagens", 1)
    unid_e = item.get("unidades_por_embalagem", 1)
    preco = item.get("preco_total", 0)
    marca_str = f" • {_esc(marca)}" if marca else ""
    is_outro = categoria == "OUTRO"

    cat_hint = "🤔 <i>Parece não ser insumo do negócio</i>\n" if is_outro else ""
    info = (
        f"📦 <b>Item {idx + 1}/{len(payload['itens'])}</b>\n"
        f"<code>{_esc(desc)}</code>{marca_str}\n"
        f"{cat_hint}"
        f"Categoria sugerida: <b>{_esc(categoria)}</b> · {qtd_e}×{unid_e} unid · R$ {preco:.2f}"
    )

    if prod:
        text = (
            f"{info}\n\n"
            f"Sugestão ({prod.get('match_score', 0):.0f}%): "
            f"<b>{_esc(prod['id'])} — {_esc(prod['nome'])}</b>\n\n"
            f"O que faço?"
        )
        buttons = [
            [{"text": f"✓ Usar {prod['id']}", "callback_data": f"iuse:{state_id}:{idx}"}],
            [{"text": "➕ Criar novo produto", "callback_data": f"icreate:{state_id}:{idx}"}],
            [{"text": "⏭ Pular este item", "callback_data": f"iskip:{state_id}:{idx}"}],
            [{"text": "❌ Cancelar tudo", "callback_data": f"cancel:{state_id}"}],
        ]
        tg.send_message_with_buttons(chat_id, text, buttons)
        return

    # No fuzzy match.
    # For OUTRO: default is skip but offer to cadastrar with explicit categoria choice
    if is_outro:
        text = (
            f"{info}\n\n"
            f"Quer ignorar (default) ou cadastrar como produto?"
        )
        buttons = [
            [{"text": "⏭ Pular (default)", "callback_data": f"iskip:{state_id}:{idx}"}],
            [{"text": f"➕ Cadastrar como {CATEGORIA_LABEL['ALI']}", "callback_data": f"icreate:{state_id}:{idx}:ALI"}],
            [{"text": f"➕ Cadastrar como {CATEGORIA_LABEL['EMB']}", "callback_data": f"icreate:{state_id}:{idx}:EMB"}],
            [{"text": f"➕ Cadastrar como {CATEGORIA_LABEL['EQP']}", "callback_data": f"icreate:{state_id}:{idx}:EQP"}],
            [{"text": f"➕ Cadastrar como {CATEGORIA_LABEL['OPR']}", "callback_data": f"icreate:{state_id}:{idx}:OPR"}],
            [{"text": "❌ Cancelar tudo", "callback_data": f"cancel:{state_id}"}],
        ]
        tg.send_message_with_buttons(chat_id, text, buttons)
        return

    # Other categorias: just use the Gemini-suggested categoria when cadastrando
    text = f"{info}\n\nNão achei produto parecido cadastrado. O que faço?"
    buttons = [
        [{"text": f"➕ Cadastrar como {categoria}", "callback_data": f"icreate:{state_id}:{idx}"}],
        [{"text": "⏭ Pular este item", "callback_data": f"iskip:{state_id}:{idx}"}],
        [{"text": "❌ Cancelar tudo", "callback_data": f"cancel:{state_id}"}],
    ]
    tg.send_message_with_buttons(chat_id, text, buttons)


def _ask_final(chat_id: int, state_id: str, payload: dict) -> None:
    forn_id = payload["resolved_supplier_id"]
    forn_name = _resolve_forn_name(forn_id)
    itens = payload.get("itens", [])
    resolved = payload.get("items_resolved", [])

    included = []
    skipped_outro = []
    skipped_manual = []
    for idx, item in enumerate(itens):
        r = resolved[idx]
        desc = _esc(item.get("descricao", "?"))
        preco = item.get("preco_total", 0)
        if not r or r["action"] == "skip":
            line = f"  <s>{desc}</s> — R$ {preco:.2f}"
            if r and r.get("reason") == "outro":
                skipped_outro.append(line)
            else:
                skipped_manual.append(line)
        else:
            included.append(f"  ✓ {desc} → {r['produto_id']} — R$ {preco:.2f}")

    lines = [
        f"📝 <b>Pronto pra salvar?</b>",
        f"Fornecedor: <b>{_esc(forn_name)}</b>",
        f"Data: {_esc(payload.get('data') or 'hoje')}",
    ]
    if included:
        lines += ["", f"<b>Vou adicionar ({len(included)}):</b>"] + included
    if skipped_outro:
        lines += ["", f"<b>Ignorados (não-insumos, {len(skipped_outro)}):</b>"] + skipped_outro
    if skipped_manual:
        lines += ["", f"<b>Pulados ({len(skipped_manual)}):</b>"] + skipped_manual

    buttons = [
        [{"text": f"💾 Salvar {len(included)} compra(s)", "callback_data": f"save:{state_id}"}],
        [{"text": "❌ Cancelar", "callback_data": f"cancel:{state_id}"}],
    ]
    tg.send_message_with_buttons(chat_id, "\n".join(lines), buttons)


def _finalize(chat_id: int, message_id: int, payload: dict, state_id: str, service=None) -> None:
    service = service or sheets.get_service()
    forn_id = payload["resolved_supplier_id"]
    data = payload.get("data") or datetime.now().strftime("%Y-%m-%d")
    itens = payload.get("itens", [])
    resolved = payload.get("items_resolved", [])

    added = []
    for idx, item in enumerate(itens):
        r = resolved[idx]
        if not r or r["action"] == "skip":
            continue
        compra_id = sheets.append_compra(
            spreadsheet_id=_spreadsheet_id(),
            data=data,
            produto_id=r["produto_id"],
            fornecedor_id=forn_id,
            marca=item.get("marca") or "",
            qtde_embalagens=item.get("qtde_embalagens", 1),
            unidades_por_embalagem=item.get("unidades_por_embalagem", 1),
            preco_total=item.get("preco_total", 0),
            notas=f"Via bot — {payload.get('observacoes', '')}".strip(" —"),
            service=service,
        )
        added.append(compra_id)

    state.delete_state(_spreadsheet_id(), state_id, service=service)

    msg = f"✅ Adicionei {len(added)} compra(s):\n" + "\n".join(f"• {c}" for c in added)
    tg.edit_message_text(chat_id, message_id, msg, reply_markup=None)


# ============================================================================
# Helpers
# ============================================================================

def _format_overview(receipt: dict) -> str:
    forn = receipt.get("fornecedor_match")
    if forn:
        forn_line = f"<b>Fornecedor:</b> {_esc(forn['id'])} — {_esc(forn['nome'])} ({forn.get('match_score', 0):.0f}%)"
    else:
        forn_line = f"<b>Fornecedor:</b> ⚠️ <code>{_esc(receipt.get('fornecedor', '?'))}</code>"

    itens = receipt.get("itens", [])
    lines = [
        forn_line,
        f"<b>Data:</b> {_esc(receipt.get('data') or 'não detectada')}",
        f"<b>Total da nota:</b> R$ {receipt.get('total', 0):.2f}",
        "",
        f"<b>Itens detectados ({len(itens)}):</b>",
    ]
    for i, it in enumerate(itens, 1):
        cat = it.get("categoria", "?")
        marca = f" • {_esc(it['marca'])}" if it.get("marca") else ""
        lines.append(f"  {i}. [{cat}] {_esc(it.get('descricao', '?'))}{marca} — R$ {it.get('preco_total', 0):.2f}")

    if receipt.get("observacoes"):
        lines.append("")
        lines.append(f"<i>{_esc(receipt['observacoes'])}</i>")
    lines.append("")
    lines.append("<i>Vou perguntar item por item. Se algo for auto-ignorado e você quiser incluir, mande: <code>incluir N</code></i>")
    return "\n".join(lines)


def handle_include_command(chat_id: int, item_index_1based: int) -> bool:
    """
    Handle 'incluir N' text command — revert a previously skipped item back to review.

    Returns True if the command was handled (state found and item revived), False otherwise.
    """
    service = sheets.get_service()
    state_id = state.find_latest_active_state_id(_spreadsheet_id(), chat_id, service=service)
    if not state_id:
        tg.send_message(chat_id, "❌ Nenhuma nota ativa pra editar. Mande uma foto primeiro.")
        return True

    payload = state.load_state(_spreadsheet_id(), state_id, service=service)
    if not payload:
        tg.send_message(chat_id, "❌ Estado não encontrado.")
        return True

    itens = payload.get("itens", [])
    if item_index_1based < 1 or item_index_1based > len(itens):
        tg.send_message(chat_id, f"❌ Item {item_index_1based} não existe (a nota tem {len(itens)} itens).")
        return True

    idx = item_index_1based - 1
    item = itens[idx]
    # Clear the resolution to force re-review
    payload["items_resolved"][idx] = None
    # If there was an alias=SKIP, mark this item to bypass it this round
    item.pop("alias_skip", None)
    # Force going through ask_item even if categoria was OUTRO — override the auto-skip
    # by setting a "force_review" flag and adjusting categoria handling
    item["force_review"] = True

    state.delete_state(_spreadsheet_id(), state_id, service=service)
    new_state_id = state.save_state(_spreadsheet_id(), payload, chat_id=chat_id, service=service)
    tg.send_message(chat_id, f"🔄 Trazendo item {item_index_1based} de volta pra revisão...")
    _next_step(chat_id, new_state_id, payload, service=service)
    return True


def _resolve_forn_name(forn_id: str) -> str:
    """Cheap lookup — read just the supplier name. Cached per-call would be nice but ok for now."""
    try:
        forns = sheets.get_fornecedores(_spreadsheet_id())
        for f in forns:
            if f["id"] == forn_id:
                return f"{f['id']} — {f['nome']}"
    except Exception:
        pass
    return forn_id
