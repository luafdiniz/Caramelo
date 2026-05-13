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


# Subtle wavy SVG pattern (caramel waves, very low opacity) — evokes the brand's swirl background
_WAVE_SVG = (
    "data:image/svg+xml;utf8,"
    "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 800 200'>"
    "<defs><linearGradient id='g' x1='0' x2='1'>"
    f"<stop offset='0' stop-color='{CARAMEL}' stop-opacity='0.08'/>"
    f"<stop offset='1' stop-color='{CARAMEL}' stop-opacity='0.04'/>"
    "</linearGradient></defs>"
    "<path d='M0,100 C 200,40 400,160 600,100 S 800,100 800,100 L 800,200 L 0,200 Z' fill='url(%23g)'/>"
    "<path d='M0,140 C 200,80 400,200 600,140 S 800,140 800,140 L 800,200 L 0,200 Z' fill='url(%23g)'/>"
    "</svg>"
).replace("#", "%23")


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
    font-size: 2.6rem !important;
    line-height: 1.05 !important;
}}

h2 {{
    font-weight: 800 !important;
    color: {PURPLE} !important;
}}

/* Caption text — darker for readability against cream */
.stCaption, [data-testid="stCaptionContainer"],
[data-testid="stCaptionContainer"] p,
[data-testid="stCaptionContainer"] span,
small, p.caption {{
    color: {CARAMEL} !important;
    font-weight: 500 !important;
    opacity: 1 !important;
}}

/* Make sure bold markdown inside captions still bold */
[data-testid="stCaptionContainer"] strong,
[data-testid="stCaptionContainer"] b {{
    color: {PURPLE_DARK} !important;
    font-weight: 700 !important;
}}

/* Form inputs — force light theme regardless of system preference */
.stTextInput input, .stTextArea textarea, .stNumberInput input,
.stDateInput input, .stTimeInput input,
[data-baseweb="input"] input, [data-baseweb="textarea"] textarea,
[data-baseweb="select"] > div {{
    background-color: {CREAM} !important;
    color: {DARK_BROWN} !important;
    border: 1px solid {CARAMEL_LIGHT} !important;
}}

.stSelectbox > div > div {{
    background-color: {CREAM} !important;
}}

.stSelectbox > div > div * {{
    color: {DARK_BROWN} !important;
}}

/* Multiselect tags */
[data-baseweb="tag"] {{
    background-color: {PURPLE} !important;
    color: {CREAM} !important;
    border-radius: 12px !important;
}}

[data-baseweb="tag"] span {{
    color: {CREAM} !important;
}}

/* Labels above inputs */
[data-testid="stWidgetLabel"],
[data-testid="stWidgetLabel"] *,
.stTextInput label, .stNumberInput label, .stDateInput label,
.stSelectbox label, .stMultiSelect label, .stTextArea label,
.stCheckbox label, .stRadio label {{
    color: {PURPLE_DARK} !important;
    font-weight: 600 !important;
    opacity: 1 !important;
}}

/* Help text below labels */
[data-testid="stWidgetLabelHelp"] {{
    color: {CARAMEL} !important;
}}

/* Code-style chips (used for IDs like TAM-001) */
code {{
    background-color: {PURPLE_DARK} !important;
    color: {CREAM} !important;
    padding: 2px 8px !important;
    border-radius: 6px !important;
    font-size: 0.85em !important;
    font-family: 'JetBrains Mono', monospace !important;
}}

/* Expander */
[data-testid="stExpander"] {{
    border: 1px solid {CARAMEL_LIGHT} !important;
    border-radius: 12px !important;
    background-color: rgba(255, 255, 255, 0.5) !important;
}}

[data-testid="stExpander"] summary {{
    color: {PURPLE} !important;
    font-weight: 600 !important;
}}

[data-testid="stExpander"] summary:hover {{
    color: {PURPLE_DARK} !important;
}}

/* Checkbox label text */
.stCheckbox > label > div:last-child {{
    color: {DARK_BROWN} !important;
}}

/* Force cream background and wavy texture — overrides dark mode preference */
.stApp, [data-testid="stAppViewContainer"] {{
    background-color: {CREAM} !important;
    background-image: url("{_WAVE_SVG}");
    background-repeat: repeat;
    background-size: 600px auto;
    background-attachment: fixed;
}}

[data-testid="stHeader"] {{
    background-color: transparent !important;
}}

/* Main content area */
.main, [data-testid="block-container"] {{
    background-color: transparent !important;
}}

