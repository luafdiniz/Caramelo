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
    # "unidade"/"unidades"/"unid"/"unids" — captura variações abreviadas
    # comuns em títulos do ML tipo "10 Unid" ou "300 Un Transparente".
    re.compile(r'\b(\d+)\s*unida?d?e?s?\b', re.IGNORECASE),
    re.compile(r'\b(\d+)\s*un\b\.?', re.IGNORECASE),
    re.compile(r'\bcx\.?\s*(\d+)\b', re.IGNORECASE),
    re.compile(r'\bcaixa\s+(?:com\s+)?(\d+)\b', re.IGNORECASE),
    re.compile(r'\bpacote\s+(?:com\s+)?(\d+)\b', re.IGNORECASE),
    re.compile(r'\bpack\s*(\d+)\b', re.IGNORECASE),
    re.compile(r'\bkit\s*(?:c/|com)?\s*(\d+)\b', re.IGNORECASE),
    re.compile(r'\bc/\s*(\d+)\s*un', re.IGNORECASE),
    re.compile(r'\bcom\s+(\d+)\s+unida?d?e?s?', re.IGNORECASE),
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

# Alguns sites (ex: Maria Chocolate) descrevem formas de pudim por
# DIMENSÕES em cm em vez de volume nominal. Sem esse mapping, uma busca
# por "500ml" não bate no título "Forma para Pudim 16x6 cm c/ 6 unidades".
# Confirmado 2026-08-07 nas páginas da Maria Chocolate; outros catálogos
# Plastilania podem seguir a mesma convenção.
_DIMENSIONS_TO_VOLUME_ML = {
    "8x5x4": 80,      # Mini 80ml (20un/pack)
    "9x6,5x4": 220,   # Quadrado 220ml (10un/pack)
    "9x65x4": 220,    # variação sem vírgula
    "16x6": 500,      # Grande Oitavada 500ml (6un/pack)
    # Nota: 1,1L Família não achado no catálogo Maria Chocolate hoje.
    # Adicionar aqui quando aparecer.
}
_DIMENSION_PATTERN = re.compile(
    r'\b(\d+(?:[.,]\d+)?(?:x\d+(?:[.,]\d+)?){1,3})\s*cm\b',
    re.IGNORECASE,
)


def _derive_specs_from_dimensions(text: str) -> set[str]:
    """Return normalized volume specs implied by dimensions in the text.
    Ex: 'Forma 16x6 cm c/ 6 un' → {'500ml', '0.5l'}."""
    out: set[str] = set()
    if not text:
        return out
    for match in _DIMENSION_PATTERN.findall(text):
        key = match.lower().replace(" ", "")
        volume_ml = _DIMENSIONS_TO_VOLUME_ML.get(key)
        if volume_ml is None:
            continue
        out.add(f"{volume_ml}ml")
        # Also add liters form (500ml → 0.5l)
        as_l = volume_ml / 1000.0
        # Match how spec_tokens formats: no trailing zeros, decimal point.
        as_l_str = f"{as_l:g}"
        out.add(f"{as_l_str}l")
    return out

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
    # Enriquece o título com specs implícitos de dimensões conhecidas
    # (ex: "16x6 cm" → conta como se tivesse "500ml" no título).
    derived_specs = _derive_specs_from_dimensions(titulo)
    for spec in spec_tokens(termo):
        if spec in titulo_norm:
            continue
        if spec in derived_specs:
            continue
        return False

    termo_words = _significant_words(termo)
    if not termo_words:
        return True
    title_words = _significant_words(titulo)

    hits = sum(1 for w in termo_words if _word_matches_any(w, title_words))
    coverage = hits / len(termo_words)
    return coverage >= _MIN_WORD_COVERAGE


_MEDIDA_PATTERN = re.compile(
    r'(\d+(?:[.,]\d+)?)\s*(kg|g|l|ml|litros?)\b',
    re.IGNORECASE,
)


def extract_medida(titulo: str) -> tuple[float, str]:
    """Extract the first weight/volume spec from a product title.

    Returns (value_in_base_unit, base_unit_name) where base is 'kg' for
    weights and 'l' for volumes, so different pack sizes are comparable:
        "5kg"   → (5.0,   'kg')
        "500g"  → (0.5,   'kg')
        "1L"    → (1.0,   'l')
        "395g"  → (0.395, 'kg')
        "220ml" → (0.22,  'l')

    Returns (0.0, "") when nothing matches.
    """
    if not titulo:
        return 0.0, ""
    m = _MEDIDA_PATTERN.search(titulo)
    if not m:
        return 0.0, ""
    try:
        val = float(m.group(1).replace(",", "."))
    except ValueError:
        return 0.0, ""
    unit = m.group(2).lower()
    if unit == "g":
        return val / 1000.0, "kg"
    if unit == "kg":
        return val, "kg"
    if unit == "ml":
        return val / 1000.0, "l"
    if unit.startswith("l"):
        return val, "l"
    return 0.0, ""


def preco_por_unidade(preco_total: float, qtde_unidades: int) -> float:
    """Divide the listing price by units in the package.

    `qtde_unidades` is expected ≥ 1 (extractor default), but we guard anyway.
    """
    if qtde_unidades <= 0:
        return float(preco_total)
    return round(float(preco_total) / qtde_unidades, 4)
