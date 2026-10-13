"""Diálogos modales compartidos por varias pantallas.

Streamlit solo permite abrir **un** diálogo por ejecución y no anidarlos. Por eso cualquier pantalla que quiera
abrir uno hace ``request("nombre", **datos)`` y ``dispatch()`` (llamado una vez por ejecución desde ``app.py``)
lo muestra al volver a ejecutar.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

import streamlit as st

from core.config import STATUS_CANCELLED, STATUS_CONFIRMED, STATUS_NOSHOW
from core.utils import (
    fmt_date, fmt_eur, fmt_long_date, fmt_time, now, parse_dt, to_cents, today, whatsapp_link,
)
from documents.invoice_pdf import render_invoice_pdf
from services import appointments, billing, catalog, clients, giftcards, settings, wallet
from ui import components as ui


# --------------------------------------------------------------------------- despacho
def request(name: str, **kwargs) -> None:
    """Pide abrir un diálogo en la siguiente ejecución."""
    if name == "checkout":  # empezar siempre con un cobro limpio
        for key in [k for k in st.session_state if str(k).startswith("co_")]:
            del st.session_state[key]
    st.session_state["_dialog"] = (name, kwargs)
    st.rerun()


def dispatch() -> None:
    req = st.session_state.pop("_dialog", None)
    if not req:
        return
    name, kwargs = req
    fn = {
        "new_appointment": new_appointment_dialog,
        "edit_appointment": edit_appointment_dialog,
        "appointment": appointment_detail_dialog,
        "checkout": checkout_dialog,
        "new_client": new_client_dialog,
    }.get(name)
    if fn:
        fn(**kwargs)


def _close(message: str | None = None) -> None:
    if message:
        st.toast(message)
    st.rerun()


# --------------------------------------------------------------------------- nueva clienta
@st.dialog("Nueva clienta")
def new_client_dialog() -> None:
    with st.form("new_client_form"):
        c1, c2 = st.columns(2)
        first = c1.text_input("Nombre *")
        last = c2.text_input("Apellidos")
        phone = st.text_input("Móvil (para WhatsApp)", placeholder="600 123 456")
        email = st.text_input("Email")
        birth = st.date_input("Fecha de nacimiento", value=None, min_value=date(1920, 1, 1), max_value=today(), format="DD/MM/YYYY")
        allergies = st.text_input("Alergias o avisos importantes", placeholder="Ej.: alergia al níquel, embarazo…")
        marketing = st.checkbox("Acepta recibir felicitaciones y comunicaciones comerciales")
        submitted = st.form_submit_button("Guardar clienta", type="primary", use_container_width=True)
    if submitted:
        try:
            cid = clients.create_client(first, last, phone, email, birth, allergies=allergies, marketing_consent=marketing)
        except ValueError as exc:
            st.error(str(exc))
            return
        st.session_state["_open_client"] = cid
        _close("Clienta guardada ✅")


# --------------------------------------------------------------------------- cita (alta / edición)
def _default_start() -> datetime:
    n = now()
    minutes = (n.minute // 15 + 1) * 15
    return n.replace(minute=0, second=0) + timedelta(minutes=minutes)


def _appointment_form(prefix: str, appt: dict | None, start: datetime | None, client_id: int | None) -> None:
    services = catalog.list_services()
    if not services:
        st.warning("Primero crea algún servicio en Ajustes → Servicios.")
        return
    by_id = {s["id"]: s for s in services}

    # --- clienta
    new_client = False
    if appt is None:
        has_clients = bool(clients.search_clients())
        new_client = st.toggle("Clienta nueva", value=not has_clients, key=f"{prefix}_newc")
    if new_client:
        c1, c2 = st.columns(2)
        nc_first = c1.text_input("Nombre *", key=f"{prefix}_nc_first")
        nc_last = c2.text_input("Apellidos", key=f"{prefix}_nc_last")
        nc_phone = st.text_input("Móvil (WhatsApp)", key=f"{prefix}_nc_phone", placeholder="600 123 456")
        chosen_client = None
    else:
        chosen_client = ui.client_picker("Clienta", f"{prefix}_client", default_id=(appt or {}).get("client_id") or client_id,
                                         allow_none=False)
        info = clients.get_client(chosen_client)
        if info and (info["allergies"] or info["notes_medical"]):
            ui.html(f'<div class="jd-alert">⚠️ <b>Atención:</b> {ui.esc(info["allergies"] or info["notes_medical"])}</div>')

    # --- servicio, fecha y hora
    ids = list(by_id)
    default_sid = (appt or {}).get("service_id")
    sid = st.selectbox(
        "Servicio", ids, index=ids.index(default_sid) if default_sid in ids else 0, key=f"{prefix}_service",
        format_func=lambda i: f"{by_id[i]['name']} · {by_id[i]['duration_min']} min · {fmt_eur(by_id[i]['price_cents'])}",
    )
    svc = by_id[sid]
    base = parse_dt(appt["start_ts"]) if appt else (start or _default_start())
    c1, c2 = st.columns(2)
    day = c1.date_input("Fecha", value=base.date(), format="DD/MM/YYYY", key=f"{prefix}_date")
    at = c2.time_input("Hora", value=base.time().replace(second=0), step=900, key=f"{prefix}_time")
    old_min = int((parse_dt(appt["end_ts"]) - parse_dt(appt["start_ts"])).total_seconds() // 60) if appt else svc["duration_min"]
    c3, c4 = st.columns(2)
    duration = c3.number_input("Duración (min)", min_value=5, max_value=480, step=5, key=f"{prefix}_dur_{sid}",
                               value=old_min if appt and sid == appt["service_id"] else svc["duration_min"])
    with c4:
        price = ui.money_input("Precio (IVA incl.)", appt["price_cents"] if appt and sid == appt["service_id"] else svc["price_cents"],
                               key=f"{prefix}_price_{sid}")
    professional = st.text_input("Profesional (opcional)", value=(appt or {}).get("professional", ""), key=f"{prefix}_pro")
    notes = st.text_area("Notas de la cita", value=(appt or {}).get("notes", ""), key=f"{prefix}_notes", height=80)

    # --- avisos
    start_dt = datetime.combine(day, at)
    end_dt = start_dt + timedelta(minutes=int(duration))
    overlap = appointments.conflicts(start_dt, end_dt, exclude_id=appt["id"] if appt else None)
    force = True
    if overlap:
        names = ", ".join(f"{o['client_name']} ({fmt_time(o['start_ts'])}–{fmt_time(o['end_ts'])})" for o in overlap[:3])
        st.warning(f"⚠️ Se solapa con: {names}")
        force = st.checkbox("Guardar de todos modos", key=f"{prefix}_force")
    if int(day.strftime("%w")) not in settings.open_days():
        st.info("Ese día el centro figura como cerrado en Ajustes → Horario.")

    if st.button("Guardar cita", type="primary", use_container_width=True, disabled=not force, key=f"{prefix}_save"):
        try:
            if appt:
                appointments.update(appt["id"], client_id=chosen_client, service_id=sid, start=start_dt, duration_min=int(duration),
                                    price_cents=price, professional=professional, notes=notes)
            else:
                if new_client:
                    chosen_client = clients.create_client(nc_first, nc_last, nc_phone)
                appointments.create(chosen_client, sid, start_dt, int(duration), price, professional, notes)
        except ValueError as exc:
            st.error(str(exc))
            return
        st.session_state["agenda_date"] = day.isoformat()
        _close("Cita guardada ✅")


@st.dialog("Nueva cita", width="large")
def new_appointment_dialog(start_iso: str | None = None, client_id: int | None = None) -> None:
    _appointment_form("na", None, parse_dt(start_iso) if start_iso else None, client_id)


@st.dialog("Editar cita", width="large")
def edit_appointment_dialog(appt_id: int) -> None:
    appt = appointments.get(appt_id)
    if not appt:
        st.error("La cita ya no existe.")
        return
    _appointment_form(f"ea{appt_id}", appt, None, None)


# --------------------------------------------------------------------------- detalle de cita
@st.dialog("Cita", width="large")
def appointment_detail_dialog(appt_id: int) -> None:
    a = appointments.get(appt_id)
    if not a:
        st.error("La cita ya no existe.")
        return
    start, end = parse_dt(a["start_ts"]), parse_dt(a["end_ts"])
    ui.html(
        f'<div class="jd-card gold"><div style="display:flex;justify-content:space-between;gap:.6rem;align-items:flex-start">'
        f'<div><div style="font-family:var(--font-title);font-size:1.9rem;line-height:1.1">{ui.esc(a["client_name"])}</div>'
        f'<div class="jd-muted">{ui.esc(a["service_name"])}</div></div><div>{ui.status_badge(a["status"], a["paid"])}</div></div>'
        f'<div style="margin-top:.7rem">📅 {fmt_long_date(start)} · 🕐 {fmt_time(start)}–{fmt_time(end)} · 💶 {fmt_eur(a["price_cents"])}</div>'
        + (f'<div class="jd-muted" style="margin-top:.3rem">👩‍⚕️ {ui.esc(a["professional"])}</div>' if a["professional"] else "")
        + (f'<div style="margin-top:.5rem">📝 {ui.esc(a["notes"])}</div>' if a["notes"] else "") + "</div>"
    )
    if (a.get("allergies") or "").strip() or (a.get("notes_medical") or "").strip():
        ui.html(f'<div class="jd-alert">⚠️ <b>Alergias / notas médicas:</b> {ui.esc(a["allergies"] or a["notes_medical"])}</div>')

    closed = a["status"] in (STATUS_CANCELLED, STATUS_NOSHOW)
    if a["paid"]:
        inv = billing.get_invoice(a["invoice_id"])
        if inv:
            st.success(f"Cobrada con la factura {inv['full_number']} · {fmt_eur(inv['total_cents'])} ({billing.payment_summary(inv)})")
            st.download_button("⬇️ Descargar factura (PDF)", render_invoice_pdf(inv, settings.all_settings()),
                               file_name=f"{inv['full_number']}.pdf", mime="application/pdf", use_container_width=True, key=f"dl_{appt_id}")
    elif not closed:
        c1, c2 = st.columns(2)
        if c1.button("💶 Cobrar", type="primary", use_container_width=True, key=f"d_pay_{appt_id}"):
            request("checkout", appt_id=appt_id)
        with c2:
            ui.whatsapp_button("💬 Recordatorio WhatsApp", appointments.reminder_link(a), key=f"d_wa_{appt_id}")

    if not a["paid"] and not closed:
        c1, c2, c3 = st.columns(3)
        if c1.button("✅ Confirmar", use_container_width=True, key=f"d_conf_{appt_id}", disabled=a["status"] == STATUS_CONFIRMED):
            appointments.set_status(appt_id, STATUS_CONFIRMED)
            _close("Cita confirmada")
        if c2.button("✏️ Editar", use_container_width=True, key=f"d_edit_{appt_id}"):
            request("edit_appointment", appt_id=appt_id)
        if c3.button("📨 Aviso enviado", use_container_width=True, key=f"d_sent_{appt_id}", help="Marca el recordatorio como enviado y confirma la cita"):
            appointments.mark_reminder_sent(appt_id)
            _close("Recordatorio marcado como enviado")
        c1, c2 = st.columns(2)
        if c1.button("✖️ Cancelar cita", use_container_width=True, key=f"d_cancel_{appt_id}"):
            appointments.set_status(appt_id, STATUS_CANCELLED)
            _close("Cita cancelada")
        if c2.button("🚫 No se presentó", use_container_width=True, key=f"d_noshow_{appt_id}"):
            appointments.set_status(appt_id, STATUS_NOSHOW)
            _close("Marcada como ausencia")
    elif closed:
        if st.button("↩️ Reactivar cita", use_container_width=True, key=f"d_react_{appt_id}"):
            appointments.set_status(appt_id, "pendiente")
            _close("Cita reactivada")

    if a["client_id"]:
        if st.button("👤 Ver ficha de la clienta", use_container_width=True, key=f"d_client_{appt_id}"):
            ui.goto("clientes", _open_client=a["client_id"])
    if not a["paid"]:
        with st.expander("Eliminar cita"):
            if st.checkbox("Confirmo que quiero eliminarla definitivamente", key=f"d_delc_{appt_id}"):
                if st.button("Eliminar", key=f"d_del_{appt_id}"):
                    appointments.delete(appt_id)
                    _close("Cita eliminada")


# --------------------------------------------------------------------------- cobro
def _lines_table(lines: list[dict], computed: list[dict]) -> str:
    rows = "".join(
        f'<tr><td>{ui.esc(c["description"])}</td><td class="r">{ln["qty"]:g}</td><td class="r">{fmt_eur(ln["unit_cents"])}</td>'
        f'<td class="r">{fmt_eur(c["total_cents"])}</td></tr>'
        for ln, c in zip(lines, computed)
    )
    return ('<table class="jd-lines"><tr><th>Concepto</th><th class="r">Cant.</th><th class="r">Precio</th><th class="r">Importe</th></tr>'
            + rows + "</table>")


@st.dialog("Cobrar", width="large")
def checkout_dialog(appt_id: int | None = None, client_id: int | None = None) -> None:
    ctx = f"co_{appt_id or 'rapido'}"
    done_key = f"{ctx}_done"
    if st.session_state.get(done_key):
        _checkout_success(st.session_state[done_key])
        return

    appt = appointments.get(appt_id) if appt_id else None
    lines_key = f"{ctx}_lines"
    if lines_key not in st.session_state:
        svc = catalog.get_service(appt["service_id"]) if appt else None
        st.session_state[lines_key] = (
            [{"description": appt["service_name"], "qty": 1, "unit_cents": appt["price_cents"],
              "vat_rate": svc["vat_rate"] if svc else 21, "service_id": appt["service_id"]}] if appt else []
        )
    lines: list[dict] = st.session_state[lines_key]

    default_client = appt["client_id"] if appt else client_id
    cid = ui.client_picker("Clienta", f"{ctx}_client", default_id=default_client, allow_none=True)
    info = clients.get_client(cid)
    if info and info["allergies"]:
        ui.html(f'<div class="jd-alert">⚠️ <b>Alergias:</b> {ui.esc(info["allergies"])}</div>')

    # --- conceptos
    services = catalog.list_services()
    by_id = {s["id"]: s for s in services}
    with st.expander("➕ Añadir servicio o producto", expanded=not lines):
        t1, t2 = st.tabs(["Del catálogo", "Concepto libre"])
        with t1:
            with st.form(f"{ctx}_add_cat", clear_on_submit=True):
                sid = st.selectbox("Servicio", list(by_id), key=f"{ctx}_cat_sel", format_func=lambda i: f"{by_id[i]['name']} · {fmt_eur(by_id[i]['price_cents'])}")
                qty = st.number_input("Cantidad", min_value=1, max_value=20, value=1, key=f"{ctx}_cat_qty")
                if st.form_submit_button("Añadir", use_container_width=True) and sid:
                    s = by_id[sid]
                    lines.append({"description": s["name"], "qty": qty, "unit_cents": s["price_cents"], "vat_rate": s["vat_rate"], "service_id": sid})
                    st.rerun(scope="fragment")
        with t2:
            with st.form(f"{ctx}_add_free", clear_on_submit=True):
                concept = st.text_input("Concepto", placeholder="Ej.: Crema hidratante")
                f1, f2, f3 = st.columns(3)
                fqty = f1.number_input("Cant.", min_value=1, max_value=50, value=1)
                fprice = f2.number_input("Precio (IVA incl.)", min_value=0.0, value=0.0, step=1.0, format="%.2f")
                frate = f3.selectbox("IVA %", [21, 10, 4, 0], index=0)
                if st.form_submit_button("Añadir", use_container_width=True):
                    if concept.strip() and fprice > 0:
                        lines.append({"description": concept.strip(), "qty": fqty, "unit_cents": to_cents(fprice), "vat_rate": frate, "service_id": None})
                        st.rerun(scope="fragment")
                    else:
                        st.error("Indica concepto y precio.")
    if not lines:
        st.info("Añade al menos un concepto para cobrar.")
        return

    # --- descuento y totales
    gross = sum(int(round(ln["qty"] * ln["unit_cents"])) for ln in lines)
    d1, d2 = st.columns([1, 1])
    mode = d1.radio("Descuento", ["Ninguno", "%", "€"], horizontal=True, key=f"{ctx}_dmode")
    discount = 0
    with d2:
        if mode == "%":
            pct = st.number_input("Porcentaje", min_value=0.0, max_value=100.0, value=10.0, step=5.0, key=f"{ctx}_dpct")
            discount = round(gross * pct / 100)
        elif mode == "€":
            discount = ui.money_input("Importe", 0, key=f"{ctx}_deur", max_cents=gross)
    try:
        computed = billing.compute_lines(lines, discount)
    except ValueError as exc:
        st.error(str(exc))
        return
    total = sum(c["total_cents"] for c in computed)
    ui.html(
        f'<div class="jd-card">{_lines_table(lines, computed)}'
        + (f'<div class="jd-muted" style="text-align:right;margin-top:.4rem">Descuento: −{fmt_eur(discount)}</div>' if discount else "")
        + f'<div class="jd-total"><span class="jd-muted">TOTAL (IVA incluido)</span><b>{fmt_eur(total)}</b></div></div>'
    )
    if len(lines) > 1 or not appt:
        idx = st.selectbox("Quitar concepto", [None] + list(range(len(lines))), key=f"{ctx}_rm", format_func=lambda i: "—" if i is None else lines[i]["description"])
        if idx is not None and st.button("Quitar", key=f"{ctx}_rm_btn"):
            lines.pop(idx)
            st.rerun(scope="fragment")
    if total <= 0:
        st.warning("El total debe ser mayor que 0 para emitir factura.")
        return

    # --- forma de pago
    st.markdown("**Forma de pago**")
    options = ["efectivo", "tarjeta", "bizum", "monedero", "tarjeta_regalo", "mixto"]
    method = st.radio("Forma de pago", options, horizontal=True, key=f"{ctx}_method", label_visibility="collapsed",
                      format_func=lambda m: "🔀 Mixto" if m == "mixto" else ui.payment_label(m))
    bal = wallet.balance(cid) if cid else 0
    payments: list[dict] = []
    problems: list[str] = []

    def gift_input(key: str) -> str:
        code = st.text_input("Código de la tarjeta regalo", key=key, placeholder="JD-XXXX-XXXX")
        if code.strip():
            card = giftcards.get_by_code(code)
            if not card:
                st.error("No existe esa tarjeta.")
            else:
                status = giftcards.effective_status(card)
                (st.success if status == "activa" else st.error)(f"Tarjeta {card['code']}: saldo {fmt_eur(card['balance_cents'])} · {status} · caduca {fmt_date(card['expires_at'])}")
        return code

    if method != "mixto":
        if method == "monedero":
            if not cid:
                problems.append("Para pagar con monedero elige una clienta.")
            else:
                st.caption(f"Saldo del monedero: {fmt_eur(bal)}")
                if bal < total:
                    problems.append("Saldo insuficiente: usa pago mixto para completar con otro método.")
        code = gift_input(f"{ctx}_gift1") if method == "tarjeta_regalo" else ""
        if method == "tarjeta_regalo" and not code.strip():
            problems.append("Escribe el código de la tarjeta regalo.")
        payments = [{"method": method, "amount_cents": total, "gift_code": code}]
    else:
        remaining = total
        amounts: dict[str, int] = {}
        for m in ("efectivo", "tarjeta", "bizum"):
            amounts[m] = ui.money_input(ui.payment_label(m), 0, key=f"{ctx}_mx_{m}", max_cents=total)
        amounts["monedero"] = ui.money_input(f"{ui.payment_label('monedero')} (saldo {fmt_eur(bal)})", 0, key=f"{ctx}_mx_mon", max_cents=min(bal, total) if cid else 0)
        amounts["tarjeta_regalo"] = ui.money_input(ui.payment_label("tarjeta_regalo"), 0, key=f"{ctx}_mx_gift", max_cents=total)
        code = gift_input(f"{ctx}_gift2") if amounts["tarjeta_regalo"] else ""
        if amounts["tarjeta_regalo"] and not code.strip():
            problems.append("Escribe el código de la tarjeta regalo.")
        remaining = total - sum(amounts.values())
        payments = [{"method": m, "amount_cents": v, "gift_code": code if m == "tarjeta_regalo" else ""} for m, v in amounts.items() if v > 0]
        if remaining > 0:
            st.warning(f"Faltan por asignar {fmt_eur(remaining)}")
        elif remaining < 0:
            st.error(f"Te pasas {fmt_eur(-remaining)} del total")
        else:
            st.success("Importes cuadrados ✅")
        if remaining != 0:
            problems.append("Los importes deben sumar el total.")

    nif = st.text_input("NIF/DNI para la factura (opcional)", key=f"{ctx}_nif", value=(info or {}).get("dni", "") if info else "")
    for p in problems:
        st.caption(f"• {p}")
    if st.button(f"Confirmar cobro · {fmt_eur(total)}", type="primary", use_container_width=True, disabled=bool(problems), key=f"{ctx}_confirm"):
        try:
            inv = billing.create_invoice(lines, payments, client_id=cid, appointment_id=appt_id, discount_cents=discount, client_nif=nif)
        except ValueError as exc:
            st.error(str(exc))
            return
        st.session_state[done_key] = inv["id"]
        st.rerun(scope="fragment")


def _checkout_success(invoice_id: int) -> None:
    inv = billing.get_invoice(invoice_id)
    if not inv:
        st.error("No se encontró la factura.")
        return
    ui.html(
        f'<div class="jd-card gold" style="text-align:center"><div style="font-size:2.2rem">✅</div>'
        f'<div style="font-family:var(--font-title);font-size:1.8rem">Cobro registrado</div>'
        f'<div class="jd-muted">{ui.esc(inv["full_number"])} · {ui.esc(billing.payment_summary(inv))}</div>'
        f'<div class="jd-total" style="justify-content:center;gap:1rem"><b>{fmt_eur(inv["total_cents"])}</b></div></div>'
    )
    c1, c2 = st.columns(2)
    with c1:
        st.download_button("⬇️ Factura (PDF)", render_invoice_pdf(inv, settings.all_settings()), file_name=f"{inv['full_number']}.pdf",
                           mime="application/pdf", use_container_width=True, key=f"co_dl_{invoice_id}")
    client = clients.get_client(inv["client_id"])
    with c2:
        text = billing.receipt_text(inv, (client or {}).get("first_name", ""))
        ui.whatsapp_button("💬 Enviar ticket por WhatsApp", whatsapp_link((client or {}).get("phone"), text, settings.default_cc()), key=f"co_wa_{invoice_id}")
    if not settings.get("nif").strip():
        st.warning("Falta el NIF del centro en Ajustes → Centro: complétalo para que las facturas sean válidas.")
    if st.button("Cerrar", use_container_width=True, type="primary", key=f"co_close_{invoice_id}"):
        for key in [k for k in st.session_state if str(k).startswith("co_")]:
            del st.session_state[key]
        st.rerun()
