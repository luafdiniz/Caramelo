"""
NF-e (Brazilian electronic invoice) XML parser.

Consumes raw NF-e XML bytes and returns the same dict shape produced by
`bot.lib.gemini.parse_receipt()`. That way the orchestrator can treat
photo-based receipts (parsed via Gemini Vision) and electronic invoices
(parsed here) identically downstream.

Suporta:
- NF-e modelo 55 (layout 3.10 e 4.00, ambos ainda em circulação).
- Root `<nfeProc>` (NF-e + protocolo) ou apenas `<NFe>`.
- Namespace padrão `http://www.portalfiscal.inf.br/nfe`.

Não classifica produtos: categoria fica sempre "OUTRO" e o matcher do
orchestrator (lib.matcher) é quem casa com a aba Produtos da planilha.
"""

import xml.etree.ElementTree as ET
from typing import Optional


NFE_NAMESPACE = "http://www.portalfiscal.inf.br/nfe"


def _strip_namespace(tree_root: ET.Element) -> ET.Element:
    """Remove o prefixo `{http://...}` de todas as tags da árvore.

    Faz tudo virar tag "pura" (`xNome`, `vNF` etc.) pra não ter que repetir
    o namespace em cada `find`/`findtext`. NF-e usa um único namespace
    consistente, então isso é seguro aqui.
    """
    for elem in tree_root.iter():
        if isinstance(elem.tag, str) and elem.tag.startswith("{"):
            elem.tag = elem.tag.split("}", 1)[1]
    return tree_root


def _findtext(parent: Optional[ET.Element], path: str, default: str = "") -> str:
    """findtext que aceita parent None e devolve string."""
    if parent is None:
        return default
    val = parent.findtext(path)
    return val.strip() if val else default


def _to_float(s: str) -> float:
    """NF-e sempre usa ponto decimal, mas guardamos uma tolerância mínima."""
    if not s:
        return 0.0
    try:
        return float(s.strip().replace(",", "."))
    except (ValueError, AttributeError):
        return 0.0


def _extract_date(ide: Optional[ET.Element]) -> Optional[str]:
    """Extrai a data de emissão (YYYY-MM-DD).

    Layout 4.00 usa `dhEmi` (ISO 8601 com timezone, ex.
    `2026-05-13T14:30:00-03:00`). Layout 3.10 antigo usa `dEmi`
    (`YYYY-MM-DD` puro). Tentamos os dois.
    """
    if ide is None:
        return None
    dh = _findtext(ide, "dhEmi")
    if dh:
        # Pega só a parte da data (antes do 'T')
        return dh.split("T", 1)[0]
    d = _findtext(ide, "dEmi")
    if d:
        return d
    return None


def _extract_supplier(emit: Optional[ET.Element]) -> str:
    """Razão social (xNome); cai pra nome fantasia (xFant) se vazio."""
    if emit is None:
        return ""
    name = _findtext(emit, "xNome")
    if name:
        return name
    return _findtext(emit, "xFant")


def _extract_observacoes(inf_nfe: ET.Element) -> str:
    """Junta `infAdic/infCpl` da nota + cada `infAdProd` de cada item.

    Separador `" | "` pra ficar legível quando exibirmos no Telegram.
    """
    pieces = []
    inf_cpl = _findtext(inf_nfe, "infAdic/infCpl")
    if inf_cpl:
        pieces.append(inf_cpl)
    for det in inf_nfe.findall("det"):
        adprod = _findtext(det, "infAdProd")
        if adprod:
            pieces.append(adprod)
    return " | ".join(pieces)


