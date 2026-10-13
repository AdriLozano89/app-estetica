"""Ejecuta render() de cada página sobre una BD con datos (sin pytest):  python -m tests.smoke_runner"""
import importlib, os, sys, tempfile, traceback

from tests import fake_streamlit

PAGES = ["ui.pages.agenda", "ui.pages.caja", "ui.pages.clientes", "ui.pages.marketing", "ui.pages.analitica",
         "ui.pages.ajustes", "ui.assistant_widget"]


def seed():
    from core.database import init_db
    init_db()
    from core.utils import now
    from services import appointments, billing, catalog, clients, giftcards
    cid = clients.create_client("Ana", "López", "612345678", birthdate=now().date().replace(year=1990))
    svc = catalog.list_services()[0]
    start = now().replace(hour=11, minute=0, second=0, microsecond=0)
    appointments.create(cid, svc["id"], start)
    giftcards.issue(5000, "efectivo", "Luis", "600111222", "Ana", "612345678", "Feliz día", "", 12)
    billing.create_invoice([{"service_id": svc["id"], "description": svc["name"], "qty": 1, "unit_cents": svc["price_cents"], "vat_rate": svc["vat_rate"]}],
                           [{"method": "efectivo", "amount_cents": svc["price_cents"]}], client_id=cid)


def main() -> int:
    bad = 0
    for page in PAGES:
        os.environ["JD_DATA_DIR"] = tempfile.mkdtemp()
        for m in [m for m in sys.modules if m.split(".")[0] in ("ui", "services", "core", "documents")]:
            del sys.modules[m]
        fake_streamlit.install()
        try:
            seed()
            importlib.import_module(page).render()
            print("OK  ", page)
        except Exception:
            bad += 1
            print("FAIL", page)
            traceback.print_exc(limit=-4)
    return bad


if __name__ == "__main__":
    sys.exit(main())
