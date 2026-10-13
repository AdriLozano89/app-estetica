"""Fichero de clientas (CRM): búsqueda, ficha, historial, notas, monedero, consentimientos y derechos RGPD."""
from __future__ import annotations

import json

import pandas as pd
import streamlit as st

from core.config import CASH_IN_METHODS, PAYMENT_LABELS
from core.utils import age_from, fmt_date, fmt_datetime, fmt_eur, fmt_time, parse_date, today, whatsapp_link
from documents.consent_pdf import render_consent_pdf
from services import appointments, billing, catalog, clients, consents, settings, wallet
from ui import components as ui
from ui import dialogs
from ui.signature import signature_pad


# --------------------------------------------------------------------------- ficha
def _header(c: dict) -> None:
    age = age_from(c["birthdate"])
    meta = " · ".join(x for x in (c["phone"], c["email"], f"{age} años" if age is not None else "") if x) or "Sin datos de contacto"
    badges = (ui.badge("RGPD firmado", "ok") if c["rgpd_signed"] else ui.badge("RGPD pendiente", "warn")) + " " + \
             (ui.badge("Acepta marketing", "gold") if c["marketing_consent"] else "")
    ui.html(f'<div class="jd-card gold"><div style="font-family:var(--font-title);font-size:2.1rem;line-height:1.1">{ui.esc(clients.full_name(c))}</div>'
            f'<div class="jd-muted" style="margin:.25rem 0 .5rem">{ui.esc(meta)}</div>{badges}</div>')
    if (c["allergies"] or "").strip():
        ui.html(f'<div class="jd-alert">⚠️ <b>Alergias / avisos:</b> {ui.esc(c["allergies"])}</div>')

    stats = clients.client_stats(c["id"])
    nxt = stats["next"]
    ui.kpi_grid([
        ("Visitas", str(stats["visits"]), f"última: {fmt_date(stats['last_visit']) if stats['last_visit'] else '—'}"),
        ("Gastado", fmt_eur(stats["spent_cents"]), "facturado en total"),
        ("Monedero", fmt_eur(stats["wallet_cents"]), "saldo disponible"),
        ("Próxima cita", f"{fmt_date(nxt['start_ts'])[:5]} {fmt_time(nxt['start_ts'])}" if nxt else "—", nxt["service_name"] if nxt else "sin cita futura"),
    ])
    a, b, d = st.columns(3)
    if a.button("📅 Nueva cita", use_container_width=True, key=f"c_appt_{c['id']}"):
        dialogs.request("new_appointment", client_id=c["id"])
    if b.button("💶 Cobrar", use_container_width=True, key=f"c_pay_{c['id']}", type="primary"):
        dialogs.request("checkout", client_id=c["id"])
    with d:
        first = c["first_name"].split(" ")[0]
        ui.whatsapp_button("💬 WhatsApp", whatsapp_link(c["phone"], f"Hola {first}, ", settings.default_cc()), key=f"c_wa_{c['id']}")


def _tab_history(c: dict) -> None:
    with st.expander("➕ Añadir tratamiento al historial", expanded=False):
        with st.form(f"treat_form_{c['id']}", clear_on_submit=True):
            c1, c2 = st.columns(2)
            when = c1.date_input("Fecha", value=today(), format="DD/MM/YYYY")
            names = [s["name"] for s in catalog.list_services(active_only=False)]
            service = c2.selectbox("Tratamiento", names + ["Otro (escribir)"])
            other = st.text_input("Si es otro, escribe cuál")
            notes = st.text_area("Notas técnicas (zonas, parámetros, reacción)", height=80)
            c3, c4 = st.columns(2)
            products = c3.text_input("Productos usados")
            pro = c4.text_input("Profesional")
            if st.form_submit_button("Guardar en el historial", type="primary", use_container_width=True):
                name = other.strip() if service.startswith("Otro") else service
                if not name:
                    st.error("Indica el tratamiento.")
                else:
                    clients.add_treatment(c["id"], when, name, notes, products, pro)
                    st.toast("Tratamiento añadido ✅")
                    st.rerun()
    rows = clients.list_treatments(c["id"])
    if not rows:
        ui.empty_state("Aún no hay tratamientos en el historial. Se añaden solos al cobrar una cita.", "📋")
        return
    for t in rows[:60]:
        extra = " · ".join(x for x in (f"Productos: {t['products']}" if t["products"] else "", f"Profesional: {t['professional']}" if t["professional"] else "") if x)
        ui.html(f'<div class="jd-card"><b>{ui.esc(t["service_name"])}</b> <span class="jd-muted">· {fmt_date(t["date"])}</span>'
                + (f'<div style="margin-top:.3rem">{ui.esc(t["notes"])}</div>' if t["notes"] else "")
                + (f'<div class="jd-muted" style="font-size:.88rem;margin-top:.2rem">{ui.esc(extra)}</div>' if extra else "") + "</div>")
    with st.expander("Eliminar una anotación"):
        by_id = {t["id"]: t for t in rows}
        sel = st.selectbox("Anotación", list(by_id), key=f"t_del_{c['id']}", format_func=lambda i: f"{fmt_date(by_id[i]['date'])} · {by_id[i]['service_name']}")
        if st.button("Eliminar", key=f"t_del_btn_{c['id']}"):
            clients.delete_treatment(sel)
            st.rerun()


