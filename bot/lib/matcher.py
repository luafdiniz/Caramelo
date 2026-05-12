"""
Fuzzy matching of receipt items to existing Produtos and Fornecedores.

The challenge: receipt text is verbose and noisy ("IMPACTO Atacado & Varejo")
while the cadastrado name is short and clean ("Impacto"). Standard fuzzy ratios
(token_set_ratio, partial_ratio) get diluted by the noise.

Strategy used here:
1. Normalize both sides (lowercase, strip accents, replace punctuation with space)
2. Compute TOKEN CONTAINMENT — what % of the candidate's distinctive tokens appear
   in the receipt text. This is robust to the receipt being longer/noisier.
3. Fall back to partial_ratio for short strings or when containment is ambiguous.
4. Return the max of both.
"""

import re
import unicodedata
from typing import Optional
from rapidfuzz import fuzz


HIGH_CONFIDENCE = 80
MEDIUM_CONFIDENCE = 55

# Common words that shouldn't drive matching (legal entity suffixes, generic terms)
STOP_TOKENS = {
    "ltda", "me", "epp", "sa", "cia",
    "de", "da", "do", "das", "dos", "e",
    "atacado", "varejo", "comercio", "comercial",
    "loja", "lojas",
    "p", "c",  # "p/" "c/" become "p" "c" after norm
}


def _normalize(s: str) -> str:
    """Lowercase, strip accents, replace non-alphanumeric with single space."""
    if not s:
        return ""
    # Decompose accents and drop combining marks
    no_accent = "".join(
        c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn"
    )
    # Replace anything not alnum with space, lowercase, collapse spaces
    return re.sub(r"[^a-z0-9]+", " ", no_accent.lower()).strip()


def _tokens(s: str) -> set[str]:
    return {t for t in _normalize(s).split() if t and t not in STOP_TOKENS}


def score(receipt_text: str, candidate_name: str) -> float:
    """
    Score 0-100 for how likely the candidate matches the receipt text.

    Combines token containment (good for "short_clean_name in noisy_long_receipt")
    with fuzzy partial ratio (good for typos/abbreviations).
    """
    r_norm = _normalize(receipt_text)
    c_norm = _normalize(candidate_name)
    if not r_norm or not c_norm:
        return 0.0

    r_tokens = _tokens(receipt_text)
    c_tokens = _tokens(candidate_name)

    # Containment: what % of candidate's distinctive tokens are in receipt
    containment = 0.0
    if c_tokens:
        matching = c_tokens & r_tokens
        containment = 100.0 * len(matching) / len(c_tokens)
        # Penalize tiny candidates: if candidate is 1 token and the receipt has many,
        # require the match be a substantive token (>= 4 chars) to avoid false positives
        if len(c_tokens) == 1 and matching:
            only = next(iter(matching))
            if len(only) < 4:
                containment *= 0.5

    # Fuzzy partial — handles abbreviations like "famila" vs "familia"
    partial = fuzz.partial_ratio(r_norm, c_norm)

    return max(containment, partial)


def _best_match(text: str, choices: list[dict]) -> Optional[dict]:
    """Run our custom scorer against all choices, return best one above threshold."""
    if not text or not choices:
        return None
    best = None
    best_score = 0.0
    for c in choices:
        s = score(text, c["nome"])
        if s > best_score:
            best_score = s
            best = c
    if best is None or best_score < MEDIUM_CONFIDENCE:
        return None
    return {
        **best,
        "match_score": best_score,
        "match_confidence": "alta" if best_score >= HIGH_CONFIDENCE else "media",
    }


def match_fornecedor(name: str, fornecedores: list[dict]) -> Optional[dict]:
    return _best_match(name, fornecedores)


def match_produto(descricao: str, produtos: list[dict]) -> Optional[dict]:
    return _best_match(descricao, produtos)


def enrich_receipt(receipt: dict, produtos: list[dict], fornecedores: list[dict]) -> dict:
    """Add 'fornecedor_match' to receipt and 'produto_match' to each item."""
    enriched = dict(receipt)
    enriched["fornecedor_match"] = match_fornecedor(receipt.get("fornecedor", ""), fornecedores)
    enriched_items = []
    for item in receipt.get("itens", []):
        new_item = dict(item)
        new_item["produto_match"] = match_produto(item.get("descricao", ""), produtos)
        enriched_items.append(new_item)
    enriched["itens"] = enriched_items
    return enriched
