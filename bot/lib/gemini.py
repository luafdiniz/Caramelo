"""
Gemini Vision receipt parser.

Sends a receipt image to Gemini Flash and returns structured data:
- Supplier name (best guess from header)
- Date
- Total amount
- Items with quantity, unit price, total
"""

import os
import json
import re
from typing import Optional
from google import genai
from google.genai import types


SYSTEM_PROMPT = """Você é um assistente especializado em extrair dados de notas fiscais brasileiras (cupom fiscal, NF-e, bloco manuscrito).

Analise a imagem da nota e retorne APENAS um JSON válido com este formato exato (sem markdown, sem ```):

{
  "fornecedor": "Nome da loja/fornecedor extraído do cabeçalho",
  "data": "YYYY-MM-DD ou null se ilegível",
  "total": 0.00,
  "itens": [
    {
      "descricao": "Nome do item como aparece na nota",
      "marca": "Marca se identificável, ou null",
      "categoria": "ALI" | "FOR" | "EMB" | "GRA" | "EQP" | "OPR" | "OUTRO",
      "qtde_embalagens": 1,
      "unidades_por_embalagem": 1,
      "preco_unitario": 0.00,
      "preco_total": 0.00,
      "confianca": "alta" | "media" | "baixa"
    }
  ],
  "frete": 0.00,
  "desconto": 0.00,
  "observacoes": "Notas sobre a extração (itens ilegíveis, manuscrito, etc.)",
  "confianca_geral": "alta" | "media" | "baixa"
}

Regras:
- Use ponto decimal (não vírgula) para números
- Para datas no formato brasileiro DD/MM/YYYY ou DD/MM/YY, converta para YYYY-MM-DD (assuma 20YY para anos de 2 dígitos)
- "qtde_embalagens" = quantos pacotes/unidades de venda foram comprados (ex: 2 pacotes)
- "unidades_por_embalagem" = quantos itens em cada pacote (ex: pente de 30 ovos = 30; sacola individual = 1)
- "preco_total" = preço total pago por essa linha (qtde × preço unit)

Categoria (importante! distingue entre tipos de custo):
- ALI = alimentos/ingredientes comestíveis que entram na receita do pudim (açúcar, leite, ovo, leite condensado, farinha, etc.)
- FOR = formas para o pudim (forma plástica, alumínio, etc.)
- EMB = embalagens FÍSICAS do produto final (sacola, fita lisa, barbante, celofane, colher descartável, pote, tampa, lacre — sem impressão).
- GRA = material impresso em gráfica (adesivo, etiqueta, rótulo, papel impresso, cartão, flyer, tag). É custo de comunicação visual / identidade, não embalagem física. **Importante:** adesivo e etiqueta vão em GRA, NÃO em EMB.
- EQP = equipamentos/utensílios duráveis de cozinha (panela, grade, luva silicone, espátula, batedeira, etc.)
- OPR = consumíveis operacionais usados na produção que NÃO vão pro produto final (papel toalha, palito de dente, papelaria/escritório, sacos de lixo, detergente neutro de cozinha, etc.)
- OUTRO = produtos claramente pessoais ou irrelevantes pro negócio de pudim (bebidas pessoais como Red Bull/cerveja, cosméticos, comida não-ingrediente, etc.)

Regras pra classificar:
- Se o item é comida e poderia ser ingrediente de pudim → ALI
- Se você não tem certeza se é insumo do negócio ou pessoal → OUTRO (usuário pode reverter)
- "Detergente" pra lavar prato de cozinha → OPR; sabão de roupa → OUTRO

Frete e desconto:
- Se a nota mostrar uma linha "TAXA DE ENTREGA", "FRETE", "ENTREGA" → preencher "frete" com o valor total (positivo).
- Se a nota mostrar uma linha "DESCONTO", "DESC.", "ABATIMENTO" → preencher "desconto" com o valor total (positivo, sem sinal de menos).
- Se não houver, deixe 0.

- Para notas manuscritas ou com itens ilegíveis, marque confianca: "baixa" e explique em observacoes
- NÃO invente dados. Se algo está ilegível, escreva "ILEGÍVEL" na descrição e marque confianca: "baixa"
"""


