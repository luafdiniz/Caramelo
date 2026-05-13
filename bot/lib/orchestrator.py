"""
Orchestrator: photo → parse → match → interactive resolution → write to Sheets.

Interactive flow:
1. Photo arrives → Gemini parses → matcher enriches
2. If fornecedor doesn't match, ask: [Use sugestão] [Criar novo] [Cancelar]
3. For each unmatched item, ask: [Use sugestão] [Criar novo] [Pular]
4. For each kept item, ask pack size (units per receipt line) — learned via alias
5. After all resolved, write to Compras and confirm

State is kept in the hidden _BotState tab. Keys we use in the state dict:
- "fornecedor", "data", "total", "itens", "observacoes"  (raw from Gemini)
- "fornecedor_match" (best match or None)
- "current_item_index": index of the item currently being reviewed
- "resolved_supplier_id": final FORN-NNN to use
- "items_resolved": list parallel to "itens"; each entry is one of:
    - None (not yet resolved)
    - {"action": "skip", ...}
    - {"action": "use" | "create", "produto_id": "...", "pack_size": int}
  Until pack_size is set, "pack_size" key is absent.
- "awaiting_text_for_item" / "awaiting_pack_size_for_item": int idx when waiting on text input
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


# Pack-size presets shown as quick buttons. "custom" opens a free-text prompt.
PACK_SIZE_PRESETS = [1, 5, 10, 12, 24, 30]


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
    sup_alias = aliases.get_alias(_spreadsheet_id(), "FORNECEDOR", enriched.get("fornecedor", ""), service=service)
    if sup_alias:
        forn = next((f for f in fornecedores if f["id"] == sup_alias["resolved_id"]), None)
        if forn:
            enriched["fornecedor_match"] = {**forn, "match_score": 100, "match_confidence": "alta", "from_alias": True}

    for item in enriched.get("itens", []):
        item_alias = aliases.get_alias(_spreadsheet_id(), "PRODUTO", item.get("descricao", ""), service=service)
        if item_alias:
            if item_alias["resolved_id"] == "SKIP":
                item["alias_skip"] = True
            else:
                prod = next((p for p in produtos if p["id"] == item_alias["resolved_id"]), None)
                if prod:
                    item["produto_match"] = {
                        **prod,
                        "match_score": 100,
                        "match_confidence": "alta",
                        "from_alias": True,
                    }
                    if item_alias.get("pack_size"):
                        item["alias_pack_size"] = item_alias["pack_size"]

    # Initialize state
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
    elif action == "fpicklist":  # show list of all fornecedores as buttons
        fornecedores = sheets.get_fornecedores(_spreadsheet_id(), service=service)
        if not fornecedores:
            tg.edit_message_text(
                chat_id, message_id,
                "❌ Nenhum fornecedor cadastrado ainda. Cadastra direto na planilha ou clique em '➕ Criar novo'.",
                reply_markup=None,
            )
            return
        list_buttons = [
            [{"text": f"{f['id']} — {f['nome']}", "callback_data": f"fpick:{state_id}:{f['id']}"}]
            for f in fornecedores
        ]
        list_buttons.append([{"text": "← Voltar", "callback_data": f"fback:{state_id}"}])
        # Edit current message instead of creating new
        import requests as _req
        token = os.environ["TELEGRAM_BOT_TOKEN"]
        _req.post(
            f"https://api.telegram.org/bot{token}/editMessageText",
            json={
                "chat_id": chat_id,
                "message_id": message_id,
                "text": f"🏪 Qual fornecedor é esse?\nA nota diz: <code>{_esc(payload.get('fornecedor', '?'))}</code>",
                "parse_mode": "HTML",
                "reply_markup": {"inline_keyboard": list_buttons},
            },
            timeout=10,
        )
        return
    elif action == "fpick":  # specific fornecedor chosen from list
        forn_id = parts[2]
        fornecedores = sheets.get_fornecedores(_spreadsheet_id(), service=service)
        forn = next((f for f in fornecedores if f["id"] == forn_id), None)
        if not forn:
            tg.edit_message_text(chat_id, message_id, "❌ Fornecedor não encontrado.", reply_markup=None)
            return
        payload["resolved_supplier_id"] = forn_id
        raw_name = payload.get("fornecedor", "")
        saved = aliases.save(_spreadsheet_id(), "FORNECEDOR", raw_name, forn_id, service=service)
        learned = "\n📚 <i>Aprendi: dessa nota em diante, esse texto vira esse fornecedor.</i>" if saved else ""
        tg.edit_message_text(
            chat_id, message_id,
            f"✓ Fornecedor: <b>{_esc(forn['nome'])}</b>{learned}",
            reply_markup=None,
        )
    elif action == "fback":  # back to fornecedor question
        state.delete_state(_spreadsheet_id(), state_id, service=service)
        new_state_id = state.save_state(_spreadsheet_id(), payload, chat_id=chat_id, service=service)
        tg.edit_message_text(chat_id, message_id, "↩️ Voltando...", reply_markup=None)
        _ask_supplier(chat_id, new_state_id, payload)
        return
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
            alias_text = item.get("original_descricao") or item.get("descricao", "")
            saved = aliases.save(_spreadsheet_id(), "PRODUTO", alias_text, produto_id, service=service)
            if saved:
                learned = "\n📚 <i>Aprendi essa associação.</i>"
        tg.edit_message_text(
            chat_id, message_id,
            f"✓ Item {idx+1}: <b>{_esc(item['produto_match']['nome'])}</b>{learned}",
            reply_markup=None,
        )
    elif action == "icreate":  # item: create new product
        idx = int(parts[2])
        item = payload["itens"][idx]
        if len(parts) > 3 and parts[3] in ("ALI", "FOR", "EMB", "EQP", "OPR"):
            categoria = parts[3]
        else:
            categoria = item.get("categoria") or "ALI"
            if categoria == "OUTRO":
                categoria = "ALI"
        unidade = "UN"
        nome = item.get("descricao", "?")
        marca = item.get("marca")
        full_nome = f"{nome} ({marca})" if marca else nome
        new_id = sheets.create_produto(
            _spreadsheet_id(), full_nome, categoria, unidade=unidade, service=service
        )
        payload["items_resolved"][idx] = {"action": "create", "produto_id": new_id}
        alias_text = item.get("original_descricao") or item.get("descricao", "")
        aliases.save(_spreadsheet_id(), "PRODUTO", alias_text, new_id, service=service)
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
        saved = aliases.save(_spreadsheet_id(), "PRODUTO", item.get("descricao", ""), "SKIP", service=service)
        learned = "\n📚 <i>Aprendi: dessa nota em diante esse item é auto-ignorado.</i>" if saved else ""
        tg.edit_message_text(
            chat_id, message_id,
            f"⏭ Item {idx+1} ignorado: <i>{_esc(item.get('descricao', '?'))}</i>{learned}",
            reply_markup=None,
        )
    elif action == "ihint":  # item: user wants to type a corrected name
        idx = int(parts[2])
        item = payload["itens"][idx]
        item["original_descricao"] = item.get("original_descricao") or item.get("descricao", "")
        payload["awaiting_text_for_item"] = idx
        tg.edit_message_text(
            chat_id, message_id,
            f"✏️ Digite o nome correto pro item {idx+1}\n"
            f"(o que a nota mostra: <code>{_esc(item.get('descricao', '?'))}</code>)",
            reply_markup=None,
        )
    elif action == "psize":  # pack size for an item
        idx = int(parts[2])
        val = parts[3]
        if val == "custom":
            payload["awaiting_pack_size_for_item"] = idx
            tg.edit_message_text(
                chat_id, message_id,
                f"📦 Item {idx+1}: digite o número de unidades por embalagem.",
                reply_markup=None,
            )
            state.delete_state(_spreadsheet_id(), state_id, service=service)
            state.save_state(_spreadsheet_id(), payload, chat_id=chat_id, service=service)
            return
        n = max(1, int(val))
        _apply_pack_size(chat_id, message_id, payload, idx, n, service=service)
    elif action == "save":  # final save
        _finalize(chat_id, message_id, payload, state_id, service=service)
        return
    else:
        return

    # Persist updated state and proceed
    state.delete_state(_spreadsheet_id(), state_id, service=service)
    new_state_id = state.save_state(_spreadsheet_id(), payload, chat_id=chat_id, service=service)
    _next_step(chat_id, new_state_id, payload, service=service)


def _apply_pack_size(chat_id, message_id, payload, idx, n, service=None):
    """Persist a confirmed pack_size: update items_resolved, save alias, send confirmation message."""
    item = payload["itens"][idx]
    res = payload["items_resolved"][idx]
    res["pack_size"] = n
    produto_id = res["produto_id"]
    alias_text = item.get("original_descricao") or item.get("descricao", "")
    aliases.save(
        _spreadsheet_id(), "PRODUTO", alias_text, produto_id,
        pack_size=n, service=service,
    )

    qtde = float(item.get("qtde_embalagens", 1) or 1)
    preco_total = float(item.get("preco_total", 0) or 0)
    total_un = qtde * n
    unit_price = preco_total / total_un if total_un > 0 else 0

    if n > 1:
        label = (
            f"📦 Item {idx+1}: <b>{n} un por embalagem</b> · "
            f"{int(qtde) if qtde == int(qtde) else qtde}×{n} = {total_un:g} un · "
            f"R$ {unit_price:.2f}/un"
        )
    else:
        label = (
            f"📦 Item {idx+1}: <b>unidade avulsa</b> · "
            f"R$ {unit_price:.2f}/un"
        )
    tg.edit_message_text(chat_id, message_id, label, reply_markup=None)


# ============================================================================
# Step machine
# ============================================================================

def _next_step(chat_id: int, state_id: str, payload: dict, service=None) -> None:
    """Send the next prompt based on current state."""
    # 1. Resolve supplier
    if payload.get("resolved_supplier_id") is None:
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

    # 2. Resolve each item (product first, then pack_size)
    itens = payload.get("itens", [])
    resolved = payload.get("items_resolved", [])
    for idx, item in enumerate(itens):
        res = resolved[idx]

        # Stage A — product resolution
        if res is None:
            prod = item.get("produto_match")

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

            if prod and prod.get("match_confidence") == "alta":
                payload["items_resolved"][idx] = {"action": "use", "produto_id": prod["id"]}
                state.delete_state(_spreadsheet_id(), state_id, service=service)
                new_id = state.save_state(_spreadsheet_id(), payload, chat_id=chat_id, service=service)
                _next_step(chat_id, new_id, payload, service=service)
                return

            _ask_item(chat_id, state_id, payload, idx)
            return

        # Stage B — pack_size resolution (skip items don't need it)
        if res["action"] == "skip":
            continue
        if "pack_size" not in res:
            # Try alias-stored pack_size
            alias_pack = item.get("alias_pack_size")
            if alias_pack:
                res["pack_size"] = int(alias_pack)
                qtde = float(item.get("qtde_embalagens", 1) or 1)
                preco_total = float(item.get("preco_total", 0) or 0)
                total_un = qtde * int(alias_pack)
                unit_price = preco_total / total_un if total_un > 0 else 0
                if int(alias_pack) > 1:
                    tg.send_message(
                        chat_id,
                        f"🤖 Item {idx+1}: {int(alias_pack)} un por embalagem "
                        f"(via memória) — R$ {unit_price:.2f}/un",
                    )
                state.delete_state(_spreadsheet_id(), state_id, service=service)
                new_id = state.save_state(_spreadsheet_id(), payload, chat_id=chat_id, service=service)
                _next_step(chat_id, new_id, payload, service=service)
                return
            _ask_pack_size(chat_id, state_id, payload, idx)
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
            [{"text": "🔍 Escolher outro já cadastrado", "callback_data": f"fpicklist:{state_id}"}],
            [{"text": "➕ Criar novo", "callback_data": f"fcreate:{state_id}"}],
            [{"text": "❌ Cancelar tudo", "callback_data": f"cancel:{state_id}"}],
        ]
    else:
        text = (
            f"🏪 <b>Fornecedor não reconhecido</b>\n"
            f"Nota diz: <code>{_esc(raw_name)}</code>\n\n"
            f"O que faço?"
        )
        buttons = [
            [{"text": "🔍 Escolher um já cadastrado", "callback_data": f"fpicklist:{state_id}"}],
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

    hint_button = [{"text": "✏️ Corrigir nome do item", "callback_data": f"ihint:{state_id}:{idx}"}]

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
            hint_button,
            [{"text": "⏭ Pular este item", "callback_data": f"iskip:{state_id}:{idx}"}],
            [{"text": "❌ Cancelar tudo", "callback_data": f"cancel:{state_id}"}],
        ]
        tg.send_message_with_buttons(chat_id, text, buttons)
        return

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
            hint_button,
            [{"text": "❌ Cancelar tudo", "callback_data": f"cancel:{state_id}"}],
        ]
        tg.send_message_with_buttons(chat_id, text, buttons)
        return

    text = f"{info}\n\nNão achei produto parecido cadastrado. O que faço?"
    buttons = [
        [{"text": f"➕ Cadastrar como {categoria}", "callback_data": f"icreate:{state_id}:{idx}"}],
        hint_button,
        [{"text": "⏭ Pular este item", "callback_data": f"iskip:{state_id}:{idx}"}],
        [{"text": "❌ Cancelar tudo", "callback_data": f"cancel:{state_id}"}],
    ]
    tg.send_message_with_buttons(chat_id, text, buttons)


def _ask_pack_size(chat_id: int, state_id: str, payload: dict, idx: int) -> None:
    item = payload["itens"][idx]
    res = payload["items_resolved"][idx]
    qtde = float(item.get("qtde_embalagens", 1) or 1)
    preco_total = float(item.get("preco_total", 0) or 0)
    produto_id = res.get("produto_id", "")

    qtde_str = str(int(qtde)) if qtde == int(qtde) else f"{qtde:g}"
    text_lines = [
        f"📦 <b>Quantidade — Item {idx+1}/{len(payload['itens'])}</b>",
        f"Produto: <b>{_esc(produto_id)}</b>",
        f"Nota mostra: {qtde_str}× — R$ {preco_total:.2f}",
        "",
        "Quantas <b>unidades</b> vêm em cada item dessa linha?",
        "<i>(ex.: pacote de 5 formas = 5; caixa de 30 ovos = 30; unidade avulsa = 1)</i>",
    ]
    text = "\n".join(text_lines)

    rows = []
    current_row = []
    for preset in PACK_SIZE_PRESETS:
        total_un = qtde * preset
        unit_price = preco_total / total_un if total_un > 0 else 0
        label = f"{preset} un · R$ {unit_price:.2f}/un"
        current_row.append({"text": label, "callback_data": f"psize:{state_id}:{idx}:{preset}"})
        if len(current_row) == 2:
            rows.append(current_row)
            current_row = []
    if current_row:
        rows.append(current_row)
    rows.append([{"text": "✏️ Outro número...", "callback_data": f"psize:{state_id}:{idx}:custom"}])
    rows.append([{"text": "❌ Cancelar tudo", "callback_data": f"cancel:{state_id}"}])

    tg.send_message_with_buttons(chat_id, text, rows)


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
        preco = float(item.get("preco_total", 0) or 0)
        if not r or r["action"] == "skip":
            line = f"  <s>{desc}</s> — R$ {preco:.2f}"
            if r and r.get("reason") == "outro":
                skipped_outro.append(line)
            else:
                skipped_manual.append(line)
        else:
            qtde = float(item.get("qtde_embalagens", 1) or 1)
            pack = int(r.get("pack_size") or 1)
            total_un = qtde * pack
            unit_price = preco / total_un if total_un > 0 else 0
            pack_note = ""
            if pack > 1:
                pack_note = f" <i>({pack} un/embalagem → {total_un:g} un · R$ {unit_price:.2f}/un)</i>"
            included.append(f"  ✓ {desc} → {r['produto_id']} — R$ {preco:.2f}{pack_note}")

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
        pack = int(r.get("pack_size") or item.get("unidades_por_embalagem", 1) or 1)
        compra_id = sheets.append_compra(
            spreadsheet_id=_spreadsheet_id(),
            data=data,
            produto_id=r["produto_id"],
            fornecedor_id=forn_id,
            marca=item.get("marca") or "",
            qtde_embalagens=item.get("qtde_embalagens", 1),
            unidades_por_embalagem=pack,
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


def handle_text_hint(chat_id: int, text: str) -> bool:
    """
    Dispatch a plain text message to whatever the conversation is waiting on:
    - awaiting_pack_size_for_item → parse as integer pack size
    - awaiting_text_for_item → replace the item's descricao and re-match

    Returns True if the text was consumed, False if no state was awaiting input.
    """
    service = sheets.get_service()
    state_id = state.find_latest_active_state_id(_spreadsheet_id(), chat_id, service=service)
    if not state_id:
        return False
    payload = state.load_state(_spreadsheet_id(), state_id, service=service)
    if not payload:
        return False

    if "awaiting_pack_size_for_item" in payload:
        return _handle_pack_size_text(chat_id, state_id, payload, text, service)

    if "awaiting_text_for_item" in payload:
        return _handle_item_name_text(chat_id, state_id, payload, text, service)

    return False


def _handle_pack_size_text(chat_id, state_id, payload, text, service) -> bool:
    idx = payload.get("awaiting_pack_size_for_item")
    itens = payload.get("itens", [])
    if idx is None or idx < 0 or idx >= len(itens):
        payload.pop("awaiting_pack_size_for_item", None)
        return False

    try:
        n = int(text.strip().replace(",", ".").split(".")[0])
        if n <= 0:
            raise ValueError("non-positive")
    except (ValueError, TypeError):
        tg.send_message(chat_id, "❌ Não entendi. Digite um número inteiro maior que zero (ex: 5).")
        return True

    payload.pop("awaiting_pack_size_for_item", None)
    # Reuse _apply_pack_size but we don't have a message to edit, so build a fresh confirmation
    item = itens[idx]
    res = payload["items_resolved"][idx]
    res["pack_size"] = n
    produto_id = res["produto_id"]
    alias_text = item.get("original_descricao") or item.get("descricao", "")
    aliases.save(
        _spreadsheet_id(), "PRODUTO", alias_text, produto_id,
        pack_size=n, service=service,
    )
    qtde = float(item.get("qtde_embalagens", 1) or 1)
    preco_total = float(item.get("preco_total", 0) or 0)
    total_un = qtde * n
    unit_price = preco_total / total_un if total_un > 0 else 0
    tg.send_message(
        chat_id,
        f"📦 Item {idx+1}: <b>{n} un por embalagem</b> · "
        f"{int(qtde) if qtde == int(qtde) else qtde}×{n} = {total_un:g} un · "
        f"R$ {unit_price:.2f}/un",
    )

    state.delete_state(_spreadsheet_id(), state_id, service=service)
    new_state_id = state.save_state(_spreadsheet_id(), payload, chat_id=chat_id, service=service)
    _next_step(chat_id, new_state_id, payload, service=service)
    return True


def _handle_item_name_text(chat_id, state_id, payload, text, service) -> bool:
    idx = payload["awaiting_text_for_item"]
    itens = payload.get("itens", [])
    if idx is None or idx < 0 or idx >= len(itens):
        del payload["awaiting_text_for_item"]
        return False

    item = itens[idx]
    item["descricao"] = text.strip()
    produtos = sheets.get_produtos(_spreadsheet_id(), service=service)
    item["produto_match"] = matcher.match_produto(item["descricao"], produtos)
    item.pop("alias_skip", None)
    del payload["awaiting_text_for_item"]

    state.delete_state(_spreadsheet_id(), state_id, service=service)
    new_state_id = state.save_state(_spreadsheet_id(), payload, chat_id=chat_id, service=service)
    tg.send_message(chat_id, f"🔍 Buscando produto pra <b>{_esc(item['descricao'])}</b>...")
    _ask_item(chat_id, new_state_id, payload, idx)
    return True


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
    payload["items_resolved"][idx] = None
    item.pop("alias_skip", None)
    item["force_review"] = True

    state.delete_state(_spreadsheet_id(), state_id, service=service)
    new_state_id = state.save_state(_spreadsheet_id(), payload, chat_id=chat_id, service=service)
    tg.send_message(chat_id, f"🔄 Trazendo item {item_index_1based} de volta pra revisão...")
    _next_step(chat_id, new_state_id, payload, service=service)
    return True


def _resolve_forn_name(forn_id: str) -> str:
    """Cheap lookup — read just the supplier name."""
    try:
        forns = sheets.get_fornecedores(_spreadsheet_id())
        for f in forns:
            if f["id"] == forn_id:
                return f"{f['id']} — {f['nome']}"
    except Exception:
        pass
    return forn_id
