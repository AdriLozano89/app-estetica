"""Caja diaria: arqueo por método de pago, cuadre de efectivo y cierres.

Qué cuenta como "entra dinero": efectivo, tarjeta y Bizum. Monedero y tarjeta regalo son medios de
pago que se *consumen* (el dinero entró cuando se recargó/vendió), por eso se muestran aparte y no
suman al total cobrado del día.
"""
from __future__ import annotations

from datetime import date

from core.config import CASH_IN_METHODS, PAYMENT_LABELS
from core.database import audit, execute, fetch_all, fetch_one, get_conn
from core.utils import now

KIND_LABELS = {
    "invoice": "Ventas de servicios",
    "rectify": "Devoluciones (rectificativas)",
    "giftcard_sale": "Tarjetas regalo vendidas",
    "giftcard_refund": "Devoluciones de tarjetas regalo",
    "wallet_topup": "Recargas de monedero",
}


def day_movements(day: date) -> list[dict]:
    return fetch_all("SELECT * FROM payments WHERE substr(ts, 1, 10) = ? ORDER BY ts, id", (day.isoformat(),))


def day_summary(day: date) -> dict:
    """Arqueo del día: totales por método, por concepto y efectivo esperado en caja."""
    moves = day_movements(day)
    by_method = {k: 0 for k in PAYMENT_LABELS}
    by_kind: dict[str, int] = {}
    for m in moves:
        by_method[m["method"]] = by_method.get(m["method"], 0) + m["amount_cents"]
        by_kind[m["kind"]] = by_kind.get(m["kind"], 0) + m["amount_cents"]
    cash_expenses = fetch_one(
        "SELECT COALESCE(SUM(total_cents),0) AS s FROM expenses WHERE date = ? AND method = 'efectivo'", (day.isoformat(),)
    )["s"]
    tickets = fetch_one(
        "SELECT COUNT(*) AS n, COALESCE(SUM(total_cents),0) AS s FROM invoices WHERE issued_at = ? AND kind = 'F2'", (day.isoformat(),)
    )
    return {
        "date": day,
        "by_method": by_method,
        "by_kind": by_kind,
        "money_in_cents": sum(by_method[k] for k in CASH_IN_METHODS),
        "consumed_cents": by_method.get("monedero", 0) + by_method.get("tarjeta_regalo", 0),
        "cash_expenses_cents": cash_expenses,
        "tickets": tickets["n"],
        "sales_cents": tickets["s"],
        "movements": moves,
    }


def expected_cash(day: date, opening_cents: int) -> int:
    s = day_summary(day)
    return opening_cents + s["by_method"].get("efectivo", 0) - s["cash_expenses_cents"]


def get_closing(day: date) -> dict | None:
    return fetch_one("SELECT * FROM cash_closings WHERE date = ?", (day.isoformat(),))


def suggested_opening(day: date) -> int:
    """Fondo inicial sugerido: el efectivo contado en el último cierre anterior."""
    row = fetch_one("SELECT counted_cents FROM cash_closings WHERE date < ? ORDER BY date DESC LIMIT 1", (day.isoformat(),))
    return row["counted_cents"] if row else 0


def close_day(day: date, opening_cents: int, counted_cents: int, notes: str = "") -> dict:
    """Guarda (o actualiza) el cierre de caja con la diferencia entre lo esperado y lo contado."""
    if opening_cents < 0 or counted_cents < 0:
        raise ValueError("Los importes no pueden ser negativos.")
    expected = expected_cash(day, opening_cents)
    diff = counted_cents - expected
    with get_conn() as conn:
        execute(
            "INSERT INTO cash_closings(date, opening_cents, expected_cents, counted_cents, diff_cents, notes, closed_at) VALUES (?,?,?,?,?,?,?) "
            "ON CONFLICT(date) DO UPDATE SET opening_cents=excluded.opening_cents, expected_cents=excluded.expected_cents,"
            " counted_cents=excluded.counted_cents, diff_cents=excluded.diff_cents, notes=excluded.notes, closed_at=excluded.closed_at",
            (day.isoformat(), opening_cents, expected, counted_cents, diff, notes.strip(), now().isoformat(timespec="seconds")), conn,
        )
        audit("cash_close", f"{day.isoformat()} esperado={expected} contado={counted_cents} dif={diff}", conn)
    return get_closing(day)  # type: ignore[return-value]


def list_closings(limit: int = 60) -> list[dict]:
    return fetch_all("SELECT * FROM cash_closings ORDER BY date DESC LIMIT ?", (limit,))