def _tab_notes(c: dict) -> None:
    st.caption("Información sensible: solo para el equipo del centro. Se guarda junto a la ficha.")
    with st.form(f"notes_form_{c['id']}"):
        allergies = st.text_area("Alergias y avisos importantes (se muestran en rojo en la agenda y al cobrar)", value=c["allergies"], height=80)
        medical = st.text_area("Notas médicas (medicación, patologías, embarazo…)", value=c["notes_medical"], height=110)
        tech = st.text_area("Notas técnicas y preferencias (tipo de piel, productos, gustos…)", value=c["notes_tech"], height=110)
        if st.form_submit_button("Guardar notas", type="primary", use_container_width=True):
            clients.update_client(c["id"], allergies=allergies, notes_medical=medical, notes_tech=tech)
            st.toast("Notas guardadas ✅")
            st.rerun()


def _tab_wallet(c: dict) -> None:
    bal = wallet.balance(c["id"])
    ui.kpi_grid([("Saldo del monedero", fmt_eur(bal), "disponible para pagar servicios")])
    t1, t2 = st.columns(2)
    with t1:
        with st.form(f"topup_{c['id']}", clear_on_submit=True):
            st.markdown("**Recargar monedero**")
            amount = st.number_input("Importe (€)", min_value=0.0, step=5.0, format="%.2f", key=f"tu_amt_{c['id']}")
            method = st.selectbox("Pagado con", list(CASH_IN_METHODS), format_func=lambda m: PAYMENT_LABELS[m], key=f"tu_m_{c['id']}")
            if st.form_submit_button("Recargar", type="primary", use_container_width=True):
                try:
                    wallet.topup(c["id"], round(amount * 100), method)
                except ValueError as exc:
                    st.error(str(exc))
                else:
                    st.toast("Monedero recargado ✅")
                    st.rerun()
    with t2:
        with st.form(f"adjust_{c['id']}", clear_on_submit=True):
            st.markdown("**Ajuste manual** (regalo o corrección, no mueve caja)")
            adj = st.number_input("Importe (+ suma, − resta)", step=5.0, format="%.2f", key=f"adj_amt_{c['id']}")
            why = st.text_input("Motivo", key=f"adj_why_{c['id']}")
            if st.form_submit_button("Aplicar ajuste", use_container_width=True):
                try:
                    wallet.adjust(c["id"], round(adj * 100), why)
                except ValueError as exc:
                    st.error(str(exc))
                else:
                    st.rerun()
    mv = wallet.movements(c["id"])
    if mv:
        st.dataframe(pd.DataFrame([{"Fecha": fmt_datetime(m["ts"]), "Concepto": m["concept"], "Importe": m["amount_cents"] / 100} for m in mv]),
                     hide_index=True, use_container_width=True, column_config={"Importe": st.column_config.NumberColumn(format="%+.2f €")})