def _sniff_mime(data: bytes, fallback: str = "image/jpeg") -> str:
    """Guess the MIME type from the first bytes of a file."""
    if data[:4] == b"%PDF":
        return "application/pdf"
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:4] in (b"GIF8",):
        return "image/gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return fallback


def parse_receipt(file_bytes: bytes, api_key: Optional[str] = None, mime_type: Optional[str] = None) -> dict:
    """
    Parse a receipt (image or PDF) using Gemini Flash.

    Args:
        file_bytes: Raw bytes — JPG/PNG/WEBP/HEIC image, or PDF document.
        api_key: Gemini API key. If None, reads from GEMINI_API_KEY env var.
        mime_type: Override the MIME type. If None, sniffs from the file header.

    Returns:
        Parsed receipt dict with structure defined in SYSTEM_PROMPT.

    Raises:
        ValueError: If API returns invalid JSON.
        RuntimeError: If API call fails.
    """
    api_key = api_key or os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not configured")

    if mime_type is None:
        mime_type = _sniff_mime(file_bytes)

    client = genai.Client(api_key=api_key)

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=[
            types.Part.from_bytes(data=file_bytes, mime_type=mime_type),
            SYSTEM_PROMPT,
        ],
        config=types.GenerateContentConfig(
            temperature=0.1,
            response_mime_type="application/json",
        ),
    )

    raw = response.text or ""
    # Strip markdown fences if present
    raw = re.sub(r"^```(?:json)?\s*", "", raw.strip())
    raw = re.sub(r"\s*```$", "", raw)

    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"Gemini returned invalid JSON: {e}\nRaw: {raw[:500]}")


TEXT_PROMPT = """Você está extraindo uma compra a partir de uma descrição em texto livre em português brasileiro mandada por usuário num chat.

A pessoa que envia é dona de um negócio de pudim caseiro. Os textos costumam ser informais, tipo:
- "comprei 30 ovos na feira por 15 reais"
- "duas latas de leite condensado, 8 reais cada, no apoio mineiro"
- "papel toalha 12 unidades 24,90 supernosso"
- "uma forma de pudim grande 6,50 na maria chocolate"

Retorne APENAS um JSON válido com o mesmo formato do parser de nota fiscal:

{
  "fornecedor": "Nome do fornecedor mencionado ou \"DESCONHECIDO\" se não foi mencionado",
  "data": "YYYY-MM-DD relativa à data de hoje quando houver indicação (hoje, ontem, semana passada, dia 5...) ou null",
  "total": 0.00,
  "itens": [
    {
      "descricao": "Nome do produto",
      "marca": null,
      "categoria": "ALI" | "FOR" | "EMB" | "GRA" | "EQP" | "OPR" | "OUTRO",
      "qtde_embalagens": 1,
      "unidades_por_embalagem": 1,
      "preco_unitario": 0.00,
      "preco_total": 0.00,
      "confianca": "alta" | "media" | "baixa"
    }
  ],
  "frete": 0.00,
  "desconto": 0.00,
  "observacoes": "Notas curtas sobre a interpretação (ambiguidade, suposições)",
  "confianca_geral": "alta" | "media" | "baixa"
}

Categorias (mesma classificação do parser de nota):
- ALI = alimentos/ingredientes (açúcar, leite, ovo, leite condensado, etc.)
- FOR = formas de pudim (forma plástica, alumínio, pote pra pudim, etc.)
- EMB = embalagens FÍSICAS sem impressão (sacola lisa, fita lisa, barbante, celofane, colher descartável, pote, tampa, lacre)
- GRA = material impresso em gráfica (adesivo, etiqueta, rótulo, papel impresso, cartão, flyer, tag). **Adesivo e etiqueta sempre vão em GRA, não em EMB.**
- EQP = equipamentos duráveis (panela, grade, luva silicone, espátula, batedeira, etc.)
- OPR = consumíveis operacionais (papel toalha, palito, sabão neutro, etc.)
- OUTRO = pessoal ou irrelevante (bebidas, cosméticos, etc.)

Regras de cálculo:
- "30 ovos por 15 reais" → qtde_embalagens=30, unidades_por_embalagem=1, preco_total=15.00, preco_unitario=0.50
- "2 latas a 8 reais cada" → qtde=2, preco_unitario=8.00, preco_total=16.00
- Se mencionar só preço unitário, calcule total = qtde × unitário
- Se mencionar só total, calcule unitário = total / qtde
- Use ponto decimal (não vírgula) nos números

Regras de confiança:
- Se quantidade, produto e preço estiverem claros: confianca "alta"
- Se algum desses estiver implícito ou ambíguo: "media"
- Se faltar algo crítico (sem produto, sem preço, sem qtde): "baixa" e explique em observacoes

Frete e desconto:
- Se a mensagem citar frete/entrega/taxa → preencher "frete" com o valor (positivo).
- Se citar desconto → preencher "desconto" com o valor (positivo).
- Se não citar, deixe 0.

Se a mensagem NÃO descrever uma compra (saudação, pergunta, comando aleatório), responda:
{
  "fornecedor": "DESCONHECIDO",
  "data": null,
  "total": 0,
  "itens": [],
  "frete": 0,
  "desconto": 0,
  "observacoes": "Mensagem não parece descrever uma compra.",
  "confianca_geral": "baixa"
}
"""


