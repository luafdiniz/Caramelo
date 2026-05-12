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
- Para notas manuscritas ou com itens ilegíveis, marque confianca: "baixa" e explique em observacoes
- Se houver desconto aplicado ao total, mencione em observacoes mas mantenha preco_total dos itens conforme aparecem
- NÃO invente dados. Se algo está ilegível, escreva "ILEGÍVEL" na descrição e marque confianca: "baixa"
"""


def parse_receipt(image_bytes: bytes, api_key: Optional[str] = None) -> dict:
    """
    Parse a receipt image using Gemini Flash.

    Args:
        image_bytes: Raw image bytes (JPG, PNG, HEIC supported by Gemini)
        api_key: Gemini API key. If None, reads from GEMINI_API_KEY env var.

    Returns:
        Parsed receipt dict with structure defined in SYSTEM_PROMPT.

    Raises:
        ValueError: If API returns invalid JSON.
        RuntimeError: If API call fails.
    """
    api_key = api_key or os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not configured")

    client = genai.Client(api_key=api_key)

    response = client.models.generate_content(
        model="gemini-2.0-flash-exp",
        contents=[
            types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"),
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
