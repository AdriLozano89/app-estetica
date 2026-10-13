"""Estimación trimestral de impuestos: Modelo 303 (IVA) y Modelo 130 (IRPF, pago fraccionado).

IMPORTANTE: son estimaciones orientativas calculadas con los datos registrados en la app, para
anticipar cuánto separar cada trimestre. La presentación oficial debe revisarla tu gestor/a.
"""
from __future__ import annotations

from datetime import date

from core.database import fetch_all, fetch_one
from core.utils import quarter_bounds

# Casillas del modelo 303 (régimen general) para los tipos habituales; solo como guía de rellenado.
CASILLAS_DEVENGADO = {4: ("01", "03"), 10: ("04", "06"), 21: ("07", "09")}


def iva_quarter(year: int, quarter: int) -> dict:
    """IVA devengado (ventas) menos IVA soportado deducible (gastos) del trimestre."""
    start, end = quarter_bounds(year, quarter)
    accrued_rows = fetch_all(
        "SELECT l.vat_rate AS rate, SUM(l.base_cents) AS base, SUM(l.vat_cents) AS vat "
        "FROM invoice_lines l JOIN invoices i ON i.id = l.invoice_id "
        "WHERE i.issued_at >= ? AND i.issued_at <= ? GROUP BY l.vat_rate ORDER BY l.vat_rate",
        (start.isoformat(), end.isoformat()),
    )
    input_rows = fetch_all(
        "SELECT vat_rate AS rate, SUM(base_cents) AS base, SUM(vat_cents) AS vat FROM expenses "
        "WHERE date >= ? AND date <= ? AND vat_deductible = 1 AND vat_rate > 0 GROUP BY vat_rate ORDER BY vat_rate",
        (start.isoformat(), end.isoformat()),
    )
    accrued_total = sum(r["vat"] for r in accrued_rows)
    input_total = sum(r["vat"] for r in input_rows)
    result = accrued_total - input_total
    return {
        "year": year, "quarter": quarter, "start": start, "end": end,
        "accrued": accrued_rows, "input": input_rows,
        "accrued_total_cents": accrued_total, "input_total_cents": input_total,
        "sales_base_cents": sum(r["base"] for r in accrued_rows),
        "result_cents": result,
        "to_pay_cents": max(result, 0),
        "to_offset_cents": max(-result, 0),
    }


def _ytd_income_expenses(year: int, until: date) -> tuple[int, int]:
    first = date(year, 1, 1).isoformat()
    income = fetch_one(
        "SELECT COALESCE(SUM(base_cents),0) AS s FROM invoices WHERE issued_at >= ? AND issued_at <= ?", (first, until.isoformat())
    )["s"]
    # Gasto deducible en IRPF: la base; si el IVA no es deducible, forma parte del gasto.
    expenses = fetch_one(
        "SELECT COALESCE(SUM(base_cents + CASE WHEN vat_deductible = 1 THEN 0 ELSE vat_cents END),0) AS s "
        "FROM expenses WHERE date >= ? AND date <= ?", (first, until.isoformat()),
    )["s"]
    return income, expenses


def irpf_130(year: int, quarter: int, previous_payments_cents: int | None = None, withholdings_cents: int = 0) -> dict:
    """Pago fraccionado del 20 % del rendimiento neto acumulado (estimación directa).

    ``previous_payments_cents``: pagos fraccionados ya ingresados en trimestres anteriores. Si no se
    indica, se estiman con los datos de la app (sin retenciones).
    """
    _, end = quarter_bounds(year, quarter)
    income, expenses = _ytd_income_expenses(year, end)
    net = income - expenses
    gross_payment = max(round(net * 0.20), 0)
    if previous_payments_cents is None:
        previous_payments_cents = 0
        for q in range(1, quarter):
            previous_payments_cents += irpf_130(year, q, previous_payments_cents=previous_payments_cents)["to_pay_cents"]
    result = gross_payment - previous_payments_cents - withholdings_cents
    return {
        "year": year, "quarter": quarter, "end": end,
        "income_cents": income, "expenses_cents": expenses, "net_cents": net,
        "gross_payment_cents": gross_payment,
        "previous_payments_cents": previous_payments_cents,
        "withholdings_cents": withholdings_cents,
        "result_cents": result,
        "to_pay_cents": max(result, 0),
    }


def quarter_provision(year: int, quarter: int) -> dict:
    """Cuánto conviene reservar del trimestre: IVA a ingresar + 130 estimado."""
    iva = iva_quarter(year, quarter)
    irpf = irpf_130(year, quarter)
    return {"iva_cents": iva["to_pay_cents"], "irpf_cents": irpf["to_pay_cents"],
            "total_cents": iva["to_pay_cents"] + irpf["to_pay_cents"]}
