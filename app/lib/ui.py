"""Reusable Streamlit UI helpers."""

import streamlit as st


# Brand color palette
PURPLE = "#5C2D7A"
PURPLE_DARK = "#3F1E55"
CARAMEL = "#B07842"
CARAMEL_LIGHT = "#C99860"
CREAM = "#FFF9F0"
BEIGE = "#F1E3CB"
DARK_BROWN = "#2D1810"


# Custom CSS — applied to every page via setup_page
_BRAND_CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,400;9..144,700;9..144,900&family=Outfit:wght@400;500;600;700&display=swap');

/* Base typography */
html, body, [class*="css"], .stMarkdown, p, label, div {{
    font-family: 'Outfit', system-ui, sans-serif !important;
}}

/* Headings — retro serif */
h1, h2, h3, .stMarkdown h1, .stMarkdown h2, .stMarkdown h3 {{
    font-family: 'Fraunces', serif !important;
    font-weight: 700 !important;
    color: {PURPLE_DARK} !important;
    letter-spacing: -0.02em;
}}

h1 {{
    font-weight: 900 !important;
    font-size: 2.4rem !important;
}}

/* Top decorative bar */
[data-testid="stAppViewContainer"]::before {{
    content: "";
    display: block;
    height: 8px;
    background: linear-gradient(90deg, {PURPLE} 0%, {CARAMEL} 50%, {PURPLE} 100%);
}}

/* Sidebar */
[data-testid="stSidebar"] {{
    background-color: {BEIGE} !important;
    border-right: 2px solid {CARAMEL_LIGHT};
}}

[data-testid="stSidebar"] h1, [data-testid="stSidebar"] h2 {{
    color: {PURPLE_DARK} !important;
}}

/* Buttons */
.stButton > button {{
    border-radius: 24px !important;
    border: 2px solid {PURPLE} !important;
    background-color: {CREAM} !important;
    color: {PURPLE} !important;
    font-weight: 600 !important;
    transition: all 0.15s ease;
}}

.stButton > button:hover {{
    background-color: {PURPLE} !important;
    color: {CREAM} !important;
}}

.stButton > button[kind="primary"] {{
    background-color: {PURPLE} !important;
    color: {CREAM} !important;
}}

.stButton > button[kind="primary"]:hover {{
    background-color: {PURPLE_DARK} !important;
}}

/* Metric cards */
[data-testid="stMetric"] {{
    background-color: {CREAM};
    border: 1px solid {CARAMEL_LIGHT};
    border-radius: 12px;
    padding: 1rem;
}}

[data-testid="stMetricLabel"] {{
    color: {CARAMEL} !important;
    font-weight: 600 !important;
}}

[data-testid="stMetricValue"] {{
    color: {PURPLE_DARK} !important;
    font-family: 'Fraunces', serif !important;
    font-weight: 700 !important;
}}

/* Bordered containers as "cards" */
div[data-testid="stContainer"] > div > div:has(> div[data-testid="stVerticalBlock"]) {{
    border-radius: 12px;
}}

/* Tabs */
.stTabs [data-baseweb="tab-list"] {{
    gap: 4px;
}}

.stTabs [data-baseweb="tab"] {{
    background-color: {BEIGE};
    border-radius: 12px 12px 0 0;
    font-weight: 600;
}}

.stTabs [aria-selected="true"] {{
    background-color: {PURPLE} !important;
    color: {CREAM} !important;
}}

/* Dataframes — softer */
[data-testid="stDataFrame"] {{
    border-radius: 12px;
    overflow: hidden;
}}

/* Info / warning / success boxes */
[data-baseweb="notification"] {{
    border-radius: 12px !important;
}}
</style>
"""


def setup_page(title: str, icon: str = "🍮") -> None:
    """Standard page header + brand styling. Call once at the top of each page."""
    st.set_page_config(
        page_title=f"{title} — Pudim Caramelo",
        page_icon=icon,
        layout="wide",
        initial_sidebar_state="expanded",
    )
    st.markdown(_BRAND_CSS, unsafe_allow_html=True)


def brand_header(title: str, subtitle: str = "") -> None:
    """Decorative header for the home page with the retro vibe."""
    st.markdown(
        f"""
        <div style="
            background: linear-gradient(135deg, {BEIGE} 0%, {CREAM} 100%);
            border: 3px solid {PURPLE};
            border-radius: 20px;
            padding: 2rem;
            text-align: center;
            margin-bottom: 1.5rem;
            box-shadow: 0 4px 16px rgba(92, 45, 122, 0.1);
        ">
            <div style="font-size: 4rem; line-height: 1;">🍮</div>
            <h1 style="
                font-family: 'Fraunces', serif !important;
                font-weight: 900;
                font-size: 3rem !important;
                color: {PURPLE_DARK};
                margin: 0.5rem 0 0 0;
                letter-spacing: -0.02em;
            ">{title}</h1>
            {f'<p style="color: {CARAMEL}; font-weight: 500; margin-top: 0.5rem; font-size: 1.1rem;">{subtitle}</p>' if subtitle else ''}
        </div>
        """,
        unsafe_allow_html=True,
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
