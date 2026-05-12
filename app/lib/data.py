"""
Cached data access layer for the Streamlit app.

Reuses bot/lib/sheets.py for I/O. Caches reads for 30 seconds — fresh enough
for a personal admin tool, slow enough to avoid hammering the API.

After any write, call invalidate_cache() to force a reload.
"""

import os
import sys
import json
from typing import Optional
import streamlit as st
import pandas as pd

# Make bot/lib importable
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO_ROOT, "bot"))

from lib import sheets as _sheets  # noqa: E402


CACHE_TTL_SECONDS = 30


def _spreadsheet_id() -> str:
    try:
        return st.secrets["SPREADSHEET_ID"]
    except (KeyError, FileNotFoundError):
        return os.environ["SPREADSHEET_ID"]


def _service_account_json() -> str:
    try:
        v = st.secrets["GOOGLE_SERVICE_ACCOUNT_JSON"]
    except (KeyError, FileNotFoundError):
        v = os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"]
    # st.secrets may return a dict if the secret was provided as TOML table.
    # Our bot module expects a JSON string.
    if isinstance(v, dict):
        return json.dumps(dict(v))
    return v


def get_service():
    """Build the Sheets API service. Not cached — Streamlit creates per-session."""
    return _sheets.get_service(_service_account_json())


def invalidate_cache():
    """Clear all cached reads. Call after any write."""
    st.cache_data.clear()


# --- Cached reads ------------------------------------------------------------

@st.cache_data(ttl=CACHE_TTL_SECONDS)
def get_produtos() -> pd.DataFrame:
    service = get_service()
    rows = _sheets.get_produtos(_spreadsheet_id(), service=service)
    df = pd.DataFrame(rows)
    if not df.empty:
        df["categoria"] = df["id"].str.split("-").str[0]
    return df


@st.cache_data(ttl=CACHE_TTL_SECONDS)
def get_fornecedores() -> pd.DataFrame:
    service = get_service()
    rows = _sheets.get_fornecedores(_spreadsheet_id(), service=service)
    return pd.DataFrame(rows)