def _tab_consents(c: dict) -> None:
    status = consents.status_for_client(c["id"])
    if status["rgpd"]:
        st.success("✅ Protección de datos (RGPD) firmada")
    else:
        st.warning("Falta la firma de protección de datos (RGPD).")
    st.markdown("##### Nuevo consentimiento")
    options = ["Protección de datos (RGPD)"] + [f"Consentimiento informado: {s['name']}" for s in catalog.list_services()]
    pick = st.selectbox("Documento", options, key=f"cs_pick_{c['id']}")
    is_rgpd = pick.startswith("Protección")
    treatment = "" if is_rgpd else pick.split(": ", 1)[1]
    text = consents.rgpd_text() if is_rgpd else consents.treatment_consent_text(treatment)
    with st.expander("Leer el texto que se va a firmar"):
        st.text(text)
    marketing = st.checkbox(consents.MARKETING_TEXT, value=bool(c["marketing_consent"]), key=f"cs_mk_{c['id']}") if is_rgpd else None
    name = st.text_input("Nombre completo de quien firma", value=clients.full_name(c), key=f"cs_name_{c['id']}")
    nonce = st.session_state.get(f"cs_nonce_{c['id']}", 0)
    st.caption("Firma con el dedo (móvil/tablet) o con el ratón:")
    sig = signature_pad(key=f"sig_{c['id']}_{nonce}")
    if sig is None:
        st.caption("Si no dibujas firma, el documento llevará tu nombre en letra manuscrita digital.")
    if st.button("✍️ Guardar consentimiento firmado", type="primary", use_container_width=True, key=f"cs_save_{c['id']}"):
        try:
            cid = consents.save_consent(c["id"], consents.KIND_RGPD if is_rgpd else consents.KIND_TREATMENT, name, sig, treatment, marketing)
        except ValueError as exc:
            st.error(str(exc))
        else:
            st.session_state[f"cs_nonce_{c['id']}"] = nonce + 1
            st.session_state[f"cs_last_{c['id']}"] = cid
            st.toast("Consentimiento guardado ✅")
            st.rerun()

    st.markdown("##### Firmados")
    rows = consents.list_consents(c["id"])
    if not rows:
        ui.empty_state("Todavía no hay consentimientos firmados.", "✍️")
    for r in rows:
        title = "Protección de datos (RGPD)" if r["kind"] == "rgpd" else f"Consentimiento: {r['treatment']}"
        a, b, d = st.columns([4, 2, 2], vertical_alignment="center")
        ok = consents.verify_consent(r["id"])
        a.markdown(f"**{title}**  \n<span class='jd-muted'>{consents.valid_today_label(r)} · {'🔒 íntegro' if ok else '⚠️ alterado'}</span>", unsafe_allow_html=True)
        full = consents.get_consent(r["id"])
        b.download_button("⬇️ PDF", render_consent_pdf(full, clients.full_name(c), c["dni"]), file_name=f"consentimiento_{r['id']}.pdf",
                          mime="application/pdf", key=f"cs_pdf_{r['id']}", use_container_width=True)
        if not r["revoked"] and d.button("Revocar", key=f"cs_rev_{r['id']}", use_container_width=True):
            consents.revoke(r["id"])
            st.rerun()


def _tab_activity(c: dict) -> None:
    hist = appointments.client_history(c["id"], 40)
    if hist:
        st.markdown("##### Citas")
        for a in hist[:15]:
            st.markdown(ui.appointment_card(a).replace(fmt_time(a["start_ts"]), f"{fmt_date(a['start_ts'])[:5]}", 1), unsafe_allow_html=True)
    inv = billing.list_invoices(client_id=c["id"])
    if inv:
        st.markdown("##### Facturas")
        st.dataframe(pd.DataFrame([{"Nº": i["full_number"], "Fecha": fmt_date(i["issued_at"]), "Total": i["total_cents"] / 100} for i in inv]),
                     hide_index=True, use_container_width=True, column_config={"Total": st.column_config.NumberColumn(format="%.2f €")})
    if not hist and not inv:
        ui.empty_state("Sin actividad todavía.", "📅")


