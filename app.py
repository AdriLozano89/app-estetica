"""Judit Domingo · Centre d'Estètica — punto de entrada de la aplicación.

Arranque:  streamlit run app.py
"""
from __future__ import annotations

import streamlit as st

st.set_page_config(page_title="Judit Domingo · Centre d'Estètica", page_icon="✨", layout="wide", initial_sidebar_state="collapsed")

from core.database import init_db  # noqa: E402
from core.utils import fmt_long_date, today  # noqa: E402
from ui import assistant_widget, auth, dialogs, theme  # noqa: E402
from ui import components as ui  # noqa: E402
from ui.pages import agenda, ajustes, analitica, caja, clientes, marketing  # noqa: E402

PAGES = {
    "agenda": ("Agenda", agenda),
    "caja": ("Caja", caja),
    "clientes": ("Clientes", clientes),
    "marketing": ("Marketing", marketing),
    "analitica": ("Analítica", analitica),
    "ajustes": ("Ajustes", ajustes),
}


@st.cache_resource(show_spinner=False)
def _boot() -> bool:
    init_db()
    return True


def main() -> None:
    theme.inject()
    _boot()
    if not auth.require_login():
        return

    # Cambio de sección pedido desde otro punto (debe resolverse ANTES de crear el selector).
    target = st.session_state.pop("_goto", None)
    if target in PAGES:
        st.session_state["nav"] = target
        st.session_state["_nav_last"] = target

    with st.container(key="jd_header"):
        left, right = st.columns([5, 2], vertical_alignment="center")
        left.markdown('<div class="jd-brand"><div class="jd-brand-name">Judit Domingo</div><div class="jd-brand-tag">CENTRE D\'ESTÈTICA</div></div>',
                      unsafe_allow_html=True)
        with right:
            st.caption(fmt_long_date(today()).capitalize())
            if st.button("Salir", key="logout", use_container_width=True):
                auth.logout()

    with st.container(key="jd_nav"):
        page = ui.choice("Sección", list(PAGES), key="nav", default="agenda", format_func=lambda k: PAGES[k][0])

    dialogs.dispatch()
    PAGES[page][1].render()
    assistant_widget.render()


main()
