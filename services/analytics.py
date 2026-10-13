"""Analítica de negocio: KPIs, ingresos, servicios más vendidos, mezcla de pagos y ocupación."""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

from core.config import PAYMENT_LABELS, STATUS_CANCELLED, STATUS_DONE, STATUS_NOSHOW
from core.database import fetch_all, fetch_one
from core.utils import WEEKDAYS_SHORT, quarter_bounds, quarter_of, today

PERIODS = {
    "mes": "Este mes",
    "mes_anterior": "Mes anterior",
    "trimestre": "Este trimestre",
    "anio": "Este año",
    "30d": "Últimos 30 días",
}


def period_bounds(key: str, ref: date | None = None) -> tuple[date, date]:
    ref = ref or today()
    if key == "mes":
        return ref.replace(day=1), ref
    if key == "mes_anterior":
        end = ref.replace(day=1) - timedelta(days=1)
        return end.replace(day=1), end
    if key == "trimestre":
        start, _ = quarter_bounds(ref.year, quarter_of(ref))
        return start, ref
    if key == "anio":
        return date(ref.year, 1, 1), ref
    return ref - timedelta(days=29), ref


def kpis(start: date, end: date) -> dict:
    s, e = start.isoformat(), end.isoformat()
    inv = fetch_one(
        "SELECT COALESCE(SUM(total_cents),0) AS total, COALESCE(SUM(base_cents),0) AS base, "
        "COALESCE(SUM(CASE WHEN kind='F2' AND status='emitida' THEN 1 ELSE 0 END),0) AS tickets "
        "FROM invoices WHERE issued_at >= ? AND issued_at <= ?", (s, e),
    )
    appts = fetch_all(
        "SELECT status, COUNT(*) AS n FROM appointments WHERE substr(start_ts,1,10) >= ? AND substr(start_ts,1,10) <= ? GROUP BY status",
        (s, e),
    )
    by_status = {r["status"]: r["n"] for r in appts}
    total_appts = sum(by_status.values())
    lost = by_status.get(STATUS_CANCELLED, 0) + by_status.get(STATUS_NOSHOW, 0)
    new_clients = fetch_one(
        "SELECT COUNT(*) AS n FROM clients WHERE substr(created_at,1,10) >= ? AND substr(created_at,1,10) <= ?", (s, e)
    )["n"]
    return {
        "revenue_cents": inv["total"], "base_cents": inv["base"], "tickets": inv["tickets"],
        "avg_ticket_cents": round(inv["total"] / inv["tickets"]) if inv["tickets"] else 0,
        "appointments": total_appts, "completed": by_status.get(STATUS_DONE, 0),
        "cancelled": by_status.get(STATUS_CANCELLED, 0), "no_shows": by_status.get(STATUS_NOSHOW, 0),
        "loss_rate": (lost / total_appts) if total_appts else 0.0, "new_clients": new_clients,
    }


def revenue_by_day(start: date, end: date) -> pd.DataFrame:
    rows = fetch_all(
        "SELECT issued_at AS day, SUM(total_cents) AS cents FROM invoices WHERE issued_at >= ? AND issued_at <= ? GROUP BY issued_at",
        (start.isoformat(), end.isoformat()),
    )
    lookup = {r["day"]: r["cents"] for r in rows}
    days = pd.date_range(start, end, freq="D")
    return pd.DataFrame({"Ingresos (€)": [lookup.get(d.date().isoformat(), 0) / 100 for d in days]},
                        index=pd.Index([d.date() for d in days], name="Día"))


def revenue_by_month(year: int) -> pd.DataFrame:
    rows = fetch_all(
        "SELECT substr(issued_at,6,2) AS m, SUM(total_cents) AS cents FROM invoices WHERE substr(issued_at,1,4) = ? GROUP BY m",
        (str(year),),
    )
    lookup = {int(r["m"]): r["cents"] for r in rows}
    labels = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]
    return pd.DataFrame({"Ingresos (€)": [lookup.get(m, 0) / 100 for m in range(1, 13)]}, index=pd.Index(labels, name="Mes"))


