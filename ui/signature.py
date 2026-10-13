"""Panel de firma táctil: componente HTML propio (sin npm) que devuelve la firma como PNG."""
from __future__ import annotations

import base64
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

_FRONTEND = Path(__file__).parent / "frontend" / "signature_pad"
MAX_BYTES = 600_000

try:
    _pad = components.declare_component("jd_signature_pad", path=str(_FRONTEND))
except Exception:  # entorno sin soporte de componentes: la app seguirá con firma escrita
    _pad = None


def decode_data_url(value) -> bytes | None:
    """'data:image/png;base64,....' → bytes PNG (None si no es válido o pesa demasiado)."""
    if not value or not isinstance(value, str) or not value.startswith("data:image/png;base64,"):
        return None
    try:
        data = base64.b64decode(value.split(",", 1)[1], validate=True)
    except (ValueError, base64.binascii.Error):
        return None
    return data if 0 < len(data) <= MAX_BYTES and data[:8] == b"\x89PNG\r\n\x1a\n" else None


def signature_pad(key: str) -> bytes | None:
    """Dibuja el panel y devuelve los bytes del PNG cuando la clienta pulsa «Usar esta firma»."""
    if _pad is None:
        st.caption("El panel de firma no está disponible en este entorno; se usará el nombre escrito.")
        return None
    return decode_data_url(_pad(key=key, default=None))
