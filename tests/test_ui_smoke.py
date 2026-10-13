"""Cada página debe poder dibujarse sobre una base de datos con datos, sin excepciones."""
import importlib
import sys
from datetime import timedelta

import pytest

from tests import fake_streamlit


@pytest.fixture()
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("JD_DATA_DIR", str(tmp_path))
    for m in [m for m in sys.modules if m.split(".")[0] in ("ui", "services", "core", "documents")]:
        del sys.modules[m]
    st = fake_streamlit.install()
    from core.database import init_db
    init_db()
    from core.utils import now
    from services import appointments, catalog, clients, giftcards
    cid = clients.create_client("Ana", "López", "612345678", birthdate=now().date().replace(year=1990))
    svc = catalog.list_services()[0]
    start = now().replace(hour=11, minute=0, second=0, microsecond=0)
    try:
        appointments.create_appointment(cid, svc["id"], start)
    except Exception:
        pass
    giftcards.issue(5000, "efectivo", "Luis", "600111222", "Ana", "612345678", "Feliz día", "", 12)
    return st


@pytest.mark.parametrize("page", ["agenda", "caja", "clientes", "marketing", "analitica", "ajustes"])
def test_page_renders(env, page):
    mod = importlib.import_module(f"ui.pages.{page}")
    mod.render()


def test_assistant_widget(env):
    importlib.import_module("ui.assistant_widget").render()
