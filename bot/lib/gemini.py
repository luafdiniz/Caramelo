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
      "categoria": "ALI" | "FOR" | "EMB" | "EQP" | "OPR" | "OUTRO",
      "qtde_embalagens": 1,
      "unidades_por_embalagem": 1,
      "preco_unitario": 0.00,
      "preco_total": 0.00,
      "confianca": "alta" | "media" | "baixa"
    }
  ],
  "observacoes": "Notas sobre a extração (desconto aplicado, itens ilegíveis, manuscrito, etc.)",
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
- EMB = embalagens do produto final (sacola, fita, barbante, etiqueta, adesivo, celofane, colher descartável que vai pro cliente, etc.)
- EQP = equipamentos/utensílios duráveis de cozinha (panela, grade, luva silicone, espátula, batedeira, etc.)
- OPR = consumíveis operacionais usados na produção que NÃO vão pro produto final (papel toalha, palito de dente, papelaria/escritório, sacos de lixo, detergente neutro de cozinha, etc.)
- OUTRO = produtos claramente pessoais ou irrelevantes pro negócio de pudim (bebidas pessoais como Red Bull/cerveja, cosméticos, comida não-ingrediente, etc.)

Regras pra classificar:
- Se o item é comida e poderia ser ingrediente de pudim → ALI
- Se você não tem certeza se é insumo do negócio ou pessoal → OUTRO (usuário pode reverter)
- "Detergente" pra lavar prato de cozinha → OPR; sabão de roupa → OUTRO

- Para notas manuscritas ou com itens ilegíveis, marque confianca: "baixa" e explique em observacoes
- Se houver desconto aplicado ao total, mencione em observacoes mas mantenha preco_total dos itens conforme aparecem
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
      "categoria": "ALI" | "FOR" | "EMB" | "EQP" | "OPR" | "OUTRO",
      "qtde_embalagens": 1,
      "unidades_por_embalagem": 1,
      "preco_unitario": 0.00,
      "preco_total": 0.00,
      "confianca": "alta" | "media" | "baixa"
    }
  ],
  "observacoes": "Notas curtas sobre a interpretação (ambiguidade, suposições)",
  "confianca_geral": "alta" | "media" | "baixa"
}

Categorias (mesma classificação do parser de nota):
- ALI = alimentos/ingredientes (açúcar, leite, ovo, leite condensado, etc.)
- FOR = formas de pudim (forma plástica, alumínio, pote pra pudim, etc.)
- EMB = embalagens (sacola, fita, etiqueta, adesivo, celofane, colher descartável, etc.)
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

Se a mensagem NÃO descrever uma compra (saudação, pergunta, comando aleatório), responda:
{
  "fornecedor": "DESCONHECIDO",
  "data": null,
  "total": 0,
  "itens": [],
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
