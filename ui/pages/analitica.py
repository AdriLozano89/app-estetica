"""Analítica, control legal (cadena de facturas) y cumplimiento RGPD."""
from __future__ import annotations

import streamlit as st

from core.utils import fmt_date, fmt_eur, today
from services import analytics, backup, billing, clients, consents
from ui import components as ui

GOLD = "#e6c566"


def _analytics() -> None:
    key = ui.choice("Periodo", list(analytics.PERIODS), key="an_period", default="mes", format_func=lambda k: analytics.PERIODS[k])
    start, end = analytics.period_bounds(key)
    st.caption(f"Del {fmt_date(start)} al {fmt_date(end)}")
    k = analytics.kpis(start, end)
    ui.kpi_grid([
        ("Facturación", fmt_eur(k["revenue_cents"]), f"base {fmt_eur(k['base_cents'])}"),
        ("Ticket medio", fmt_eur(k["avg_ticket_cents"]), f"{k['tickets']} tickets"),
        ("Citas", str(k["appointments"]), f"{k['completed']} realizadas"),
        ("Cancel./ausencias", f"{k['loss_rate'] * 100:.0f} %", f"{k['cancelled']} canc. · {k['no_shows']} no vino"),
        ("Clientas nuevas", str(k["new_clients"]), "en el periodo"),
    ])
    daily = analytics.revenue_by_day(start, end)
    if daily["Ingresos (€)"].sum() == 0:
        ui.empty_state("Todavía no hay ventas en este periodo.", "📈")
        return
    st.markdown("##### Ingresos por día")
    st.bar_chart(daily, color=GOLD, height=240)
    a, b = st.columns(2)
    with a:
        st.markdown("##### Servicios más vendidos")
        top = analytics.top_services(start, end)
        st.bar_chart(top[["Ingresos (€)"]], color=GOLD, horizontal=True, height=260)
    with b:
        st.markdown("##### Cómo pagan")
        mix = analytics.payment_mix(start, end)
        st.bar_chart(mix, color=GOLD, height=260)
    a, b = st.columns(2)
    with a:
        st.markdown("##### Citas por día de la semana")
        st.bar_chart(analytics.busy_by_weekday(start, end), color=GOLD, height=220)
    with b:
        st.markdown("##### Citas por hora")
        st.bar_chart(analytics.busy_by_hour(start, end), color=GOLD, height=220)
    st.markdown("##### Mejores clientas")
    tc = analytics.top_clients(start, end)
    st.dataframe(tc, use_container_width=True)
    st.markdown(f"##### Facturación mensual {today().year}")
    st.line_chart(analytics.revenue_by_month(today().year), color=GOLD, height=220)


def _legal() -> None:
    st.markdown("##### Integridad del registro de facturas")
    st.caption("Cada factura guarda una huella SHA-256 que incluye la de la anterior. Si alguien altera un dato, la cadena se rompe.")
    if st.button("🔍 Verificar cadena ahora", type="primary", key="lg_verify"):
        st.session_state["lg_result"] = billing.verify_chain()
    res = st.session_state.get("lg_result")
    if res:
        if res["ok"]:
            st.success(f"Cadena íntegra: {res['checked']} registros verificados.")
        else:
            st.error("Se han detectado incidencias:")
            for e in res["errors"]:
                st.write(f"• {e}")
        if res["last_hash"]:
            st.code(res["last_hash"], language=None)
    st.markdown("##### Libro de facturas")
    c1, c2 = st.columns(2)
    d1 = c1.date_input("Desde", value=today().replace(month=1, day=1), format="DD/MM/YYYY", key="lg_from")
    d2 = c2.date_input("Hasta", value=today(), format="DD/MM/YYYY", key="lg_to")
    df = backup.invoices_register_df(d1, d2)
    st.dataframe(df, hide_index=True, use_container_width=True)
    st.download_button("⬇️ Descargar CSV", backup.csv_bytes(df), file_name=f"facturas_{d1}_{d2}.csv", mime="text/csv", key="lg_dl")
    st.info("**Veri*Factu: preparada, no certificada.** Las facturas ya llevan numeración correlativa, huella encadenada y tipos F2/R5, "
            "pero el envío a la AEAT y la declaración responsable del software requieren un sistema homologado. "
            "Consulta con tu gestoría antes de depender de esta app como sistema de facturación oficial.")


def _rgpd() -> None:
    rows = consents.missing_rgpd()
    if not rows:
        st.success("Todas las clientas activas tienen el consentimiento RGPD firmado.")
        return
    st.warning(f"{len(rows)} clienta(s) sin consentimiento RGPD firmado.")
    for r in rows:
        a, b = st.columns([4, 2], vertical_alignment="center")
        a.markdown(f"**{ui.esc(clients.full_name(r))}**  \n{ui.esc(r['phone'] or 'sin teléfono')}")
        if b.button("Abrir ficha", key=f"rg_{r['id']}", use_container_width=True):
            ui.goto("clientes", _open_client=r["id"])


def render() -> None:
    ui.page_header("Analítica y legal", "Cómo va el centro y que todo esté en regla")
    t1, t2, t3 = st.tabs(["Analítica", "Legal", "RGPD"])
    with t1:
        _analytics()
    with t2:
        _legal()
    with t3:
        _rgpd()
