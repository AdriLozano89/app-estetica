"""Agenda de citas: alta, edición, estados, conflictos, eventos de calendario y recordatorios."""
from __future__ import annotations

from datetime import date, datetime, timedelta

from core.config import (
    STATUS_CANCELLED, STATUS_CONFIRMED, STATUS_DONE, STATUS_LABELS, STATUS_NOSHOW, STATUS_PENDING, Colors,
    CATEGORY_FALLBACK_COLOR,
)
from core.database import audit, execute, fetch_all, fetch_one
from core.utils import (
    fmt_long_date, fmt_time, iso_minute, now, parse_dt, render_template, today, whatsapp_link,
)
from services import catalog, settings

ACTIVE_STATUSES = (STATUS_PENDING, STATUS_CONFIRMED, STATUS_DONE)

_SELECT = """
SELECT a.*, c.first_name, c.last_name, c.phone, c.allergies, c.notes_medical,
       s.color AS color, s.category AS category
FROM appointments a
LEFT JOIN clients c ON c.id = a.client_id
LEFT JOIN services s ON s.id = a.service_id
"""


def _decorate(row: dict) -> dict:
    row["client_name"] = f"{row.get('first_name') or ''} {row.get('last_name') or ''}".strip() or "Sin cliente"
    row["color"] = row.get("color") or CATEGORY_FALLBACK_COLOR
    row["paid"] = bool(row.get("invoice_id"))
    return row


# --------------------------------------------------------------------------- consulta
def get(appt_id: int) -> dict | None:
    row = fetch_one(_SELECT + " WHERE a.id = ?", (appt_id,))
    return _decorate(row) if row else None


def list_range(start: datetime | date, end: datetime | date, include_cancelled: bool = False) -> list[dict]:
    """Citas con inicio en [start, end). Acepta fechas o datetimes."""
    s = start.strftime("%Y-%m-%dT%H:%M") if isinstance(start, datetime) else f"{start.isoformat()}T00:00"
    e = end.strftime("%Y-%m-%dT%H:%M") if isinstance(end, datetime) else f"{end.isoformat()}T00:00"
    sql = _SELECT + " WHERE a.start_ts >= ? AND a.start_ts < ?"
    if not include_cancelled:
        sql += f" AND a.status NOT IN ('{STATUS_CANCELLED}')"
    return [_decorate(r) for r in fetch_all(sql + " ORDER BY a.start_ts", (s, e))]


def day_appointments(day: date, include_cancelled: bool = False) -> list[dict]:
    return list_range(day, day + timedelta(days=1), include_cancelled)


def client_history(client_id: int, limit: int = 50) -> list[dict]:
    rows = fetch_all(_SELECT + " WHERE a.client_id = ? ORDER BY a.start_ts DESC LIMIT ?", (client_id, limit))
    return [_decorate(r) for r in rows]


def pending_payment(before: datetime | None = None) -> list[dict]:
    """Citas ya pasadas que siguen sin cobrar (para no olvidar ningún cobro)."""
    limit = (before or now()).strftime("%Y-%m-%dT%H:%M")
    rows = fetch_all(
        _SELECT + " WHERE a.invoice_id IS NULL AND a.status IN ('pendiente','confirmada','completada') AND a.end_ts <= ? "
        "ORDER BY a.start_ts DESC LIMIT 100", (limit,),
    )
    return [_decorate(r) for r in rows]


def conflicts(start: datetime, end: datetime, exclude_id: int | None = None, professional: str = "") -> list[dict]:
    """Citas activas que se solapan con el tramo [start, end)."""
    sql = _SELECT + " WHERE a.start_ts < ? AND a.end_ts > ? AND a.status NOT IN ('cancelada','no_show')"
    params: list = [iso_minute(end), iso_minute(start)]
    if exclude_id:
        sql += " AND a.id != ?"
        params.append(exclude_id)
    rows = [_decorate(r) for r in fetch_all(sql, params)]
    if professional:
        rows = [r for r in rows if (r.get("professional") or "") == professional]
    return rows


