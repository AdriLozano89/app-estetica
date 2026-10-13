"""Marketing y regalos: tarjetas regalo (generador + gestor), cumpleaños, reactivación y plantillas de mensajes."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from core.config import CASH_IN_METHODS, GIFT_ACTIVE, GIFT_EMPTY, GIFT_EXPIRED, GIFT_VOID, PAYMENT_LABELS
from core.utils import MONTHS_ES, fmt_date, fmt_datetime, fmt_eur, render_template, today, whatsapp_link
from documents.giftcard import render_giftcard
from services import catalog, clients, giftcards, settings
from ui import components as ui

STATUS_FILTERS = {"todas": "Todas", GIFT_ACTIVE: "Activas", GIFT_EMPTY: "Agotadas", GIFT_EXPIRED: "Caducadas", GIFT_VOID: "Anuladas"}
TEMPLATES = {
    "tpl_reminder": ("Recordatorio de cita", "{nombre} {centro} {servicio} {fecha} {hora}"),
    "tpl_birthday": ("Felicitación de cumpleaños", "{nombre} {centro}"),
    "tpl_reactivation": ("Reactivación de clientas", "{nombre} {centro}"),
    "tpl_giftcard": ("Envío de tarjeta regalo", "{nombre} {importe} {codigo} {caducidad} {centro}"),
    "tpl_receipt": ("Ticket por WhatsApp", "{nombre} {numero} {importe} {centro}"),
}


def _render_png(card: dict) -> bytes:
    cfg = settings.all_settings()
    return render_giftcard(card, cfg["business_name"], cfg["phone"], cfg["city"])


def _gift_message(card: dict, to_name: str) -> str:
    cfg = settings.all_settings()
    return render_template(cfg["tpl_giftcard"], nombre=(to_name or "").split(" ")[0], importe=fmt_eur(card["initial_cents"]),
                           codigo=card["code"], caducidad=fmt_date(card["expires_at"]), centro=cfg["business_name"])


# --------------------------------------------------------------------------- tarjetas regalo: crear
def _gift_create() -> None:
    left, right = st.columns([1, 1.15])
    with left:
        preset = ui.choice("Importe", [30, 50, 75, 100, "Otro"], key="gc_preset", default=50, format_func=lambda v: "Otro" if v == "Otro" else f"{v} €")
        amount = ui.money_input("Importe personalizado", 5000, key="gc_custom", min_cents=100) if preset == "Otro" else int(preset) * 100
        a, b = st.columns(2)
        buyer = a.text_input("Quién la compra", key="gc_buyer")
        buyer_phone = b.text_input("Móvil del comprador", key="gc_bphone")
        a, b = st.columns(2)
        rcpt = a.text_input("Para quién es", key="gc_rcpt")
        rcpt_phone = b.text_input("Móvil de quien la recibe", key="gc_rphone")
        message = st.text_area("Dedicatoria", max_chars=140, height=80, key="gc_msg", placeholder="Ej.: Feliz cumpleaños, te mereces un día de mimos.")
        services = ["Cualquier servicio"] + [s["name"] for s in catalog.list_services()]
        service = st.selectbox("Válida para", services, key="gc_service")
        a, b = st.columns(2)
        method = a.selectbox("Pagada con", list(CASH_IN_METHODS), key="gc_method", format_func=lambda m: PAYMENT_LABELS[m])
        months = b.number_input("Validez (meses)", 1, 36, int(settings.get("gift_validity_months", "12") or 12), key="gc_months")
    preview = {
        "code": "JD-XXXX-XXXX", "initial_cents": amount, "recipient_name": rcpt, "buyer_name": buyer, "message": message,
        "for_service": "" if service == "Cualquier servicio" else service,
        "expires_at": giftcards.add_months(today(), int(months)).isoformat(),
    }
    with right:
        st.caption("Vista previa (el código real se genera al emitirla)")
        st.image(_render_png(preview), use_container_width=True)
    if st.button("🎁 Emitir tarjeta regalo", type="primary", use_container_width=True, key="gc_issue"):
        try:
            card = giftcards.issue(amount, method, buyer, buyer_phone, rcpt, rcpt_phone, message, preview["for_service"], int(months))
        except ValueError as exc:
            st.error(str(exc))
        else:
            st.session_state["gc_last"] = card["id"]
            st.rerun()

    last = giftcards.get(st.session_state["gc_last"]) if st.session_state.get("gc_last") else None
    if last:
        st.success(f"Tarjeta {last['code']} emitida y cobrada ({fmt_eur(last['initial_cents'])}).")
        png = _render_png(last)
        st.image(png, use_container_width=True)
        c1, c2, c3 = st.columns(3)
        c1.download_button("⬇️ Descargar PNG", png, file_name=f"tarjeta_{last['code']}.png", mime="image/png", use_container_width=True, key="gc_dl_last")
        with c2:
            ui.whatsapp_button("💬 Enviar a quien la recibe", whatsapp_link(last["recipient_phone"], _gift_message(last, last["recipient_name"]), settings.default_cc()), key="gc_wa_r")
        with c3:
            ui.whatsapp_button("💬 Enviar al comprador", whatsapp_link(last["buyer_phone"], _gift_message(last, last["buyer_name"]), settings.default_cc()), key="gc_wa_b")
        st.caption("WhatsApp no permite adjuntar la imagen desde un enlace: descarga el PNG y adjúntalo en el chat que se abre.")


# --------------------------------------------------------------------------- tarjetas regalo: gestor
def _gift_manage() -> None:
    soon = giftcards.expiring_soon(30)
    all_cards = giftcards.list_cards()
    ui.kpi_grid([
        ("Saldo pendiente", fmt_eur(giftcards.outstanding_cents()), "en tarjetas vigentes"),
        ("Activas", str(sum(1 for c in all_cards if c["effective_status"] == GIFT_ACTIVE)), "con saldo por consumir"),
        ("Caducan en 30 días", str(len(soon)), fmt_eur(sum(c["balance_cents"] for c in soon))),
    ])
    for c in soon[:5]:
        st.warning(f"⏳ {c['code']} · {fmt_eur(c['balance_cents'])} caduca el {fmt_date(c['expires_at'])} ({c['recipient_name'] or c['buyer_name'] or 'sin nombre'})")
    f1, f2 = st.columns([2, 2])
    with f1:
        status = ui.choice("Estado", list(STATUS_FILTERS), key="gm_status", default="todas", format_func=lambda k: STATUS_FILTERS[k])
    text = f2.text_input("Buscar", key="gm_text", placeholder="Código, comprador o destinataria", label_visibility="collapsed")
    cards = giftcards.list_cards(status, text)
    if not cards:
        ui.empty_state("No hay tarjetas con ese filtro.", "🎁")
        return
    st.dataframe(pd.DataFrame([{
        "Código": c["code"], "Comprador": c["buyer_name"], "Para": c["recipient_name"], "Inicial": c["initial_cents"] / 100,
        "Saldo": c["balance_cents"] / 100, "Emitida": fmt_date(c["issued_at"]), "Caduca": fmt_date(c["expires_at"]),
        "Estado": STATUS_FILTERS.get(c["effective_status"], c["effective_status"]),
    } for c in cards]), hide_index=True, use_container_width=True,
        column_config={"Inicial": st.column_config.NumberColumn(format="%.2f €"), "Saldo": st.column_config.NumberColumn(format="%.2f €")})

    by_id = {c["id"]: c for c in cards}
    sel = st.selectbox("Ver tarjeta", list(by_id), key="gm_sel", format_func=lambda i: f"{by_id[i]['code']} · {fmt_eur(by_id[i]['balance_cents'])} · {by_id[i]['recipient_name'] or by_id[i]['buyer_name'] or '—'}")
    card = by_id[sel]
    png = _render_png(card)
    a, b = st.columns([1.2, 1])
    a.image(png, use_container_width=True)
    with b:
        st.download_button("⬇️ Descargar PNG", png, file_name=f"tarjeta_{card['code']}.png", mime="image/png", use_container_width=True, key=f"gm_dl_{sel}")
        ui.whatsapp_button("💬 Enviar por WhatsApp", whatsapp_link(card["recipient_phone"] or card["buyer_phone"], _gift_message(card, card["recipient_name"] or card["buyer_name"]), settings.default_cc()), key=f"gm_wa_{sel}")
        mv = giftcards.movements(sel)
        st.dataframe(pd.DataFrame([{"Fecha": fmt_datetime(m["ts"]), "Concepto": m["concept"], "Importe": m["amount_cents"] / 100} for m in mv]),
                     hide_index=True, use_container_width=True, column_config={"Importe": st.column_config.NumberColumn(format="%+.2f €")})
    if card["effective_status"] in (GIFT_ACTIVE, GIFT_EXPIRED) and card["status"] != GIFT_VOID:
        with st.expander("Anular tarjeta"):
            refund = st.selectbox("Devolver el saldo en", ["(no devolver)"] + list(CASH_IN_METHODS), key=f"gm_ref_{sel}",
                                  format_func=lambda m: m if m.startswith("(") else PAYMENT_LABELS[m])
            if st.checkbox("Confirmo la anulación", key=f"gm_ok_{sel}") and st.button("Anular", key=f"gm_void_{sel}"):
                try:
                    giftcards.void(sel, None if refund.startswith("(") else refund)
                except ValueError as exc:
                    st.error(str(exc))
                else:
                    st.rerun()


# --------------------------------------------------------------------------- cumpleaños y reactivación
def _birthdays() -> None:
    month = st.selectbox("Mes", list(range(1, 13)), index=today().month - 1, format_func=lambda m: MONTHS_ES[m - 1].capitalize(), key="bd_month")
    rows = clients.birthdays_in_month(month)
    if not rows:
        ui.empty_state("No hay cumpleaños este mes.", "🎂")
        return
    cfg = settings.all_settings()
    st.caption(f"{len(rows)} cumpleaños en {MONTHS_ES[month - 1]}")
    for r in rows:
        text = render_template(cfg["tpl_birthday"], nombre=r["first_name"].split(" ")[0], centro=cfg["business_name"])
        a, b = st.columns([4, 2], vertical_alignment="center")
        flag = "" if r["marketing_consent"] else " " + ui.badge("sin consentimiento de marketing", "warn")
        a.markdown(f'<div class="jd-appt"><div class="jd-appt-time">{r["day"]:02d}</div><div class="jd-appt-main"><div class="jd-appt-name">{ui.esc(clients.full_name(r))}</div>'
                   f'<div class="jd-appt-meta">cumple {r["turns"]} años{flag}</div></div></div>', unsafe_allow_html=True)
        with b:
            ui.whatsapp_button("🎂 Felicitar", whatsapp_link(r["phone"], text, settings.default_cc()), key=f"bd_{r['id']}")


def _reactivation() -> None:
    days = st.slider("Sin venir desde hace (días)", 45, 365, 90, step=15, key="re_days")
    rows, excluded = clients.inactive_clients(days)
    st.caption("Solo se muestran clientas con teléfono y que han aceptado recibir comunicaciones comerciales.")
    if excluded:
        st.info(f"{excluded} clienta(s) inactiva(s) no aparecen por no tener teléfono o consentimiento de marketing.")
    if not rows:
        ui.empty_state("No hay clientas para reactivar con estos criterios.", "💌")
        return
    cfg = settings.all_settings()
    for r in rows[:60]:
        text = render_template(cfg["tpl_reactivation"], nombre=r["first_name"].split(" ")[0], centro=cfg["business_name"])
        a, b = st.columns([4, 2], vertical_alignment="center")
        a.markdown(f'<div class="jd-appt"><div class="jd-appt-main"><div class="jd-appt-name">{ui.esc(clients.full_name(r))}</div>'
                   f'<div class="jd-appt-meta">última visita: {fmt_date(r["last_visit"]) if r["last_visit"] else "sin visitas"}</div></div></div>', unsafe_allow_html=True)
        with b:
            ui.whatsapp_button("💌 Escribir", whatsapp_link(r["phone"], text, settings.default_cc()), key=f"re_{r['id']}")


def _templates() -> None:
    cfg = settings.all_settings()
    st.caption("Estos textos alimentan los enlaces de WhatsApp de toda la app. Variables entre llaves, por ejemplo {nombre}.")
    with st.form("tpl_form"):
        values = {}
        for key, (title, variables) in TEMPLATES.items():
            values[key] = st.text_area(title, value=cfg[key], height=100, help=f"Variables: {variables}", key=f"tplf_{key}")
        if st.form_submit_button("Guardar plantillas", type="primary", use_container_width=True):
            settings.set_many(values)
            st.toast("Plantillas guardadas ✅")
            st.rerun()
    sample = render_template(cfg["tpl_reminder"], nombre="Ana", centro=cfg["business_name"], servicio="Limpieza facial", fecha="lunes 12 de octubre", hora="10:30")
    st.markdown("**Vista previa del recordatorio**")
    st.info(sample)


def render() -> None:
    ui.page_header("Marketing y regalos", "Tarjetas regalo, cumpleaños y fidelización")
    t1, t2, t3, t4 = st.tabs(["Tarjetas regalo", "Cumpleaños", "Reactivación", "Plantillas"])
    with t1:
        mode = ui.choice("Modo", ["Crear tarjeta", "Gestor de tarjetas"], key="gc_mode", default="Crear tarjeta")
        _gift_create() if mode == "Crear tarjeta" else _gift_manage()
    with t2:
        _birthdays()
    with t3:
        _reactivation()
    with t4:
        _templates()
