"""
Test runnable: parse NF-e XML fixture and check dict shape.

Não usa pytest pra ser consistente com test_parser.py (que é só um script
com prints). Rodar como:

    bot/.venv/bin/python bot/tests/test_nfe_xml.py

Cobre:
- Happy path: fixture NF-e 4.00 (root <NFe>) → fornecedor, data, total, 2 itens.
- Robustez: o mesmo payload embrulhado em <nfeProc> também é parseado.
- Erro: XML que não é NF-e levanta ValueError.
"""

import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.nfe_xml import parse_nfe_xml


FIXTURE_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "fixtures",
    "sample_nfe.xml",
)


# Contador global de assertions (pra mostrar quantas passaram)
_passed = 0
_failed = 0


def check(condition: bool, label: str):
    """Mini-assertion com print legível."""
    global _passed, _failed
    if condition:
        _passed += 1
        print(f"  PASS  {label}")
    else:
        _failed += 1
        print(f"  FAIL  {label}")


def test_happy_path():
    print("\n[test_happy_path] NF-e 4.00, root <NFe>")
    with open(FIXTURE_PATH, "rb") as f:
        xml_bytes = f.read()

    result = parse_nfe_xml(xml_bytes)

    check(result["fornecedor"] == "ACQUA EMBALAGENS LTDA", "fornecedor == 'ACQUA EMBALAGENS LTDA'")
    check(result["data"] == "2026-05-13", "data == '2026-05-13'")
    check(result["total"] == 80.00, f"total == 80.00 (got {result['total']})")
    check(result["confianca_geral"] == "alta", "confianca_geral == 'alta'")
    check(len(result["itens"]) == 2, f"len(itens) == 2 (got {len(result['itens'])})")

    # Item 1: LACRE
    it1 = result["itens"][0]
    check(it1["descricao"] == "LACRE TERMOSSELAVEL 80MM", f"item[0].descricao (got {it1['descricao']!r})")
    check(it1["marca"] is None, "item[0].marca is None")
    check(it1["categoria"] == "OUTRO", "item[0].categoria == 'OUTRO'")
    check(it1["qtde_embalagens"] == 100.0, f"item[0].qtde_embalagens == 100.0 (got {it1['qtde_embalagens']})")
    check(it1["unidades_por_embalagem"] == 1, "item[0].unidades_por_embalagem == 1")
    check(it1["preco_unitario"] == 0.15, f"item[0].preco_unitario == 0.15 (got {it1['preco_unitario']})")
    check(it1["preco_total"] == 15.00, f"item[0].preco_total == 15.00 (got {it1['preco_total']})")
    check(it1["confianca"] == "alta", "item[0].confianca == 'alta'")

    # Item 2: POTE
    it2 = result["itens"][1]
    check(it2["descricao"] == "POTE PLASTICO 250ML COM TAMPA", f"item[1].descricao (got {it2['descricao']!r})")
    check(it2["qtde_embalagens"] == 50.0, f"item[1].qtde_embalagens == 50.0 (got {it2['qtde_embalagens']})")
    check(it2["preco_unitario"] == 1.30, f"item[1].preco_unitario == 1.30 (got {it2['preco_unitario']})")
    check(it2["preco_total"] == 65.00, f"item[1].preco_total == 65.00 (got {it2['preco_total']})")

    # observacoes: deve juntar infCpl + o infAdProd do item 2
    obs = result["observacoes"]
    check("Venda direta ao consumidor final" in obs, "observacoes contém infCpl")
    check("Cor branca" in obs, "observacoes contém infAdProd do item 2")
    check(" | " in obs, "observacoes usa separador ' | '")


def test_nfeproc_wrapper():
    print("\n[test_nfeproc_wrapper] mesmo payload dentro de <nfeProc>")
    with open(FIXTURE_PATH, "rb") as f:
        inner = f.read().decode("utf-8")

    # Remove a declaração XML do inner pra não duplicar
    if inner.startswith("<?xml"):
        inner = inner.split("?>", 1)[1].lstrip()

    wrapped = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<nfeProc xmlns="http://www.portalfiscal.inf.br/nfe" versao="4.00">\n'
        f'{inner}\n'
        '<protNFe versao="4.00">\n'
        '  <infProt>\n'
        '    <tpAmb>2</tpAmb>\n'
        '    <verAplic>SP</verAplic>\n'
        '    <chNFe>35260513123456000199550010000001231000001234</chNFe>\n'
        '    <dhRecbto>2026-05-13T14:35:00-03:00</dhRecbto>\n'
        '    <nProt>135260000000001</nProt>\n'
        '    <digVal>abc123</digVal>\n'
        '    <cStat>100</cStat>\n'
        '    <xMotivo>Autorizado o uso da NF-e</xMotivo>\n'
        '  </infProt>\n'
        '</protNFe>\n'
        '</nfeProc>\n'
    )

    result = parse_nfe_xml(wrapped.encode("utf-8"))
    check(result["fornecedor"] == "ACQUA EMBALAGENS LTDA", "fornecedor parseado dentro de <nfeProc>")
    check(result["total"] == 80.00, f"total parseado dentro de <nfeProc> (got {result['total']})")
    check(len(result["itens"]) == 2, f"2 itens dentro de <nfeProc> (got {len(result['itens'])})")


def test_invalid_xml_raises():
    print("\n[test_invalid_xml_raises] XML qualquer levanta ValueError")
    try:
        parse_nfe_xml(b"<foo/>")
    except ValueError as e:
        check(True, f"ValueError levantado: {e}")
        return
    check(False, "deveria ter levantado ValueError")


def test_malformed_xml_raises():
    print("\n[test_malformed_xml_raises] XML inválido também levanta ValueError")
    try:
        parse_nfe_xml(b"not even xml")
    except ValueError as e:
        check(True, f"ValueError levantado: {e}")
        return
    check(False, "deveria ter levantado ValueError")


def main():
    tests = [
        test_happy_path,
        test_nfeproc_wrapper,
        test_invalid_xml_raises,
        test_malformed_xml_raises,
    ]
    for t in tests:
        try:
            t()
        except Exception:
            global _failed
            _failed += 1
            print(f"  CRASH  {t.__name__}")
            traceback.print_exc()

    print("\n" + "=" * 50)
    print(f"Resultado: {_passed} passed, {_failed} failed")
    print("=" * 50)
    sys.exit(0 if _failed == 0 else 1)


if __name__ == "__main__":
    main()
