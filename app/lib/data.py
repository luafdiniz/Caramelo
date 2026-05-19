"""
Cached data access layer for the Streamlit app.

Reuses bot/lib/sheets.py for I/O. Caches reads for 30 seconds — fresh enough
for a personal admin tool, slow enough to avoid hammering the API.

After any write, call invalidate_cache() to force a reload.
"""

import os
import json
import importlib.util
from typing import Optional
import streamlit as st
import pandas as pd

# Load bot/lib/sheets.py via importlib to avoid namespace collision with app/lib
# (both packages are named 'lib' which confuses Python's import system).
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_SHEETS_PATH = os.path.join(REPO_ROOT, "bot", "lib", "sheets.py")


def _load_bot_sheets():
    spec = importlib.util.spec_from_file_location("bot_sheets", _SHEETS_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_sheets = _load_bot_sheets()


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


def get_sheet_id(sheet_name: str) -> int:
    """Find the numeric sheetId for a tab by its title (needed for batchUpdate)."""
    service = get_service()
    meta = service.spreadsheets().get(spreadsheetId=_spreadsheet_id()).execute()
    for s in meta["sheets"]:
        if s["properties"]["title"] == sheet_name:
            return s["properties"]["sheetId"]
    raise ValueError(f"Sheet {sheet_name!r} not found")


def delete_row(sheet_name: str, row_num: int) -> None:
    """Delete a single row (1-indexed) from the given sheet."""
    service = get_service()
    sheet_id = get_sheet_id(sheet_name)
    service.spreadsheets().batchUpdate(
        spreadsheetId=_spreadsheet_id(),
        body={
            "requests": [{
                "deleteDimension": {
                    "range": {
                        "sheetId": sheet_id,
                        "dimension": "ROWS",
                        "startIndex": row_num - 1,
                        "endIndex": row_num,
                    }
                }
            }]
        },
    ).execute()


def find_row_by_id(sheet_name: str, item_id: str) -> int:
    """Find the 1-indexed row number where column A == item_id."""
    service = get_service()
    result = service.spreadsheets().values().get(
        spreadsheetId=_spreadsheet_id(), range=f"{sheet_name}!A:A"
    ).execute()
    rows = result.get("values", [])
    for i, r in enumerate(rows):
        if r and r[0] == item_id:
            return i + 1
    raise ValueError(f"{item_id} not found in {sheet_name}")


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
    # Range extended to column I to pick up the optional `receita_id` added by
    # the receitas migration. If the column isn't there yet, the row stays
    # padded with "" and `receita_id` falls back to the padrao at calc time.
    result = service.spreadsheets().values().get(
        spreadsheetId=_spreadsheet_id(), range="Tamanhos!A2:I",
        valueRenderOption="UNFORMATTED_VALUE",
    ).execute()
    rows = result.get("values", [])
    cols = ["id", "nome", "peso_kg", "volume_ml", "rendimento", "canal", "preco_venda", "notas", "receita_id"]
    if not rows:
        return pd.DataFrame(columns=cols)
    # Pad/truncate each row to exactly len(cols)
    rows = [(r + [""] * len(cols))[:len(cols)] for r in rows]
    df = pd.DataFrame(rows, columns=cols)
    for col in ("peso_kg", "volume_ml", "rendimento", "preco_venda"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def _parse_sheets_date(value) -> pd.Timestamp:
    """
    Parse a Google Sheets date value.

    With valueRenderOption=UNFORMATTED_VALUE, Sheets returns dates as serial
    numbers (days since 1899-12-30). Plain strings still come as strings.
    """
    if value is None or value == "":
        return pd.NaT
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return pd.to_datetime(value, unit="D", origin="1899-12-30")
    try:
        return pd.to_datetime(value)
    except (ValueError, TypeError):
        return pd.NaT


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
    rows = [r + [""] * (len(cols) - len(r)) for r in rows]
    df = pd.DataFrame(rows, columns=cols)
    df["data"] = df["data"].apply(_parse_sheets_date)
    for col in ("qtde_embalagens", "unidades_por_embalagem", "total_unidades", "preco_total", "preco_unitario"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


# --- Receitas (new schema) --------------------------------------------------
# Schema v2: a Receitas tab lists named recipes (REC-NNN), and a
# Receita_Ingredientes tab holds their ingredients keyed by (receita_id,
# produto_id) plus a `componente` ("calda" or "massa"). One receita in
# Receitas carries padrao=TRUE — that's the fallback when a Tamanho has
# no receita_id of its own.
#
# Pre-migration shim: if Receita_Ingredientes does not exist yet, we silently
# fall back to reading the legacy `Receita` tab and synthesizing a single
# REC-001 receita. This keeps the app running before
# `scripts/migrate_receitas.py --apply` is executed. Delete the shim once
# the migration has run everywhere.


def _has_sheet(sheet_name: str) -> bool:
    """True if a tab with this exact title exists. Used for the migration shim."""
    service = get_service()
    meta = service.spreadsheets().get(spreadsheetId=_spreadsheet_id()).execute()
    return any(s["properties"]["title"] == sheet_name for s in meta["sheets"])


@st.cache_data(ttl=CACHE_TTL_SECONDS)
def get_receitas() -> pd.DataFrame:
    """Return the Receitas tab. Empty DF with the right columns if missing.

    Columns: receita_id | nome | padrao | notas
    `padrao` is normalized to a Python bool (TRUE/true/1/sim -> True).
    """
    cols = ["receita_id", "nome", "padrao", "notas"]
    if not _has_sheet("Receitas"):
        return pd.DataFrame(columns=cols)
    service = get_service()
    result = service.spreadsheets().values().get(
        spreadsheetId=_spreadsheet_id(), range="Receitas!A2:D",
        valueRenderOption="UNFORMATTED_VALUE",
    ).execute()
    rows = result.get("values", [])
    if not rows:
        return pd.DataFrame(columns=cols)
    rows = [r + [""] * (len(cols) - len(r)) for r in rows]
    df = pd.DataFrame(rows, columns=cols)

    def _to_bool(v):
        if isinstance(v, bool):
            return v
        s = str(v).strip().lower()
        return s in ("true", "verdadeiro", "1", "sim", "x", "yes")

    df["padrao"] = df["padrao"].apply(_to_bool)
    # Drop rows with no receita_id (defensive against blank trailing rows)
    df = df[df["receita_id"].astype(str).str.strip() != ""]
    return df.reset_index(drop=True)


@st.cache_data(ttl=CACHE_TTL_SECONDS)
def get_receita_ingredientes(receita_id: Optional[str] = None) -> pd.DataFrame:
    """
    Return ingredient rows for one or all receitas.

    New-schema columns: receita_id | produto_id | nome | qtde | unidade | componente

    If the Receita_Ingredientes tab does not yet exist, transparently fall
    back to reading the legacy `Receita` tab and synthesize
    `receita_id="REC-001"` with `componente=""`. This shim keeps existing
    pages working before the migration runs.
    """
    cols = ["receita_id", "produto_id", "nome", "qtde", "unidade", "componente"]

    if _has_sheet("Receita_Ingredientes"):
        service = get_service()
        result = service.spreadsheets().values().get(
            spreadsheetId=_spreadsheet_id(), range="Receita_Ingredientes!A2:F",
            valueRenderOption="UNFORMATTED_VALUE",
        ).execute()
        rows = result.get("values", [])
        if not rows:
            df = pd.DataFrame(columns=cols)
        else:
            rows = [r + [""] * (len(cols) - len(r)) for r in rows]
            df = pd.DataFrame(rows, columns=cols)
            df["qtde"] = pd.to_numeric(df["qtde"], errors="coerce")
            df = df[df["produto_id"].astype(str).str.strip() != ""].reset_index(drop=True)
    else:
        # Transition shim: read the old Receita tab and synthesize REC-001.
        # Safe to delete after `scripts/migrate_receitas.py --apply` has run.
        service = get_service()
        result = service.spreadsheets().values().get(
            spreadsheetId=_spreadsheet_id(), range="Receita!A2:D",
            valueRenderOption="UNFORMATTED_VALUE",
        ).execute()
        rows = result.get("values", [])
        if not rows:
            df = pd.DataFrame(columns=cols)
        else:
            old_cols = ["produto_id", "nome", "qtde", "unidade"]
            rows = [r + [""] * (len(old_cols) - len(r)) for r in rows]
            df = pd.DataFrame(rows, columns=old_cols)
            df["qtde"] = pd.to_numeric(df["qtde"], errors="coerce")
            df = df[df["produto_id"].astype(str).str.strip() != ""].reset_index(drop=True)
            df["receita_id"] = "REC-001"
            df["componente"] = ""
            df = df[cols]

    if receita_id is not None:
        df = df[df["receita_id"] == receita_id].reset_index(drop=True)
    return df


def get_receita() -> pd.DataFrame:
    """
    Back-compat wrapper returning the legacy Receita shape.

    Columns: produto_id | nome | qtde | unidade

    Equivalent to ingredients of the padrao receita (or all of them if no
    padrao is marked). Kept so older callers — and the pre-migration shim
    inside `calc_custo_alimento_unid` — don't break.
    """
    cols = ["produto_id", "nome", "qtde", "unidade"]
    receitas = get_receitas()
    if not receitas.empty:
        padrao = receitas[receitas["padrao"]]
        receita_id = padrao.iloc[0]["receita_id"] if not padrao.empty else receitas.iloc[0]["receita_id"]
        ing = get_receita_ingredientes(receita_id)
    else:
        ing = get_receita_ingredientes()
    if ing.empty:
        return pd.DataFrame(columns=cols)
    return ing[cols].copy()


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
    df["data_inicio"] = df["data_inicio"].apply(_parse_sheets_date)
    df["data_fim"] = df["data_fim"].apply(_parse_sheets_date)
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


def resolve_receita_id_for_tamanho(tamanho_row) -> Optional[str]:
    """
    Pick the receita_id a tamanho should use.

    Priority:
      1. The tamanho's own `receita_id` column, if present and non-empty.
      2. The receita marked `padrao=TRUE` in Receitas.
      3. The first receita in Receitas (defensive fallback).
      4. "REC-001" — pre-migration shim (matches the synthesized id used
         by `get_receita_ingredientes` when Receita_Ingredientes is missing).

    Accepts either a pandas Series (single row) or a dict-like.
    Returns the receita_id string, or None if there are no receitas at all.
    """
    explicit = None
    try:
        explicit = tamanho_row.get("receita_id") if hasattr(tamanho_row, "get") else tamanho_row["receita_id"]
    except (KeyError, IndexError, TypeError):
        explicit = None
    if explicit is not None and str(explicit).strip() not in ("", "nan", "None"):
        return str(explicit).strip()

    receitas = get_receitas()
    if not receitas.empty:
        padrao = receitas[receitas["padrao"]]
        if not padrao.empty:
            return str(padrao.iloc[0]["receita_id"])
        return str(receitas.iloc[0]["receita_id"])

    # Pre-migration shim: no Receitas tab yet. The ingredientes loader
    # synthesizes REC-001 from the legacy Receita tab, so match that id.
    return "REC-001"


def calc_custo_alimento_unid(tamanho_id: str) -> tuple[float, pd.DataFrame]:
    """
    Cost of ingredients per unit of pudim.
    Returns (custo_por_unidade, dataframe_with_breakdown).

    The receita used is picked via `resolve_receita_id_for_tamanho` — the
    tamanho's explicit receita_id when set, else the receita marked padrao,
    else the synthesized REC-001 (pre-migration).
    """
    tamanhos = get_tamanhos()
    compras = get_compras()
    produtos = get_produtos()

    t = tamanhos[tamanhos["id"] == tamanho_id]
    if t.empty:
        return 0.0, pd.DataFrame()
    rendimento = float(t.iloc[0]["rendimento"] or 1)

    receita_id = resolve_receita_id_for_tamanho(t.iloc[0])
    receita = get_receita_ingredientes(receita_id) if receita_id else get_receita_ingredientes()

    breakdown = receita.copy()
    if breakdown.empty:
        return 0.0, breakdown
    breakdown["preco_unit_atual"] = breakdown["produto_id"].apply(lambda p: latest_unit_price(p, compras))
    breakdown["custo_na_receita"] = breakdown["qtde"] * breakdown["preco_unit_atual"]
    # Join product name for display. `nome` may already exist in the
    # ingredientes table; we suffix the joined column to avoid clobbering and
    # then prefer the produto's canonical name when available.
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
            "receita_id": row.get("receita_id") or "",
            "custo_alimento": custo_ali,
            "custo_embalagem": custo_emb,
            "custo_total": custo_total,
            "preco_venda": preco if preco > 0 else None,
            "lucro": lucro,
            "margem": margem,
        })
    return pd.DataFrame(rows)
