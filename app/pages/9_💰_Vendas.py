"""Vendas page: register sales + browse history."""

import os
import sys
from datetime import date
import streamlit as st
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.auth import require_auth
from lib import data
from lib.ui import setup_page, brl


setup_page("Vendas", icon="💰")
require_auth()

st.title("💰 Vendas")
st.caption("Registro de transações. O preço é resolvido pelas faixas em **Preços**, mas pode ser sobrescrito.")


def _next_ven_id(existing_ids: list[str]) -> str:
    max_n = 0
    for vid in existing_ids:
        if vid.startswith("VEN-"):
            try:
                n = int(vid.split("-")[1])
                max_n = max(max_n, n)
            except (ValueError, IndexError):
                continue
    return f"VEN-{max_n + 1:03d}"


vendas = data.get_vendas()
clientes = data.get_clientes()
tamanhos = data.get_tamanhos()

if not data._has_sheet("Vendas") or not data._has_sheet("Clientes"):
    st.warning(
        "Faltam as abas **Vendas/Clientes**. "
        "Rode `python scripts/migrate_clientes_vendas.py --apply`."
    )
    st.stop()


tab_nova, tab_hist = st.tabs(["➕ Nova venda", "📋 Histórico"])


with tab_nova:
    if clientes.empty:
        st.info("Cadastre pelo menos um cliente na página 👥 Clientes.")
        st.stop()
    if tamanhos.empty:
        st.info("Cadastre pelo menos um tamanho na página 🍮 Tamanhos.")
        st.stop()

    active_clientes = clientes[clientes["ativo"] == True]  # noqa: E712
    cli_opts = {f"{r['id']} — {r['nome']} ({r['tipo']})": r["id"]
                for _, r in active_clientes.iterrows()}
    tam_opts = {f"{r['id']} — {r['nome']}": r["id"]
                for _, r in tamanhos.iterrows()}

    c1, c2 = st.columns([2, 1])
    with c1:
        cli_label = st.selectbox("Cliente", list(cli_opts.keys()))
        cliente_id = cli_opts[cli_label]
    with c2:
        venda_data = st.date_input("Data", value=date.today())

    c3, c4, c5 = st.columns([2, 1, 1])
    with c3:
        tam_label = st.selectbox("Tamanho", list(tam_opts.keys()))
        tamanho_id = tam_opts[tam_label]
    with c4:
        qtde = st.number_input("Qtde", min_value=1, value=1, step=1)
    with c5:
        preco_resolvido = data.resolve_preco_unit(cliente_id, tamanho_id, int(qtde))
        st.caption(f"Sugerido: {brl(preco_resolvido) if preco_resolvido > 0 else '—'}")

    if preco_resolvido == 0:
        # Loud warning so the user doesn't silently register a R$ 0 sale.
        # The Registrar button stays disabled (further down) until they
        # type a positive value into the manual price input below.
        st.warning(
            "Não há preço cadastrado pra esta combinação cliente/tamanho/qtde. "
            "Digite o preço manualmente em **Preço unitário (R$)** abaixo."
        )

    preco_unit = st.number_input(
        "Preço unitário (R$)",
        min_value=0.0, value=float(preco_resolvido), step=1.0,
        help="Pré-preenchido pela tabela de Preços. Editável.",
    )

    c6, c7 = st.columns(2)
    with c6:
        forma_pgto = st.selectbox(
            "Forma de pagamento", ["Pix", "Dinheiro", "Cartão", "Boleto", "Fiado"],
        )
    with c7:
        status = st.selectbox("Status", ["entregue", "pendente", "cancelada"])

    notas = st.text_input("Notas (opcional)")

    preco_total = float(preco_unit) * int(qtde)

    cli_row = clientes[clientes["id"] == cliente_id]
    canal = cli_row.iloc[0]["tipo"] if not cli_row.empty else "B2C"

    custo_ali, _ = data.calc_custo_alimento_unid(tamanho_id)
    custo_emb, _ = data.calc_custo_embalagem_unid(tamanho_id)
    custo_unit_estimado = custo_ali + custo_emb
    lucro_estimado = (float(preco_unit) - custo_unit_estimado) * int(qtde)

    k1, k2, k3 = st.columns(3)
    k1.metric("Total", brl(preco_total))
    k2.metric("Custo estimado", brl(custo_unit_estimado * int(qtde)))
    k3.metric("Lucro estimado", brl(lucro_estimado))

    if st.button("💾 Registrar venda", type="primary", disabled=preco_unit <= 0):
        try:
            existing_ids = vendas["id"].astype(str).tolist() if not vendas.empty else []
            new_id = _next_ven_id(existing_ids)
            row = [
                new_id, venda_data.isoformat(), cliente_id, tamanho_id, int(qtde),
                float(preco_unit), preco_total, canal,
                forma_pgto, status, custo_unit_estimado, notas.strip(),
            ]
            data.get_service().spreadsheets().values().append(
                spreadsheetId=data._spreadsheet_id(),
                range="Vendas!A1",
                valueInputOption="USER_ENTERED",
                body={"values": [row]},
            ).execute()
            data.invalidate_cache()
            st.success(f"✅ Venda registrada: **{new_id}** — {brl(preco_total)}")
            st.balloons()
        except Exception as e:
            st.error(f"Erro ao registrar: {e}")


with tab_hist:
    if vendas.empty:
        st.info("Ainda não há vendas registradas.")
        st.stop()

    cli_map = dict(zip(clientes["id"], clientes["nome"])) if not clientes.empty else {}
    tam_map = dict(zip(tamanhos["id"], tamanhos["nome"])) if not tamanhos.empty else {}

    disp = vendas.copy().sort_values("data", ascending=False)
    disp["Cliente"] = disp["cliente_id"].map(lambda c: cli_map.get(c, c))
    disp["Tamanho"] = disp["tamanho_id"].map(lambda t: tam_map.get(t, t))
    disp["Data"] = disp["data"].dt.strftime("%d/%m/%Y")
    disp["Preço unit."] = disp["preco_unit_efetivo"].apply(brl)
    disp["Total"] = disp["preco_total"].apply(brl)
    disp["Lucro"] = ((disp["preco_unit_efetivo"] - disp["custo_unit_estimado"])
                     * disp["qtde"]).apply(lambda v: brl(v) if pd.notna(v) else "—")

    view = disp[["id", "Data", "Cliente", "Tamanho", "qtde",
                 "Preço unit.", "Total", "Lucro", "canal", "status"]].copy()
    view.columns = ["ID", "Data", "Cliente", "Tamanho", "Qtde",
                    "Preço unit.", "Total", "Lucro", "Canal", "Status"]

    # Read-only history — st.table for brand styling consistency with other pages.
    st.table(view.set_index("ID"))

    # Aggregates
    total_fat = float(vendas[vendas["status"] != "cancelada"]["preco_total"].sum())
    total_lucro = float(
        ((vendas["preco_unit_efetivo"] - vendas["custo_unit_estimado"]) * vendas["qtde"])
        [vendas["status"] != "cancelada"].sum()
    )
    k1, k2, k3 = st.columns(3)
    k1.metric("Vendas", str(len(vendas)))
    k2.metric("Faturamento total", brl(total_fat))
    k3.metric("Lucro total estimado", brl(total_lucro))
