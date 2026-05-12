"""Simple password gate for the Streamlit app."""

import os
import streamlit as st


def _expected_password() -> str:
    # On Streamlit Cloud: secrets via st.secrets. Locally: env var.
    try:
        return st.secrets["APP_PASSWORD"]
    except (KeyError, FileNotFoundError):
        return os.environ.get("APP_PASSWORD", "")


def require_auth() -> None:
    """
    Gate the page with a password prompt. Call at the top of each page.

    Sets st.session_state['authed'] to True once authenticated, so subsequent
    page loads in the same session skip the prompt.
    """
    expected = _expected_password()
    if not expected:
        # No password configured — leave open (useful for local dev).
        st.session_state["authed"] = True
        return

    if st.session_state.get("authed"):
        return

    st.title("🍮 Pudim Caramelo")
    st.markdown("##### Acesso restrito")
    with st.form("login"):
        pw = st.text_input("Senha", type="password", autocomplete="current-password")
        if st.form_submit_button("Entrar", use_container_width=True):
            if pw == expected:
                st.session_state["authed"] = True
                st.rerun()
            else:
                st.error("Senha incorreta")
    st.stop()