/* Top decorative bar */
[data-testid="stAppViewContainer"]::before {{
    content: "";
    display: block;
    height: 10px;
    background: linear-gradient(90deg, {PURPLE} 0%, {CARAMEL} 40%, {PURPLE} 70%, {CARAMEL} 100%);
    position: sticky;
    top: 0;
    z-index: 999;
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
.stButton > button, .stButton > button * {{
    border-radius: 24px !important;
    border: 2px solid {PURPLE} !important;
    background-color: {CREAM} !important;
    color: {PURPLE} !important;
    font-weight: 600 !important;
    transition: all 0.15s ease;
}}

.stButton > button:hover, .stButton > button:hover * {{
    background-color: {PURPLE} !important;
    color: {CREAM} !important;
    border-color: {PURPLE} !important;
}}

.stButton > button[kind="primary"], .stButton > button[kind="primary"] * {{
    background-color: {PURPLE} !important;
    color: {CREAM} !important;
}}

.stButton > button[kind="primary"]:hover, .stButton > button[kind="primary"]:hover * {{
    background-color: {PURPLE_DARK} !important;
}}

.stFormSubmitButton > button, .stFormSubmitButton > button * {{
    background-color: {PURPLE} !important;
    color: {CREAM} !important;
    border-radius: 24px !important;
    border: 2px solid {PURPLE_DARK} !important;
    font-weight: 600 !important;
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

/* Dataframes — force light theme */
[data-testid="stDataFrame"] {{
    border-radius: 12px;
    overflow: hidden;
    border: 1px solid {CARAMEL_LIGHT};
}}

[data-testid="stDataFrame"] * {{
    color: {DARK_BROWN} !important;
}}

[data-testid="stDataFrame"] [role="columnheader"] {{
    background-color: {BEIGE} !important;
    color: {PURPLE_DARK} !important;
    font-weight: 700 !important;
}}

[data-testid="stDataFrame"] [role="row"]:nth-child(even) {{
    background-color: rgba(241, 227, 203, 0.3) !important;
}}

/* Info / warning / success boxes — force readable text */
[data-baseweb="notification"], .stAlert {{
    border-radius: 12px !important;
}}

.stAlert, .stAlert p, .stAlert div, .stAlert span {{
    color: {DARK_BROWN} !important;
}}

[data-testid="stNotificationContentInfo"] {{
    background-color: rgba(92, 45, 122, 0.08) !important;
    color: {DARK_BROWN} !important;
}}

[data-testid="stNotificationContentSuccess"] {{
    background-color: rgba(176, 120, 66, 0.12) !important;
    color: {DARK_BROWN} !important;
}}

[data-testid="stNotificationContentWarning"] {{
    background-color: rgba(201, 152, 96, 0.15) !important;
    color: {DARK_BROWN} !important;
}}

/* Page links in main area — force ALL nested text to brand purple */
[data-testid="stPageLink"],
[data-testid="stPageLink"] *,
[data-testid="stPageLink"] a,
[data-testid="stPageLink"] a *,
[data-testid="stPageLink"] span,
[data-testid="stPageLink"] p,
[data-testid="stPageLink"] div {{
    color: {PURPLE} !important;
    font-weight: 600 !important;
}}

[data-testid="stPageLink"] {{
    background-color: rgba(241, 227, 203, 0.4) !important;
    border-radius: 10px !important;
    padding: 4px 12px !important;
    margin: 4px 0 !important;
    border-left: 3px solid {CARAMEL} !important;
}}

[data-testid="stPageLink"]:hover {{
    background-color: rgba(176, 120, 66, 0.18) !important;
}}

[data-testid="stPageLink"] a {{
    text-decoration: none !important;
}}

/* Sidebar nav links — force dark brown */
[data-testid="stSidebarNav"],
[data-testid="stSidebarNav"] *,
[data-testid="stSidebarNav"] a,
[data-testid="stSidebarNav"] a *,
[data-testid="stSidebarNav"] span,
section[data-testid="stSidebar"] a,
section[data-testid="stSidebar"] a *,
section[data-testid="stSidebar"] span {{
    color: {DARK_BROWN} !important;
    font-weight: 600 !important;
}}

section[data-testid="stSidebar"] a {{
    text-decoration: none !important;
}}

section[data-testid="stSidebar"] a:hover {{
    color: {PURPLE_DARK} !important;
}}

/* Plain links */
a {{
    color: {PURPLE} !important;
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
    """
    Decorative header for the home page with the retro vibe.

    Mimics the brand's double-border style (outer caramel, inner purple)
    over a cream interior.
    """
    st.markdown(
        f"""
        <div style="
            background: {CARAMEL};
            padding: 8px;
            border-radius: 24px;
            margin-bottom: 1.5rem;
            box-shadow: 0 6px 24px rgba(92, 45, 122, 0.15);
        ">
            <div style="
                background: {CREAM};
                border: 3px solid {PURPLE};
                border-radius: 18px;
                padding: 2.5rem 2rem;
                text-align: center;
            ">
                <div style="font-size: 4.5rem; line-height: 1; margin-bottom: 0.5rem;">🍮</div>
                <h1 style="
                    font-family: 'Fraunces', serif !important;
                    font-weight: 900 !important;
                    font-size: 3.2rem !important;
                    color: {PURPLE_DARK} !important;
                    margin: 0 !important;
                    letter-spacing: -0.03em;
                    line-height: 1;
                ">{title}</h1>
                {f'<p style="color: {CARAMEL}; font-weight: 600; margin-top: 0.75rem; font-size: 1.05rem; letter-spacing: 0.02em;">{subtitle}</p>' if subtitle else ''}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def brl(value) -> str:
    """
    Format a number as BRL currency. Handles None/NaN.

    Returns 'R$ X,YZ' (plain). Use in: dataframes, st.metric value, st.text.
    For markdown contexts (st.caption, st.markdown, f-strings in st.write),
    use brl_md() instead — Streamlit treats `$...$` as LaTeX math.
    """
    if value is None:
        return "—"
    try:
        return f"R$ {float(value):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except (TypeError, ValueError):
        return "—"


def brl_md(value) -> str:
    """BRL formatted with the `$` escaped — safe for markdown/caption contexts."""
    return brl(value).replace("$", r"\$")


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