def _tab_data(c: dict) -> None:
    with st.form(f"data_form_{c['id']}"):
        a, b = st.columns(2)
        first = a.text_input("Nombre *", value=c["first_name"])
        last = b.text_input("Apellidos", value=c["last_name"])
        a, b = st.columns(2)
        phone = a.text_input("Móvil", value=c["phone"])
        email = b.text_input("Email", value=c["email"])
        a, b = st.columns(2)
        birth = a.date_input("Nacimiento", value=parse_date(c["birthdate"]), min_value=parse_date("1920-01-01"), max_value=today(), format="DD/MM/YYYY")
        dni = b.text_input("DNI/NIE", value=c["dni"])
        address = st.text_input("Dirección", value=c["address"])
        source = st.text_input("¿Cómo nos conoció?", value=c["source"])
        marketing = st.checkbox("Acepta comunicaciones comerciales y felicitaciones", value=bool(c["marketing_consent"]))
        if st.form_submit_button("Guardar datos", type="primary", use_container_width=True):
            try:
                clients.update_client(c["id"], first_name=first, last_name=last, phone=phone, email=email, birthdate=birth, dni=dni,
                                      address=address, source=source, marketing_consent=marketing)
            except ValueError as exc:
                st.error(str(exc))
            else:
                st.toast("Datos guardados ✅")
                st.rerun()
    with st.expander("🔐 Derechos RGPD de la clienta"):
        data = json.dumps(clients.export_client_data(c["id"]), ensure_ascii=False, indent=2, default=str).encode("utf-8")
        st.download_button("⬇️ Exportar todos sus datos (acceso / portabilidad)", data, file_name=f"datos_{c['id']}.json", mime="application/json", key=f"exp_{c['id']}")
        st.caption("Supresión: elimina sus datos personales y consentimientos, pero conserva las facturas (obligación legal) sin su nombre.")
        if st.checkbox("Entiendo que es irreversible", key=f"anon_ok_{c['id']}") and st.button("Anonimizar clienta", key=f"anon_{c['id']}"):
            clients.anonymize_client(c["id"])
            st.session_state.pop("selected_client", None)
            st.rerun()
        if st.button("Archivar (ocultar sin borrar)", key=f"arch_{c['id']}"):
            clients.update_client(c["id"], active=False)
            st.session_state.pop("selected_client", None)
            st.rerun()


# --------------------------------------------------------------------------- página
def render() -> None:
    ui.page_header("Fichero de clientas", "Historial, notas, monedero y consentimientos")
    pending = st.session_state.pop("_open_client", None)  # ficha pedida desde otra pantalla o recién creada
    if pending:
        st.session_state.update({"cl_query": "", "cl_filter": "todos", "cl_sel_box": pending, "selected_client": pending})
    c1, c2 = st.columns([4, 1.4], vertical_alignment="bottom")
    query = c1.text_input("Buscar", placeholder="Nombre, teléfono o email…", key="cl_query", label_visibility="collapsed")
    if c2.button("➕ Nueva clienta", type="primary", use_container_width=True, key="cl_new"):
        dialogs.request("new_client")
    filt = ui.choice("Filtro", list(clients.FILTERS), key="cl_filter", default="todos", format_func=lambda k: clients.FILTERS[k])
    rows = clients.search_clients(query, filt)

    if not rows:
        ui.empty_state("No hay clientas con ese criterio." if (query or filt != "todos") else "Aún no hay clientas. ¡Crea la primera!", "👤")
        return
    st.caption(f"{len(rows)} clienta(s)")
    st.dataframe(clients.clients_dataframe(rows[:300]).drop(columns=["id"]), hide_index=True, use_container_width=True, height=min(60 + 35 * len(rows), 280))

    ids = [r["id"] for r in rows]
    names = {r["id"]: ui.client_label(r) for r in rows}
    current = st.session_state.get("selected_client")
    options = [None] + ids
    sel = st.selectbox("Abrir ficha", options, index=options.index(current) if current in options else 0, key="cl_sel_box",
                       format_func=lambda i: "— elige una clienta —" if i is None else names[i])
    if sel is None and current in ids:  # ficha abierta desde otra pantalla
        sel = current
    st.session_state["selected_client"] = sel
    if sel is None:
        return
    client = clients.get_client(sel)
    if not client:
        return
    st.divider()
    _header(client)
    t = st.tabs(["Historial", "Notas", "Monedero", "Consentimientos", "Actividad", "Datos"])
    with t[0]:
        _tab_history(client)
    with t[1]:
        _tab_notes(client)
    with t[2]:
        _tab_wallet(client)
    with t[3]:
        _tab_consents(client)
    with t[4]:
        _tab_activity(client)
    with t[5]:
        _tab_data(client)