def parse_receipt_text(text: str, api_key: Optional[str] = None, today: Optional[str] = None) -> dict:
    """
    Parse a free-text purchase description (e.g. "comprei 30 ovos na feira por 15 reais")
    and return the same dict shape that `parse_receipt()` produces.

    `today` is injected into the prompt so relative dates ("hoje", "ontem") can be
    resolved without giving Gemini access to a clock.
    """
    api_key = api_key or os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not configured")

    if today is None:
        from datetime import date
        today = date.today().isoformat()

    client = genai.Client(api_key=api_key)
    prompt = f"{TEXT_PROMPT}\n\nHoje é {today}.\n\nTexto do usuário:\n\"\"\"\n{text}\n\"\"\""

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=[prompt],
        config=types.GenerateContentConfig(
            temperature=0.1,
            response_mime_type="application/json",
        ),
    )

    raw = response.text or ""
    raw = re.sub(r"^```(?:json)?\s*", "", raw.strip())
    raw = re.sub(r"\s*```$", "", raw)

    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"Gemini returned invalid JSON: {e}\nRaw: {raw[:500]}")


# ============================================================================
# Modo Feira — áudio, abertura, venda e fechamento
# ============================================================================

def _client(api_key: Optional[str] = None) -> "genai.Client":
    api_key = api_key or os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not configured")
    return genai.Client(api_key=api_key)


def _parse_json(raw: str) -> dict:
    raw = re.sub(r"^```(?:json)?\s*", "", (raw or "").strip())
    raw = re.sub(r"\s*```$", "", raw)
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as e:
        # Log full raw so operator can inspect what Gemini actually replied.
        # Real case 2026-08-05: user sent NF-e image while a feira was open;
        # Gemini couldn't fit into venda/fechamento/status schema, returned
        # partial JSON like '\n"intent"...' and the whole flow crashed.
        print(f"gemini._parse_json: JSONDecodeError {e}")
        print(f"gemini._parse_json: RAW response (full): {raw!r}")
        raise ValueError(f"Gemini returned invalid JSON: {e}")
    if not isinstance(parsed, dict):
        # Defensive — if Gemini decided to return a string/list/null, treat
        # as empty dict rather than blowing up on parsed.get(...) downstream.
        print(f"gemini._parse_json: got {type(parsed).__name__} not dict: {parsed!r}")
        return {}
    return parsed


