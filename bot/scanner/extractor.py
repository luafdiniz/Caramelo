"""Text extractors used to enrich raw product results before comparison.

Two concerns:
- `extract_qtde_unidades(titulo)`: how many units per package. Ex: "Pote 220ml
  10 Unidades" → 10. Falls back to 1 when nothing matches (single-unit item).
- `brand_confirmed_in(marca, titulo)`: does the search result actually mention
  the required brand? Used to gate PLASTILANIA-only formas.
"""

import re
import unicodedata

from rapidfuzz import fuzz


_QTDE_PATTERNS = [
    re.compile(r'\b(\d+)\s*unidades?\b', re.IGNORECASE),
    re.compile(r'\b(\d+)\s*un\b\.?', re.IGNORECASE),
    re.compile(r'\bcx\.?\s*(\d+)\b', re.IGNORECASE),
    re.compile(r'\bcaixa\s+(?:com\s+)?(\d+)\b', re.IGNORECASE),
    re.compile(r'\bpacote\s+(?:com\s+)?(\d+)\b', re.IGNORECASE),
    re.compile(r'\bpack\s*(\d+)\b', re.IGNORECASE),
    re.compile(r'\bkit\s*(?:c/|com)?\s*(\d+)\b', re.IGNORECASE),
    re.compile(r'\bc/\s*(\d+)\s*un', re.IGNORECASE),
    re.compile(r'\bcom\s+(\d+)\s+unidades', re.IGNORECASE),
]


def extract_qtde_unidades(titulo: str) -> int:
    """Return how many units the product listing represents. Defaults to 1."""
    if not titulo:
        return 1
    for pat in _QTDE_PATTERNS:
        m = pat.search(titulo)
        if not m:
            continue
        try:
            q = int(m.group(1))
        except (ValueError, IndexError):
            continue
        if 1 <= q <= 10000:
            return q
    return 1


def _normalize(text: str) -> str:
    """Uppercase + strip accents for brand/title matching."""
    nfkd = unicodedata.normalize("NFKD", text or "")
    return "".join(c for c in nfkd if not unicodedata.combining(c)).upper()


def brand_confirmed_in(marca: str, titulo: str, marca_detectada: str = "") -> bool:
    """True when either the API-supplied brand field or the title contains the
    required brand. Accents ignored so 'PLASTILÂNIA' matches 'plastilania'."""
    if not marca:
        return True
    target = _normalize(marca)
    if target in _normalize(marca_detectada):
        return True
    if target in _normalize(titulo):
        return True
    return False


_SPEC_PATTERN = re.compile(
    r'(\d+(?:[.,]\d+)?)\s*(ml|g|kg|l|litros?)\b',
    re.IGNORECASE,
)

_KEYWORD_PATTERN = re.compile(
    r'\b(condensado|integral|refinado|cristal|desnatado|semidesnatado|leve|zero|light)\b',
    re.IGNORECASE,
)


def _normalize_spec(num: str, unit: str) -> str:
    return f"{num.replace(',', '.')}{unit.lower()}"


def spec_tokens(text: str) -> set[str]:
    """Extract dimensional tokens (220ml, 5kg, 1l) as normalized set."""
    if not text:
        return set()
    tokens = set()
    for num, unit in _SPEC_PATTERN.findall(text):
        tokens.add(_normalize_spec(num, unit))
    return tokens


def keyword_tokens(text: str) -> set[str]:
    """Extract product-type keywords (condensado, integral, cristal)."""
    if not text:
        return set()
    return {m.lower() for m in _KEYWORD_PATTERN.findall(text)}


_FUZZ_THRESHOLD = 85  # per-word typo tolerance (condesado ~ condensado)
_MIN_WORD_COVERAGE = 0.7  # % of termo words that must appear in titulo

_STOPWORDS = {
    "com", "de", "para", "do", "da", "dos", "das",
    "o", "a", "os", "as", "um", "uma", "e", "ou",
    "sem", "pro", "pra", "ml", "kg",
}


def _significant_words(text: str) -> list[str]:
    """Extract meaningful words: letters only, ≥4 chars, excluding stopwords.
    Numeric specs (220ml, 5kg) are captured elsewhere via spec_tokens."""
    if not text:
        return []
    norm = _normalize(text).lower()
    words = re.findall(r"[a-z]{4,}", norm)
    return [w for w in words if w not in _STOPWORDS]


def _word_matches_any(needle: str, haystack: list[str]) -> bool:
    if needle in haystack:
        return True
    for w in haystack:
        if fuzz.ratio(needle, w) >= _FUZZ_THRESHOLD:
            return True
    return False


def matches_search_intent(termo: str, titulo: str) -> bool:
    """True when the title matches the intent of the search:
      1. Every dimensional spec in `termo` (220ml, 5kg) is present exactly.
      2. At least 70% of `termo`'s significant words appear (fuzzy) in the title.

    Blocks:
      - 'leite condensado' matching 'creme de leite'
      - '220ml' matching '150ml'
      - 'pote quadrado' matching 'pote redondo'

    Tolerates:
      - Typo variants ('condesado' still passes for 'condensado')
      - Extra descriptors in the title (unidades, marca, tampa, etc.)
    """
    if not termo:
        return True

    titulo_norm = _normalize(titulo).lower().replace(" ", "")
    for spec in spec_tokens(termo):
        if spec not in titulo_norm:
            return False

    termo_words = _significant_words(termo)
    if not termo_words:
        return True
    title_words = _significant_words(titulo)

    hits = sum(1 for w in termo_words if _word_matches_any(w, title_words))
    coverage = hits / len(termo_words)
    return coverage >= _MIN_WORD_COVERAGE


def preco_por_unidade(preco_total: float, qtde_unidades: int) -> float:
    """Divide the listing price by units in the package.

    `qtde_unidades` is expected ≥ 1 (extractor default), but we guard anyway.
    """
    if qtde_unidades <= 0:
        return float(preco_total)
    return round(float(preco_total) / qtde_unidades, 4)