def top_services(start: date, end: date, limit: int = 8) -> pd.DataFrame:
    rows = fetch_all(
        "SELECT COALESCE(s.name, l.description) AS name, SUM(l.qty) AS qty, SUM(l.total_cents) AS cents "
        "FROM invoice_lines l JOIN invoices i ON i.id = l.invoice_id LEFT JOIN services s ON s.id = l.service_id "
        "WHERE i.issued_at >= ? AND i.issued_at <= ? GROUP BY name HAVING SUM(l.total_cents) > 0 "
        "ORDER BY cents DESC LIMIT ?", (start.isoformat(), end.isoformat(), limit),
    )
    return pd.DataFrame({"Ingresos (€)": [r["cents"] / 100 for r in rows], "Unidades": [r["qty"] for r in rows]},
                        index=pd.Index([r["name"] for r in rows], name="Servicio"))


def payment_mix(start: date, end: date) -> pd.DataFrame:
    rows = fetch_all(
        "SELECT method, SUM(amount_cents) AS cents FROM payments WHERE kind IN ('invoice','rectify') "
        "AND substr(ts,1,10) >= ? AND substr(ts,1,10) <= ? GROUP BY method", (start.isoformat(), end.isoformat()),
    )
    return pd.DataFrame({"Importe (€)": [r["cents"] / 100 for r in rows]},
                        index=pd.Index([PAYMENT_LABELS.get(r["method"], r["method"]) for r in rows], name="Método"))


def busy_by_weekday(start: date, end: date) -> pd.DataFrame:
    rows = fetch_all(
        "SELECT CAST(strftime('%w', start_ts) AS INTEGER) AS wd, COUNT(*) AS n FROM appointments "
        "WHERE substr(start_ts,1,10) >= ? AND substr(start_ts,1,10) <= ? AND status NOT IN ('cancelada') GROUP BY wd",
        (start.isoformat(), end.isoformat()),
    )
    lookup = {(r["wd"] - 1) % 7: r["n"] for r in rows}  # SQLite: 0 = domingo → 6 en lunes-primero
    return pd.DataFrame({"Citas": [lookup.get(i, 0) for i in range(7)]}, index=pd.Index(list(WEEKDAYS_SHORT), name="Día"))


def busy_by_hour(start: date, end: date) -> pd.DataFrame:
    rows = fetch_all(
        "SELECT CAST(substr(start_ts,12,2) AS INTEGER) AS h, COUNT(*) AS n FROM appointments "
        "WHERE substr(start_ts,1,10) >= ? AND substr(start_ts,1,10) <= ? AND status NOT IN ('cancelada') GROUP BY h ORDER BY h",
        (start.isoformat(), end.isoformat()),
    )
    return pd.DataFrame({"Citas": [r["n"] for r in rows]}, index=pd.Index([f"{r['h']:02d}:00" for r in rows], name="Hora"))


def top_clients(start: date, end: date, limit: int = 8) -> pd.DataFrame:
    rows = fetch_all(
        "SELECT c.first_name || ' ' || c.last_name AS name, SUM(i.total_cents) AS cents, COUNT(*) AS n "
        "FROM invoices i JOIN clients c ON c.id = i.client_id WHERE i.issued_at >= ? AND i.issued_at <= ? AND c.anonymized = 0 "
        "GROUP BY c.id HAVING SUM(i.total_cents) > 0 ORDER BY cents DESC LIMIT ?", (start.isoformat(), end.isoformat(), limit),
    )
    return pd.DataFrame({"Gastado (€)": [r["cents"] / 100 for r in rows], "Facturas": [r["n"] for r in rows]},
                        index=pd.Index([r["name"].strip() for r in rows], name="Cliente"))