def transcribe_audio(audio_bytes: bytes, mime_type: str = "audio/ogg", api_key: Optional[str] = None) -> str:
    """
    Transcribe a voice message (Telegram voice = OGG/Opus) to plain text.

    Returns the transcription string. Raises RuntimeError if no API key.
    """
    client = _client(api_key)
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=[
            types.Part.from_bytes(data=audio_bytes, mime_type=mime_type or "audio/ogg"),
            "Transcreva este áudio em português do Brasil. Responda APENAS com o texto "
            "transcrito, sem comentários, sem aspas, sem rótulos.",
        ],
        config=types.GenerateContentConfig(temperature=0.0),
    )
    return (response.text or "").strip()


FEIRA_OPENING_PROMPT = """Você interpreta uma mensagem da dona de um negócio de pudim que está SAINDO para vender numa feira/bazar.
Ela pode vender MAIS DE UM tamanho de pudim (ex: 200g e 500g), cada um com preço próprio.

Exemplos:
- "tamo saindo pra feira, levando 30 pudins de 200g a R$18"
  -> 1 produto: 200g, qtd 30, preço 18
- "levando 63 de 200g e 4 de 500g"
  -> 2 produtos sem preço ainda: 200g qtd 63 preço null; 500g qtd 4 preço null
- "18 o de 200g e 45 o de 500g"
  -> 2 produtos só com preço: 200g preço 18; 500g preço 45

Retorne APENAS um JSON válido:

{
  "is_abertura": true,
  "produtos": [
    {"tamanho": "200g", "qtd_levada": 63, "preco": 18.00},   // qtd_levada e/ou preco podem ser null
    {"tamanho": "500g", "qtd_levada": 4, "preco": 45.00}
  ],
  "descricao": "Feira ..."   // local/nome do evento se houver, senão ""
}

Regras:
- "tamanho": normalize pra número + unidade, ex "200g", "500g", "1kg". Se ela não falar tamanho, use "padrão".
- Use ponto decimal. "18 reais"/"R$18"/"dezoito" -> 18.00.
- qtd_levada = quantos pudins daquele tamanho ela está levando. preco = preço de venda unitário.
- Inclua um produto mesmo que só tenha a qtde (preco null) ou só o preço (qtd_levada null).
- Ignore comentários como "talvez dou pra produção" — não viram produto.
- Se a mensagem NÃO for sobre sair pra vender numa feira, retorne {"is_abertura": false, "produtos": [], "descricao": ""}.
"""


def parse_feira_opening(text: str, api_key: Optional[str] = None) -> dict:
    """Interpret a 'saindo pra feira' message (multi-product). See FEIRA_OPENING_PROMPT."""
    client = _client(api_key)
    prompt = f'{FEIRA_OPENING_PROMPT}\n\nMensagem:\n"""\n{text}\n"""'
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=[prompt],
        config=types.GenerateContentConfig(temperature=0.1, response_mime_type="application/json"),
    )
    return _parse_json(response.text)


