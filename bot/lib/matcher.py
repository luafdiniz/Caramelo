"""
Fuzzy matching of extracted receipt items to existing Produtos and Fornecedores.

Uses rapidfuzz token-based similarity for product names. Returns confidence scores.
"""

from typing import Optional
from rapidfuzz import fuzz, process


# Confidence thresholds (0-100)
# Tuned for Brazilian receipts where item descriptions are abbreviated/truncated
# and supplier names on receipts often include "Atacado & Varejo" type suffixes
# while our cadastro is short.
HIGH_CONFIDENCE = 80
MEDIUM_CONFIDENCE = 50


def match_fornecedor(name: str, fornecedores: list[dict]) -> Optional[dict]:
    """
    Match a supplier name from a receipt to an existing Fornecedor.

    Returns the matched fornecedor dict with added 'match_score' and 'match_confidence',
    or None if no reasonable match.
    """
    if not name or not fornecedores:
        return None

    choices = {f["id"]: f["nome"] for f in fornecedores}
    result = process.extractOne(
        name, choices, scorer=fuzz.token_set_ratio, score_cutoff=MEDIUM_CONFIDENCE
    )
    if not result:
        return None

    matched_name, score, matched_id = result
    matched = next(f for f in fornecedores if f["id"] == matched_id)
    return {
        **matched,
        "match_score": score,
        "match_confidence": "alta" if score >= HIGH_CONFIDENCE else "media",
    }


def match_produto(descricao: str, produtos: list[dict]) -> Optional[dict]:
    """
    Match an item description from a receipt to an existing Produto.

    Strategy: token_set_ratio is robust to word order and partial matches.
    Receipt descriptions are often truncated/abbreviated.
    """
    if not descricao or not produtos:
        return None

    choices = {p["id"]: p["nome"] for p in produtos}
    result = process.extractOne(
        descricao, choices, scorer=fuzz.token_set_ratio, score_cutoff=MEDIUM_CONFIDENCE
    )
    if not result:
        return None

    matched_name, score, matched_id = result
    matched = next(p for p in produtos if p["id"] == matched_id)
    return {
        **matched,
        "match_score": score,
        "match_confidence": "alta" if score >= HIGH_CONFIDENCE else "media",
    }


def enrich_receipt(receipt: dict, produtos: list[dict], fornecedores: list[dict]) -> dict:
    """
    Take a raw Gemini receipt output and add matched IDs.

    Returns the receipt dict with new fields:
    - 'fornecedor_match': matched fornecedor or None
    - each item gets 'produto_match': matched produto or None
    """
    enriched = dict(receipt)
    enriched["fornecedor_match"] = match_fornecedor(
        receipt.get("fornecedor", ""), fornecedores
    )

    enriched_items = []
    for item in receipt.get("itens", []):
        new_item = dict(item)
        new_item["produto_match"] = match_produto(item.get("descricao", ""), produtos)
        enriched_items.append(new_item)
    enriched["itens"] = enriched_items

    return enriched
