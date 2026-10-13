"""Streamlit falso para pruebas de humo: permite ejecutar render() de cada página sin servidor."""
from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock


class State(dict):
    __getattr__ = dict.get

    def __setattr__(self, k, v):
        self[k] = v


_ST = None


class Ctx:
    """Contexto (columna, pestaña…): cualquier método se delega en el Streamlit falso."""

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def __getattr__(self, name):
        return getattr(_ST, name)


def install() -> types.ModuleType:
    global _ST
    st = _ST = MagicMock(name="streamlit")
    st.session_state = State()
    st.secrets = {}
    st.context.headers = {}

    def columns(spec, **kw):
        n = spec if isinstance(spec, int) else len(spec)
        return [Ctx() for _ in range(n)]

    def passthrough(*a, **k):
        if a and callable(a[0]):
            return a[0]
        return lambda f: f

    st.columns.side_effect = columns
    st.tabs.side_effect = lambda labels: [Ctx() for _ in labels]
    st.container.side_effect = lambda *a, **k: Ctx()
    st.expander.side_effect = lambda *a, **k: Ctx()
    st.popover.side_effect = lambda *a, **k: Ctx()
    st.form.side_effect = lambda *a, **k: Ctx()
    st.spinner.side_effect = lambda *a, **k: Ctx()
    st.chat_message.side_effect = lambda *a, **k: Ctx()
    st.button.return_value = False
    st.form_submit_button.return_value = False
    st.checkbox.return_value = False
    st.download_button.return_value = False
    st.text_input.return_value = ""
    st.text_area.return_value = ""
    st.file_uploader.return_value = None
    st.dialog = passthrough
    st.fragment = passthrough
    st.cache_resource = passthrough
    st.cache_data = passthrough
    st.segmented_control.side_effect = lambda label, options, **k: st.session_state.get(k.get("key")) or (options[0] if k.get("default") is None else k["default"])
    st.selectbox.side_effect = lambda label, options, index=0, **k: list(options)[index] if len(list(options)) else None
    st.multiselect.side_effect = lambda label, options, default=None, **k: list(default or [])
    st.slider.side_effect = lambda label, a, b, v=None, **k: v if v is not None else a
    st.number_input.side_effect = lambda label, a=0, b=0, v=0, **k: v
    st.date_input.side_effect = lambda label, value=None, **k: value
    st.time_input.side_effect = lambda label, value=None, **k: value
    st.data_editor.side_effect = lambda df, **k: df
    sys.modules["streamlit"] = st
    comp = types.ModuleType("streamlit.components")
    v1 = MagicMock(name="components.v1")
    comp.v1 = v1
    sys.modules["streamlit.components"] = comp
    sys.modules["streamlit.components.v1"] = v1
    st.components = comp
    return st
