"""Pruebas de lógica de negocio (compatibles con pytest; también: python -m tests.test_core)."""
import os, sys, tempfile
from datetime import date


def _fresh():
    os.environ["JD_DATA_DIR"] = tempfile.mkdtemp()
    for m in [m for m in sys.modules if m.split(".")[0] in ("services", "core", "documents")]:
        del sys.modules[m]
    from core.database import init_db
    init_db()


def test_money_and_vat():
    _fresh()
    from core.utils import split_vat, to_cents
    assert to_cents("12,50") == 1250
    base, vat = split_vat(6000, 21)
    assert base + vat == 6000 and vat == 1041


def test_invoice_chain_and_rectify():
    _fresh()
    from core.database import execute
    from services import billing
    inv = billing.create_invoice([{"description": "Facial", "qty": 1, "unit_cents": 6000, "vat_rate": 21}],
                                 [{"method": "efectivo", "amount_cents": 6000}])
    assert billing.verify_chain()["ok"]
    billing.rectify_invoice(inv["id"], "Error de cobro")
    assert billing.verify_chain()["ok"]
    execute("UPDATE invoices SET total_cents = total_cents + 1 WHERE id = ?", (inv["id"],))
    assert not billing.verify_chain()["ok"]


def test_mixed_payment_must_match_total():
    _fresh()
    from services import billing
    try:
        billing.create_invoice([{"description": "X", "qty": 1, "unit_cents": 1000, "vat_rate": 21}],
                               [{"method": "efectivo", "amount_cents": 900}])
    except ValueError:
        return
    raise AssertionError("debería rechazar pagos que no suman el total")


def test_giftcard_and_taxes_and_backup():
    _fresh()
    from services import backup, giftcards, taxes
    g = giftcards.issue(5000, "efectivo", "A", "", "B", "", "", "", 12)
    assert giftcards.get(g["id"])["balance_cents"] == 5000
    assert taxes.iva_quarter(date.today().year, 1)["result_cents"] == 0
    assert backup.backup_db_bytes().startswith(b"SQLite format 3")
    assert backup.restore_db(backup.backup_db_bytes())["facturas"] == 0


def test_documents_render():
    _fresh()
    from services import giftcards
    from documents.giftcard import render_giftcard
    g = giftcards.issue(5000, "efectivo", "A", "", "B", "", "Hola", "", 12)
    assert render_giftcard(g, "Judit Domingo", "600000000", "Barcelona")[:4] == b"\x89PNG"


def test_assistant():
    _fresh()
    from services import assistant
    assert assistant.answer("¿en qué consiste la maderoterapia?").text


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn(); print("OK", name)