def _parse_item(det: ET.Element) -> dict:
    """Converte um `<det>` em um dict de item no formato do Gemini."""
    prod = det.find("prod")
    if prod is None:
        # NF-e sempre tem prod dentro de det; se faltou, devolve item vazio
        # pra não quebrar a iteração — o orchestrator vai descartar.
        return {
            "descricao": "",
            "marca": None,
            "categoria": "OUTRO",
            "qtde_embalagens": 0.0,
            "unidades_por_embalagem": 1,
            "preco_unitario": 0.0,
            "preco_total": 0.0,
            "confianca": "alta",
        }
    return {
        "descricao": _findtext(prod, "xProd"),
        # NF-e não tem campo de marca; deixa null e o matcher resolve.
        "marca": None,
        # Parser não classifica — o matcher do orchestrator faz isso
        # cruzando com a aba Produtos da planilha.
        "categoria": "OUTRO",
        "qtde_embalagens": _to_float(_findtext(prod, "qCom")),
        # NF-e não modela "pacote com N unidades": cada item é uma linha
        # comercial. O bot pergunta o pack_size na etapa de confirmação.
        "unidades_por_embalagem": 1,
        "preco_unitario": _to_float(_findtext(prod, "vUnCom")),
        "preco_total": _to_float(_findtext(prod, "vProd")),
        # XML é dado estruturado, sem incerteza de OCR.
        "confianca": "alta",
    }


def parse_nfe_xml(xml_bytes: bytes) -> dict:
    """Parse a Brazilian NF-e XML document and return the same dict shape that
    bot.lib.gemini.parse_receipt() produces.

    Args:
        xml_bytes: Raw NF-e XML bytes. Aceita root `<nfeProc>` (NF-e
            autorizada com protocolo) ou `<NFe>` diretamente.

    Returns:
        Dict no formato definido em `gemini.SYSTEM_PROMPT`.

    Raises:
        ValueError: Se o XML não for uma NF-e válida (sem `infNFe`).
    """
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as e:
        raise ValueError(f"Not a valid NF-e XML: {e}")

    _strip_namespace(root)

    # Localiza o `<infNFe>` independentemente do root ser <nfeProc> ou <NFe>.
    # `.//infNFe` busca recursivamente, então cobre os dois casos.
    inf_nfe = root.find(".//infNFe")
    if inf_nfe is None:
        raise ValueError("Not a valid NF-e XML")

    ide = inf_nfe.find("ide")
    emit = inf_nfe.find("emit")
    total_icms = inf_nfe.find("total/ICMSTot")

    fornecedor = _extract_supplier(emit)
    data = _extract_date(ide)
    total = _to_float(_findtext(total_icms, "vNF"))
    itens = [_parse_item(det) for det in inf_nfe.findall("det")]
    observacoes = _extract_observacoes(inf_nfe)
    frete, desconto = _extract_frete_desconto(inf_nfe, total_icms)

    return {
        "fornecedor": fornecedor,
        "data": data,
        "total": total,
        "itens": itens,
        "observacoes": observacoes,
        "frete": frete,
        "desconto": desconto,
        "confianca_geral": "alta",
    }


def _extract_frete_desconto(
    inf_nfe: ET.Element, total_icms: Optional[ET.Element]
) -> tuple[float, float]:
    """Return (frete, desconto) totals for the NF-e.

    Preferência: `vFrete` / `vDesc` no bloco `<ICMSTot>` (totalizador da
    nota — é o que a SEFAZ obriga a estar correto). Se algum estiver
    ausente ou zerado, soma os `vFrete` / `vDesc` de cada `<det>/<prod>`
    como fallback (NF-e antiga ou emitente que só preenche por item).
    """
    frete = _to_float(_findtext(total_icms, "vFrete"))
    desconto = _to_float(_findtext(total_icms, "vDesc"))

    if frete == 0.0:
        frete = sum(
            _to_float(_findtext(det.find("prod"), "vFrete"))
            for det in inf_nfe.findall("det")
        )
    if desconto == 0.0:
        desconto = sum(
            _to_float(_findtext(det.find("prod"), "vDesc"))
            for det in inf_nfe.findall("det")
        )
    return frete, desconto
