"""Agenda: calendario FullCalendar (día/semana/mes/lista), citas del día, recordatorios y cobros pendientes."""
from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import streamlit as st

from core.config import TIMEZONE
from core.utils import fmt_date, fmt_eur, fmt_long_date, fmt_time, parse_date, parse_dt, today
from services import appointments, catalog, clients, settings
from ui import components as ui
from ui import dialogs
from ui.theme import CALENDAR_CSS

try:  # el calendario es un componente de terceros: si falta, la agenda sigue funcionando en modo lista
    from streamlit_calendar import calendar as fullcalendar
except Exception:  # pragma: no cover
    fullcalendar = None

VIEWS = {"Día": "timeGridDay", "Semana": "timeGridWeek", "Mes": "dayGridMonth", "Lista": "listWeek"}
CALLBACKS = ["dateClick", "eventClick", "eventChange"]  # sin "select": un clic dispararía dateClick y select a la vez
_TZ = ZoneInfo(TIMEZONE)


def _is_mobile() -> bool:
    try:
        agent = (st.context.headers.get("User-Agent") or "").lower()
    except Exception:
        return False
    return any(w in agent for w in ("mobile", "android", "iphone", "ipad"))


def _local_naive(value: str) -> datetime | None:
    """ISO del calendario → hora local del centro sin zona (admite 'Z', desfase o sin zona)."""
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt.astimezone(_TZ).replace(tzinfo=None) if dt.tzinfo else dt


def _calendar_options(view: str, initial: date) -> dict:
    open_days = settings.open_days()
    slot = int(settings.get("slot_minutes", "15") or 15)
    open_t, close_t = settings.get("open_time", "09:00"), settings.get("close_time", "20:00")
    start_h = max(int(open_t[:2]) - 1, 0)
    end_h = min(int(close_t[:2]) + 1, 24)
    return {
        "initialView": VIEWS[view], "initialDate": initial.isoformat(), "locale": "es", "firstDay": 1,
        "headerToolbar": {"left": "prev,next today", "center": "title", "right": ""},
        "buttonText": {"today": "Hoy"},
        "slotMinTime": f"{start_h:02d}:00:00", "slotMaxTime": f"{end_h:02d}:00:00" if end_h < 24 else "24:00:00",
        "slotDuration": f"00:{slot:02d}:00", "snapDuration": "00:15:00", "slotLabelInterval": "01:00",
        "slotLabelFormat": {"hour": "2-digit", "minute": "2-digit", "hour12": False},
        "eventTimeFormat": {"hour": "2-digit", "minute": "2-digit", "hour12": False},
        "dayHeaderFormat": {"weekday": "short", "day": "numeric", "month": "numeric"} if view == "Semana" else {"weekday": "long", "day": "numeric", "month": "long"},
        "allDaySlot": False, "nowIndicator": True, "editable": True, "selectable": False,
        "eventStartEditable": True, "eventDurationEditable": True,
        "longPressDelay": 350, "eventLongPressDelay": 350, "selectLongPressDelay": 350,  # en móvil: pulsación larga para crear/arrastrar
        "hiddenDays": [d for d in range(7) if d not in open_days],
        "businessHours": {"daysOfWeek": open_days, "startTime": open_t, "endTime": close_t},
        "expandRows": True, "stickyHeaderDates": True, "height": 680 if view != "Mes" else 640,
        "dayMaxEvents": 3, "navLinks": False,
    }


def _handle_calendar_event(state: dict, key: str) -> None:
    """Procesa un clic/arrastre del calendario una sola vez (el componente devuelve el último evento en cada ejecución)."""
    cb = state.get("callback")
    payload = state.get(cb) if cb else None
    if not cb or not payload:
        return
    token = (key, cb, json.dumps(payload, sort_keys=True, default=str))
    if st.session_state.get("_cal_seen") == token:
        return
    st.session_state["_cal_seen"] = token

    if cb == "eventClick":
        appt_id = (payload.get("event", {}).get("extendedProps") or {}).get("appt_id") or payload.get("event", {}).get("id")
        appt = appointments.get(int(appt_id)) if appt_id else None
        if appt:
            st.session_state["agenda_date"] = appt["start_ts"][:10]
            dialogs.appointment_detail_dialog(appt["id"])
    elif cb in ("dateClick", "select"):
        raw = payload.get("dateStr") or payload.get("startStr") or payload.get("start") or ""
        start = _local_naive(raw) if len(raw) > 10 else None
        if start is None and len(raw) >= 10:  # clic en un día entero (vista mes): proponemos la hora de apertura
            d = parse_date(raw[:10]) or today()
            hh, mm = (settings.get("open_time", "09:00") + ":00").split(":")[:2]
            start = datetime(d.year, d.month, d.day, int(hh), int(mm))
        if start:
            st.session_state["agenda_date"] = start.date().isoformat()
            dialogs.new_appointment_dialog(start_iso=start.strftime("%Y-%m-%dT%H:%M"))
    elif cb == "eventChange":
        ev = payload.get("event", {})
        appt_id = (ev.get("extendedProps") or {}).get("appt_id") or ev.get("id")
        start, end = _local_naive(ev.get("start", "")), _local_naive(ev.get("end", ""))
        if appt_id and start:
            appt = appointments.get(int(appt_id))
            if appt and not end:
                end = start + (parse_dt(appt["end_ts"]) - parse_dt(appt["start_ts"]))
            try:
                appointments.move(int(appt_id), start, end)
            except ValueError as exc:
                st.toast(f"⚠️ {exc}")
            else:
                overlap = appointments.conflicts(start, end, exclude_id=int(appt_id))
                st.toast("Cita movida ✅" + (" · ⚠️ se solapa con otra" if overlap else ""))
                st.session_state["agenda_date"] = start.date().isoformat()
            st.rerun()


