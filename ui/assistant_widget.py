"""Asistente virtual flotante (burbuja) disponible en todas las secciones."""
from __future__ import annotations

import streamlit as st

from services import assistant

KEY = "bot_history"


def _ask(question: str) -> None:
    reply = assistant.answer(question)
    hist = st.session_state.setdefault(KEY, [])
    hist.append(("user", question, []))
    hist.append(("bot", reply.text, reply.suggestions))


@st.fragment
def _chat() -> None:
    hist = st.session_state.setdefault(KEY, [])
    if not hist:
        w = assistant.welcome()
        hist.append(("bot", w.text, w.suggestions))
    box = st.container(height=340)
    with box:
        for role, text, _ in hist:
            with st.chat_message("user" if role == "user" else "assistant", avatar="🙋‍♀️" if role == "user" else "✨"):
                st.markdown(text)
    last = hist[-1]
    if last[0] == "bot":
        for i, s in enumerate(last[2][:4]):
            if st.button(s, key=f"bot_sug_{len(hist)}_{i}", use_container_width=True):
                _ask(s)
                st.rerun(scope="fragment")
    with st.form("bot_form", clear_on_submit=True):
        q = st.text_input("Pregunta", placeholder="Escribe tu duda…", label_visibility="collapsed")
        if st.form_submit_button("Enviar", type="primary", use_container_width=True) and q.strip():
            _ask(q.strip())
            st.rerun(scope="fragment")
    if len(hist) > 1 and st.button("Limpiar conversación", key="bot_clear"):
        st.session_state[KEY] = []
        st.rerun(scope="fragment")


def render() -> None:
    with st.container(key="jd_bot"):
        with st.popover("✨ Asistente", use_container_width=False):
            _chat()