@st.cache_data(ttl=CACHE_TTL_SECONDS)
def get_tamanhos() -> pd.DataFrame:
    service = get_service()
    result = service.spreadsheets().values().get(
        spreadsheetId=_spreadsheet_id(), range="Tamanhos!A2:H"
    ).execute()
    rows = result.get("values", [])
    df = pd.DataFrame(rows, columns=["id", "nome", "peso_kg", "volume_ml", "rendimento", "canal", "preco_venda", "notas"][:max(1, len(rows[0])) if rows else 1])
    # Normalize types
    for col in ("peso_kg", "volume_ml", "rendimento", "preco_venda"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


@st.cache_data(ttl=CACHE_TTL_SECONDS)
def get_compras() -> pd.DataFrame:
    service = get_service()
    result = service.spreadsheets().values().get(
        spreadsheetId=_spreadsheet_id(),
        range="Compras!A2:K",
        valueRenderOption="UNFORMATTED_VALUE",
    ).execute()
    rows = result.get("values", [])
    cols = ["id", "data", "produto_id", "fornecedor_id", "marca",
            "qtde_embalagens", "unidades_por_embalagem", "total_unidades",
            "preco_total", "preco_unitario", "notas"]
    if not rows:
        return pd.DataFrame(columns=cols)
    # Pad short rows
    rows = [r + [""] * (len(cols) - len(r)) for r in rows]
    df = pd.DataFrame(rows, columns=cols)
    df["data"] = pd.to_datetime(df["data"], errors="coerce")
    for col in ("qtde_embalagens", "unidades_por_embalagem", "total_unidades", "preco_total", "preco_unitario"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


@st.cache_data(ttl=CACHE_TTL_SECONDS)
def get_receita() -> pd.DataFrame:
    service = get_service()
    result = service.spreadsheets().values().get(
        spreadsheetId=_spreadsheet_id(), range="Receita!A2:D",
        valueRenderOption="UNFORMATTED_VALUE",
    ).execute()
    rows = result.get("values", [])
    cols = ["produto_id", "nome", "qtde", "unidade"]
    if not rows:
        return pd.DataFrame(columns=cols)
    rows = [r + [""] * (len(cols) - len(r)) for r in rows]
    df = pd.DataFrame(rows, columns=cols)
    df["qtde"] = pd.to_numeric(df["qtde"], errors="coerce")
    return df


@st.cache_data(ttl=CACHE_TTL_SECONDS)
def get_embalagens_por_tamanho() -> pd.DataFrame:
    service = get_service()
    result = service.spreadsheets().values().get(
        spreadsheetId=_spreadsheet_id(), range="Embalagens_Por_Tamanho!A2:D",
        valueRenderOption="UNFORMATTED_VALUE",
    ).execute()
    rows = result.get("values", [])
    cols = ["tamanho_id", "produto_id", "nome", "qtde_por_unidade"]
    if not rows:
        return pd.DataFrame(columns=cols)
    rows = [r + [""] * (len(cols) - len(r)) for r in rows]
    df = pd.DataFrame(rows, columns=cols)
    df["qtde_por_unidade"] = pd.to_numeric(df["qtde_por_unidade"], errors="coerce")
    return df


@st.cache_data(ttl=CACHE_TTL_SECONDS)
def get_fornadas() -> pd.DataFrame:
    service = get_service()
    result = service.spreadsheets().values().get(
        spreadsheetId=_spreadsheet_id(), range="Fornadas!A2:M",
        valueRenderOption="UNFORMATTED_VALUE",
    ).execute()
    rows = result.get("values", [])
    cols = ["id", "data_inicio", "data_fim", "tamanho_id", "qtde_produzida",
            "qtde_vendida", "qtde_cortesia", "preco_venda_unit", "receita_total",
            "custo_unit", "custo_total", "lucro", "notas"]
    if not rows:
        return pd.DataFrame(columns=cols)
    rows = [r + [""] * (len(cols) - len(r)) for r in rows]
    df = pd.DataFrame(rows, columns=cols)
    df["data_inicio"] = pd.to_datetime(df["data_inicio"], errors="coerce")
    df["data_fim"] = pd.to_datetime(df["data_fim"], errors="coerce")
    for col in ("qtde_produzida", "qtde_vendida", "qtde_cortesia",
                "preco_venda_unit", "receita_total", "custo_unit", "custo_total", "lucro"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


# --- Cost calculations -------------------------------------------------------

def latest_unit_price(produto_id: str, compras: Optional[pd.DataFrame] = None) -> float:
    """Most recent preco_unitario for a produto, or 0 if no compras."""
    if compras is None:
        compras = get_compras()
    sub = compras[compras["produto_id"] == produto_id].dropna(subset=["data"])
    if sub.empty:
        return 0.0
    last = sub.sort_values("data", ascending=False).iloc[0]
    return float(last["preco_unitario"] or 0)


def calc_custo_alimento_unid(tamanho_id: str) -> tuple[float, pd.DataFrame]:
    """
    Cost of ingredients per unit of pudim.
    Returns (custo_por_unidade, dataframe_with_breakdown).
    """
    tamanhos = get_tamanhos()
    receita = get_receita()
    compras = get_compras()
    produtos = get_produtos()

    t = tamanhos[tamanhos["id"] == tamanho_id]
    if t.empty:
        return 0.0, pd.DataFrame()
    rendimento = float(t.iloc[0]["rendimento"] or 1)

    breakdown = receita.copy()
    breakdown["preco_unit_atual"] = breakdown["produto_id"].apply(lambda p: latest_unit_price(p, compras))
    breakdown["custo_na_receita"] = breakdown["qtde"] * breakdown["preco_unit_atual"]
    # Join product name for display
    breakdown = breakdown.merge(
        produtos[["id", "nome"]].rename(columns={"id": "produto_id", "nome": "produto_nome"}),
        on="produto_id", how="left"
    )
    custo_receita = breakdown["custo_na_receita"].sum()
    return custo_receita / rendimento, breakdown


def calc_custo_embalagem_unid(tamanho_id: str) -> tuple[float, pd.DataFrame]:
    """Cost of packaging per unit. Returns (custo, dataframe_with_breakdown)."""
    emb = get_embalagens_por_tamanho()
    compras = get_compras()
    produtos = get_produtos()

    sub = emb[emb["tamanho_id"] == tamanho_id].copy()
    if sub.empty:
        return 0.0, sub
    sub["preco_unit_atual"] = sub["produto_id"].apply(lambda p: latest_unit_price(p, compras))
    sub["custo_por_unidade"] = sub["qtde_por_unidade"] * sub["preco_unit_atual"]
    sub = sub.merge(
        produtos[["id", "nome"]].rename(columns={"id": "produto_id", "nome": "produto_nome"}),
        on="produto_id", how="left"
    )
    return sub["custo_por_unidade"].sum(), sub


def get_tamanho_costs() -> pd.DataFrame:
    """Returns Tamanhos with computed custo_alimento, custo_embalagem, custo_total, lucro, margem."""
    t = get_tamanhos().copy()
    if t.empty:
        return t
    rows = []
    for _, row in t.iterrows():
        custo_ali, _ = calc_custo_alimento_unid(row["id"])
        custo_emb, _ = calc_custo_embalagem_unid(row["id"])
        custo_total = custo_ali + custo_emb
        preco = float(row.get("preco_venda") or 0) if pd.notna(row.get("preco_venda")) else 0
        lucro = preco - custo_total if preco > 0 else None
        margem = (lucro / preco) if (lucro is not None and preco > 0) else None
        rows.append({
            "id": row["id"],
            "nome": row["nome"],
            "peso_kg": row.get("peso_kg"),
            "volume_ml": row.get("volume_ml"),
            "rendimento": row.get("rendimento"),
            "canal": row.get("canal"),
            "custo_alimento": custo_ali,
            "custo_embalagem": custo_emb,
            "custo_total": custo_total,
            "preco_venda": preco if preco > 0 else None,
            "lucro": lucro,
            "margem": margem,
        })
    return pd.DataFrame(rows)