def _render_calendar(view: str) -> None:
    initial = parse_date(st.session_state.get("agenda_date")) or today()
    events = appointments.calendar_events(today() - timedelta(days=120), today() + timedelta(days=400))
    if fullcalendar is None:
        st.warning("No se pudo cargar el calendario (falta streamlit-calendar). Mostrando la lista de citas.")
        _day_list(initial)
        return
    signature = hashlib.md5(json.dumps([(e["id"], e["start"], e["end"], e["title"], e["borderColor"]) for e in events]).encode()).hexdigest()[:8]
    key = f"cal_{view}_{signature}_{initial.isoformat()}"
    state = fullcalendar(events=events, options=_calendar_options(view, initial), custom_css=CALENDAR_CSS, callbacks=CALLBACKS, key=key)
    if state:
        _handle_calendar_event(state, key)
    ui.legend(catalog.list_services())


def _day_list(day: date) -> None:
    items = appointments.day_appointments(day)
    if not items:
        ui.empty_state("Sin citas este día. ¡Buen momento para reservar huecos!", "🌿")
        return
    for a in items:
        c1, c2 = st.columns([5, 1], vertical_alignment="center")
        c1.markdown(ui.appointment_card(a), unsafe_allow_html=True)
        if c2.button("Abrir", key=f"open_{a['id']}", use_container_width=True):
            dialogs.request("appointment", appt_id=a["id"])


def _tomorrow_reminders() -> None:
    rows = appointments.tomorrow_reminders()
    if not rows:
        ui.empty_state("No hay citas pendientes de recordar para mañana.", "📨")
        return
    st.caption("Pulsa 💬 para abrir WhatsApp con el mensaje ya escrito y, después, «Enviado» para dejarlo marcado.")
    for a in rows:
        c1, c2, c3 = st.columns([5, 2, 2], vertical_alignment="center")
        c1.markdown(ui.appointment_card(a) + (ui.badge("Aviso enviado", "ok") if a["reminder_sent"] else ""), unsafe_allow_html=True)
        with c2:
            ui.whatsapp_button("💬 WhatsApp", a["wa_link"], key=f"wa_{a['id']}", primary=not a["reminder_sent"])
        if c3.button("✓ Enviado", key=f"sent_{a['id']}", use_container_width=True, disabled=bool(a["reminder_sent"])):
            appointments.mark_reminder_sent(a["id"])
            st.rerun()


def _pending_payments() -> None:
    rows = appointments.pending_payment()
    if not rows:
        ui.empty_state("Todo cobrado. ¡Caja al día! ✨", "✅")
        return
    for a in rows[:30]:
        c1, c2 = st.columns([5, 1], vertical_alignment="center")
        c1.markdown(ui.appointment_card(a).replace(fmt_time(a["start_ts"]), f"{fmt_date(a['start_ts'])[:5]} {fmt_time(a['start_ts'])}", 1),
                    unsafe_allow_html=True)
        if c2.button("Cobrar", key=f"pp_{a['id']}", type="primary", use_container_width=True):
            dialogs.request("checkout", appt_id=a["id"])


def render() -> None:
    ui.page_header("Agenda de citas", fmt_long_date(today()).capitalize())
    summary = appointments.day_summary(today())
    nxt = summary["next"]
    ui.kpi_grid([
        ("Citas hoy", str(summary["total"]), f"{summary['paid']} cobradas"),
        ("Por cobrar hoy", str(summary["to_collect"]), "pendientes de cobro"),
        ("Previsto hoy", fmt_eur(summary["expected_cents"]), "según precios de las citas"),
        ("Próxima cita", fmt_time(nxt["start_ts"]) if nxt else "—", nxt["client_name"] if nxt else "no quedan más hoy"),
    ])

    soon = clients.birthdays_between(today(), today() + timedelta(days=7))
    if soon:
        names = " · ".join(f"{clients.full_name(c)} ({'hoy' if c['date'] == today() else fmt_date(c['date'])[:5]})" for c in soon[:5])
        st.info(f"🎂 Cumpleaños esta semana: {names}")

    # --- controles
    default_view = "Día" if _is_mobile() else "Semana"
    c1, c2, c3 = st.columns([4, 2, 2], vertical_alignment="center")
    with c1:
        view = ui.choice("Vista", list(VIEWS), key="agenda_view", default=default_view)
    with c2:
        if st.button("➕ Nueva cita", type="primary", use_container_width=True, key="agenda_new"):
            dialogs.request("new_appointment")
    with c3:
        with st.popover("📆 Ir a fecha", use_container_width=True):
            target = st.date_input("Fecha", value=parse_date(st.session_state.get("agenda_date")) or today(), format="DD/MM/YYYY", key="agenda_goto")
            if st.button("Ir", key="agenda_goto_btn", use_container_width=True):
                st.session_state["agenda_date"] = target.isoformat()
                st.rerun()
            if st.button("Hoy", key="agenda_today_btn", use_container_width=True):
                st.session_state["agenda_date"] = today().isoformat()
                st.rerun()

    _render_calendar(view)

    tab_today, tab_tomorrow, tab_pending = st.tabs(["Hoy", "Recordatorios de mañana", "Sin cobrar"])
    with tab_today:
        _day_list(today())
    with tab_tomorrow:
        _tomorrow_reminders()
    with tab_pending:
        _pending_payments()