# --------------------------------------------------------------------------- escritura
def create(client_id: int | None, service_id: int | None, start: datetime, duration_min: int | None = None,
           price_cents: int | None = None, professional: str = "", notes: str = "",
           status: str = STATUS_PENDING, service_name: str = "") -> int:
    service = catalog.get_service(service_id)
    if not service and not service_name:
        raise ValueError("Elige un servicio.")
    duration = int(duration_min or (service["duration_min"] if service else 60))
    if duration <= 0:
        raise ValueError("La duración debe ser mayor que 0.")
    price = int(price_cents) if price_cents is not None else (service["price_cents"] if service else 0)
    end = start + timedelta(minutes=duration)
    aid = execute(
        "INSERT INTO appointments(client_id, service_id, service_name, start_ts, end_ts, status, price_cents, professional, notes, created_at)"
        " VALUES (?,?,?,?,?,?,?,?,?,?)",
        (client_id, service_id, service["name"] if service else service_name, iso_minute(start), iso_minute(end),
         status, price, professional.strip(), notes.strip(), now().isoformat(timespec="seconds")),
    )
    audit("appointment_create", f"id={aid} inicio={iso_minute(start)}")
    return aid


def update(appt_id: int, client_id: int | None = None, service_id: int | None = None, start: datetime | None = None,
           duration_min: int | None = None, price_cents: int | None = None, professional: str | None = None,
           notes: str | None = None) -> None:
    current = get(appt_id)
    if not current:
        raise ValueError("La cita no existe.")
    if current["invoice_id"]:
        raise ValueError("La cita ya está cobrada y no se puede modificar.")
    new_start = start or parse_dt(current["start_ts"])
    old_minutes = int((parse_dt(current["end_ts"]) - parse_dt(current["start_ts"])).total_seconds() // 60)
    minutes = int(duration_min or old_minutes)
    service = catalog.get_service(service_id) if service_id else None
    fields = {
        "client_id": client_id if client_id is not None else current["client_id"],
        "service_id": service["id"] if service else current["service_id"],
        "service_name": service["name"] if service else current["service_name"],
        "start_ts": iso_minute(new_start),
        "end_ts": iso_minute(new_start + timedelta(minutes=minutes)),
        "price_cents": price_cents if price_cents is not None else current["price_cents"],
        "professional": professional if professional is not None else current["professional"],
        "notes": notes if notes is not None else current["notes"],
    }
    sets = ", ".join(f"{k} = ?" for k in fields)
    execute(f"UPDATE appointments SET {sets}, reminder_sent = CASE WHEN start_ts != ? THEN 0 ELSE reminder_sent END WHERE id = ?",
            (*fields.values(), fields["start_ts"], appt_id))


def move(appt_id: int, start: datetime, end: datetime) -> None:
    """Arrastrar/redimensionar en el calendario."""
    current = get(appt_id)
    if not current or current["invoice_id"]:
        raise ValueError("No se puede mover una cita cobrada o inexistente.")
    if end <= start:
        raise ValueError("La hora de fin debe ser posterior al inicio.")
    execute("UPDATE appointments SET start_ts = ?, end_ts = ?, reminder_sent = 0 WHERE id = ?",
            (iso_minute(start), iso_minute(end), appt_id))


def set_status(appt_id: int, status: str) -> None:
    if status not in STATUS_LABELS:
        raise ValueError("Estado no válido.")
    execute("UPDATE appointments SET status = ? WHERE id = ?", (status, appt_id))
    audit("appointment_status", f"id={appt_id} estado={status}")


def delete(appt_id: int) -> None:
    current = get(appt_id)
    if current and current["invoice_id"]:
        raise ValueError("No se puede borrar una cita cobrada: cancélala o emite una rectificativa.")
    execute("DELETE FROM appointments WHERE id = ?", (appt_id,))


def mark_paid_tx(conn, appt_id: int, invoice_id: int) -> None:
    """La usa facturación: marca la cita como completada/cobrada y apunta el tratamiento en el historial."""
    row = fetch_one(_SELECT + " WHERE a.id = ?", (appt_id,), conn)
    if not row:
        return
    execute("UPDATE appointments SET invoice_id = ?, status = ? WHERE id = ?", (invoice_id, STATUS_DONE, appt_id), conn)
    if row["client_id"] and not fetch_one("SELECT id FROM treatments WHERE appointment_id = ?", (appt_id,), conn):
        execute(
            "INSERT INTO treatments(client_id, date, service_name, appointment_id, professional, created_at) VALUES (?,?,?,?,?,?)",
            (row["client_id"], row["start_ts"][:10], row["service_name"], appt_id, row["professional"],
             now().isoformat(timespec="seconds")), conn,
        )


def unmark_paid_tx(conn, invoice_id: int) -> None:
    """Al rectificar una factura, la cita vuelve a quedar pendiente de cobro."""
    execute("UPDATE appointments SET invoice_id = NULL, status = ? WHERE invoice_id = ?", (STATUS_CONFIRMED, invoice_id), conn)


# --------------------------------------------------------------------------- calendario (FullCalendar)
def _text_color(hex_color: str) -> str:
    h = hex_color.lstrip("#")
    if len(h) != 6:
        return Colors.BG
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return Colors.BG if (0.299 * r + 0.587 * g + 0.114 * b) > 150 else "#ffffff"


def calendar_events(start: date, end: date, include_cancelled: bool = False) -> list[dict]:
    """Eventos listos para streamlit-calendar: color por servicio, borde/icono por estado de cobro."""
    events = []
    for a in list_range(start, end, include_cancelled):
        status = a["status"]
        if status == STATUS_CANCELLED:
            icon, border, cls = "✖ ", Colors.MUTED, ["evt-cancelled"]
        elif status == STATUS_NOSHOW:
            icon, border, cls = "🚫 ", Colors.DANGER, ["evt-noshow"]
        elif a["paid"]:
            icon, border, cls = "✓ ", Colors.OK, ["evt-paid"]
        elif status == STATUS_DONE:
            icon, border, cls = "€ ", Colors.WARN, ["evt-unpaid"]
        elif status == STATUS_CONFIRMED:
            icon, border, cls = "● ", Colors.GOLD_SOFT, ["evt-confirmed"]
        else:
            icon, border, cls = "", "transparent", ["evt-pending"]
        events.append({
            "id": str(a["id"]),
            "title": f"{icon}{a['client_name']} · {a['service_name']}",
            "start": a["start_ts"] + ":00",
            "end": a["end_ts"] + ":00",
            "backgroundColor": a["color"],
            "borderColor": border,
            "textColor": _text_color(a["color"]),
            "classNames": cls,
            "editable": not a["paid"] and status not in (STATUS_CANCELLED, STATUS_NOSHOW),
            "extendedProps": {"appt_id": a["id"], "status": status, "paid": a["paid"]},
        })
    return events


# --------------------------------------------------------------------------- recordatorios WhatsApp
def reminder_text(appt: dict) -> str:
    cfg = settings.all_settings()
    start = parse_dt(appt["start_ts"])
    first = (appt.get("first_name") or appt.get("client_name") or "").split(" ")[0]
    return render_template(
        cfg["tpl_reminder"], nombre=first, centro=cfg["business_name"], servicio=appt["service_name"],
        fecha=fmt_long_date(start), hora=fmt_time(start),
    )


def reminder_link(appt: dict) -> str:
    return whatsapp_link(appt.get("phone"), reminder_text(appt), settings.default_cc())


def mark_reminder_sent(appt_id: int) -> None:
    execute("UPDATE appointments SET reminder_sent = 1, status = CASE WHEN status = 'pendiente' THEN 'confirmada' ELSE status END WHERE id = ?", (appt_id,))


def tomorrow_reminders() -> list[dict]:
    """Citas de mañana (activas) con su enlace de WhatsApp listo."""
    out = []
    for a in day_appointments(today() + timedelta(days=1)):
        if a["status"] in (STATUS_PENDING, STATUS_CONFIRMED):
            a["wa_link"] = reminder_link(a)
            out.append(a)
    return out


def day_summary(day: date) -> dict:
    items = day_appointments(day)
    return {
        "total": len(items),
        "paid": sum(1 for a in items if a["paid"]),
        "to_collect": sum(1 for a in items if not a["paid"] and a["status"] in (STATUS_PENDING, STATUS_CONFIRMED, STATUS_DONE)),
        "expected_cents": sum(a["price_cents"] for a in items if a["status"] != STATUS_NOSHOW),
        "next": next((a for a in items if a["start_ts"] >= now().strftime("%Y-%m-%dT%H:%M") and not a["paid"]), None),
    }
