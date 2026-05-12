"""Reusable Streamlit UI helpers."""

import streamlit as st


def setup_page(title: str, icon: str = "🍮") -> None:
    """Standard page header. Call once at the top of each page."""
    st.set_page_config(
        page_title=f"{title} — Pudim Caramelo",
        page_icon=icon,
        layout="wide",
        initial_sidebar_state="expanded",
    )


def brl(value) -> str:
    """Format a number as BRL currency. Handles None/NaN."""
    if value is None:
        return "—"
    try:
        return f"R$ {float(value):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except (TypeError, ValueError):
        return "—"


def pct(value) -> str:
    """Format a number as a percentage. Expects 0.10 for 10%."""
    if value is None:
        return "—"
    try:
        return f"{float(value) * 100:.1f}%".replace(".", ",")
    except (TypeError, ValueError):
        return "—"


def kpi(label: str, value: str, help: str = None) -> None:
    """A metric card."""
    st.metric(label, value, help=help)
