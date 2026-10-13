"""Gastos del centro: base de cálculo del IVA soportado (Modelo 303) y de los gastos deducibles (Modelo 130)."""
from __future__ import annotations

from datetime import date

from core.database import audit, execute, fetch_all
from core.utils import now, parse_date, split_vat, today

METHODS = {"efectivo": "Efectivo", "tarjeta": "Tarjeta", "bizum": "Bizum", "banco": "Banco / transferencia"}

CATEGORIES = (
    "Productos y cosmética",
    "Material fungible",
    "Alquiler del local",
    "Suministros (luz, agua, internet)",
    "Equipamiento y mobiliario",
    "Formación",
    "Publicidad y marketing",
    "Seguros",
    "Cuota de autónomos",
    "Gestoría y asesoría",
    "Software y suscripciones",
    "Otros",
)


def add_expense(concept: str, total_cents: int, vat_rate: int = 21, expense_date: date | None = None, supplier: str = "",
                category: str = "Otros", method: str = "tarjeta", vat_deductible: bool = True, invoice_ref: str = "") -> int:
    """Registra un gasto a partir del total pagado (IVA incluido)."""
    if not (concept or "").strip():
        raise ValueError("Indica el concepto del gasto.")
    if total_cents <= 0:
        raise ValueError("El importe debe ser mayor que 0.")
    if method not in METHODS:
        raise ValueError("Método de pago de gasto no válido.")
    base, vat = split_vat(total_cents, vat_rate)
    d = parse_date(expense_date) or today()
    eid = execute(
        "INSERT INTO expenses(date, concept, supplier, category, invoice_ref, base_cents, vat_rate, vat_cents, total_cents, method,"
        " vat_deductible, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (d.isoformat(), concept.strip(), supplier.strip(), category, invoice_ref.strip(), base, int(vat_rate), vat, total_cents,
         method, 1 if vat_deductible else 0, now().isoformat(timespec="seconds")),
    )
    audit("expense_add", f"id={eid} total={total_cents}")
    return eid


def list_expenses(date_from: date | None = None, date_to: date | None = None) -> list[dict]:
    sql, params = "SELECT * FROM expenses WHERE 1=1", []
    if date_from:
        sql += " AND date >= ?"
        params.append(date_from.isoformat())
    if date_to:
        sql += " AND date <= ?"
        params.append(date_to.isoformat())
    return fetch_all(sql + " ORDER BY date DESC, id DESC", params)


def delete_expense(expense_id: int) -> None:
    execute("DELETE FROM expenses WHERE id = ?", (expense_id,))
    audit("expense_delete", f"id={expense_id}")
