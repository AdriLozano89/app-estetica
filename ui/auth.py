"""Pantalla de acceso (contraseña) y primera configuración."""
from __future__ import annotations

import streamlit as st

from core import security
from ui.components import html


def _brand_card() -> None:
    html(
        '<div style="text-align:center;margin:8vh 0 1.2rem"><div class="jd-brand-name" style="font-size:4rem">Judit Domingo</div>'
        '<div class="jd-brand-tag" style="padding:0">CENTRE D\'ESTÈTICA</div></div>'
    )


def require_login() -> bool:
    """Devuelve True si hay sesión iniciada; si no, dibuja el login y devuelve False."""
    if st.session_state.get("auth_ok"):
        return True
    _brand_card()
    _, mid, _ = st.columns([1, 1.4, 1])
    with mid:
        if security.needs_setup():
            st.info("Primer acceso: crea la contraseña con la que entrará el equipo.")
            with st.form("setup"):
                p1 = st.text_input("Nueva contraseña", type="password")
                p2 = st.text_input("Repite la contraseña", type="password")
                if st.form_submit_button("Guardar y entrar", type="primary", use_container_width=True):
                    err = security.password_strength_error(p1)
                    if err:
                        st.error(err)
                    elif p1 != p2:
                        st.error("Las contraseñas no coinciden.")
                    else:
                        security.set_password(p1)
                        st.session_state["auth_ok"] = True
                        st.rerun()
            st.caption("Consejo: si publicas la app en internet, define mejor el secreto APP_PASSWORD en el servidor.")
            return False
        throttle = st.session_state.setdefault("_login_throttle", {})
        locked, remaining = security.throttle_state(throttle)
        with st.form("login"):
            pw = st.text_input("Contraseña", type="password", placeholder="••••••••")
            submitted = st.form_submit_button("Entrar", type="primary", use_container_width=True, disabled=locked)
        if locked:
            st.warning(f"Demasiados intentos. Espera {remaining} s.")
        elif submitted:
            ok = security.verify_password(pw)
            security.register_attempt(throttle, ok)
            if ok:
                st.session_state["auth_ok"] = True
                st.rerun()
            st.error("Contraseña incorrecta.")
    return False


def logout() -> None:
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    st.rerun()