FEIRA_MESSAGE_PROMPT = """Você ajuda a dona de um negócio de pudim a gerenciar uma feira que JÁ ESTÁ ABERTA.
Ela vai te mandando recados informais (texto, áudio transcrito, ou descrição de imagem) e você classifica e extrai os dados.

Tamanhos de pudim à venda nesta feira (com preço unitário):
{produtos_str}

Classifique a mensagem em um destes "intent":
- "venda": ela registrou uma venda. Ex: "vendi 2 pro fulano", "vendi 2 de 500g agora", "vendi 3 pra dona maria no pix", "vendi 2, o joão vai voltar pra pagar".
- "fechamento": ela está encerrando/fechando ou informando o balanço final. Ex: "voltaram 5 de 200g e 1 de 500g", "recebi 200 em dinheiro e 150 no pix", "acabou a feira, sobraram 4", "fim de feira".
- "status": ela quer o resumo parcial. Ex: "como tá o balanço?", "quanto já vendi?".
- "outro": qualquer outra coisa.

Retorne APENAS um JSON válido:

{
  "intent": "venda" | "fechamento" | "status" | "outro",
  "qtde": 2,                       // (venda) número de pudins vendidos; null se não disser
  "tamanho": "200g",               // (venda) tamanho vendido se ela disser ("200g","500g"...); "" se não disse
  "cliente_nome": "Fulano",        // (venda) nome do cliente; "" se anônimo ("vendi 2 agora")
  "pago": true,                    // (venda) false se ficou fiado / "vai pagar depois" / "deve"
  "forma_pagamento": "dinheiro",   // (venda) "dinheiro" | "pix" | "" se não disse
  "preco_unit": null,              // (venda) preço unitário SÓ se ela disser um valor diferente; senão null
  "notas": "",                     // (venda) observação curta, se houver
  "voltou": [                      // (fechamento) pudins que voltaram, por tamanho; [] se não disse
    {"tamanho": "200g", "qtde": 5},
    {"tamanho": "500g", "qtde": 1}
  ],
  "dinheiro": null,                // (fechamento) total recebido em dinheiro; null se não disse
  "pix": null                      // (fechamento) total recebido no pix; null se não disse
}

Regras:
- "tamanho": normalize pra "200g","500g","1kg". Se ela não falar tamanho numa venda, deixe "".
- Use ponto decimal nos números.
- "pix"/"piques"/"transferência" -> "pix". "dinheiro"/"em espécie"/"cash" -> "dinheiro".
- "fiado"/"vai voltar pra pagar"/"paga depois"/"anota aí"/"deve" -> pago=false (e forma_pagamento "").
- Se for venda mas não disser forma de pagamento, deixe forma_pagamento "" e pago=true.
- Campos não aplicáveis ao intent: deixe null/""/[] conforme o tipo.
"""


def _produtos_str(produtos: list) -> str:
    if not produtos:
        return "- (tamanho único, preço padrão)"
    out = []
    for p in produtos:
        preco = p.get("preco")
        preco_s = f"R$ {float(preco):.2f}" if preco else "preço não definido"
        out.append(f"- {p.get('tamanho', 'padrão')}: {preco_s}")
    return "\n".join(out)


def parse_feira_message(text: str, produtos: list, api_key: Optional[str] = None) -> dict:
    """Classify + extract a message sent during an open feira (text/transcript).

    `produtos` is the feira's product list (each {tamanho, preco, ...}) so the
    model knows the available sizes and prices.
    """
    client = _client(api_key)
    prompt = FEIRA_MESSAGE_PROMPT.format(produtos_str=_produtos_str(produtos))
    prompt += f'\n\nMensagem:\n"""\n{text}\n"""'
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=[prompt],
        config=types.GenerateContentConfig(temperature=0.1, response_mime_type="application/json"),
    )
    return _parse_json(response.text)


def parse_feira_image(image_bytes: bytes, produtos: list, mime_type: Optional[str] = None,
                      api_key: Optional[str] = None) -> dict:
    """Interpret an image sent during an open feira. Same shape as parse_feira_message."""
    client = _client(api_key)
    if mime_type is None:
        mime_type = _sniff_mime(image_bytes)
    prompt = FEIRA_MESSAGE_PROMPT.format(produtos_str=_produtos_str(produtos))
    prompt += "\n\nA mensagem é uma IMAGEM (anotação à mão, recado, ou comprovante de pix). Extraia os dados dela."
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=[
            types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
            prompt,
        ],
        config=types.GenerateContentConfig(temperature=0.1, response_mime_type="application/json"),
    )
    return _parse_json(response.text)
