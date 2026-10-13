"""Caja y finanzas: arqueo diario, facturas (con rectificativas), gastos e impuestos trimestrales."""
from __future__ import annotations



import pandas as pd
import streamlit as st

from core.config import CASH_IN_METHODS, INVOICE_RECTIFY, INVOICE_SIMPLE, PAYMENT_LABELS
from core.utils import fmt_date, fmt_datetime, fmt_eur, quarter_bounds, quarter_of, today
from documents.invoice_pdf import render_invoice_pdf
from services import backup, billing, cashbox, expenses, settings, taxes
from ui import components as ui
from ui import dialogs

KIND_LABEL = {INVOICE_SIMPLE: "Factura simplificada", INVOICE_RECTIFY: "Rectificativa"}


# --------------------------------------------------------------------------- caja del día
def _tab_cash() -> None:
    c1, c2 = st.columns([2, 1], vertical_alignment="bottom")
    day = c1.date_input("Día", value=today(), max_value=today(), format="DD/MM/YYYY", key="caja_day")
    if c2.button("➕ Venta rápida", type="primary", use_container_width=True, key="caja_quick"):
        dialogs.request("checkout")

    s = cashbox.day_summary(day)
    ui.kpi_grid([
        ("Cobrado", fmt_eur(s["money_in_cents"]), "efectivo + tarjeta + Bizum"),
        ("Tickets", str(s["tickets"]), f"ventas {fmt_eur(s['sales_cents'])}"),
        ("Efectivo", fmt_eur(s["by_method"].get("efectivo", 0)), "entró en caja"),
        ("Tarjeta + Bizum", fmt_eur(s["by_method"].get("tarjeta", 0) + s["by_method"].get("bizum", 0)), "cobrado digital"),
    ])

    ui.section("Arqueo por método de pago")
    rows = [[ui.payment_label(m), fmt_eur(s["by_method"].get(m, 0)), "dinero que entra" if m in CASH_IN_METHODS else "saldo consumido (ya cobrado antes)"]
            for m in PAYMENT_LABELS]
    rows.append(["TOTAL COBRADO", fmt_eur(s["money_in_cents"]), ""])
    ui.html_table(["Método", "Importe", "Nota"], rows, right={1}, bold_last=True)
    if s["by_kind"]:
        with st.expander("Desglose por concepto"):
            ui.html_table(["Concepto", "Importe"], [[cashbox.KIND_LABELS.get(k, k), fmt_eur(v)] for k, v in s["by_kind"].items()], right={1})

    # --- cierre
    ui.section("Cierre de caja", "Cuenta el efectivo y la app calcula la diferencia")
    closing = cashbox.get_closing(day)
    if closing:
        kind = "success" if closing["diff_cents"] == 0 else "warning"
        getattr(st, kind)(f"Caja cerrada el {fmt_datetime(closing['closed_at'])}: esperado {fmt_eur(closing['expected_cents'])}, "
                          f"contado {fmt_eur(closing['counted_cents'])}, diferencia {fmt_eur(closing['diff_cents'], sign=True)}.")
    f1, f2 = st.columns(2)
    with f1:
        opening = ui.money_input("Fondo de caja inicial (efectivo con el que empezaste)", closing["opening_cents"] if closing else cashbox.suggested_opening(day), key=f"caja_open_{day}")
    expected = cashbox.expected_cash(day, opening)
    with f2:
        counted = ui.money_input("Efectivo contado ahora", closing["counted_cents"] if closing else expected, key=f"caja_count_{day}")
    diff = counted - expected
    ui.kpi_grid([
        ("Efectivo esperado", fmt_eur(expected), f"fondo + efectivo − gastos en efectivo ({fmt_eur(s['cash_expenses_cents'])})"),
        ("Diferencia", fmt_eur(diff, sign=True), "cuadra ✅" if diff == 0 else ("sobra" if diff > 0 else "falta")),
    ])
    notes = st.text_input("Notas del cierre (opcional)", value=closing["notes"] if closing else "", key=f"caja_notes_{day}")
    if st.button("🔒 Cerrar caja" if not closing else "🔒 Actualizar cierre", type="primary", use_container_width=True, key=f"caja_close_{day}"):
        cashbox.close_day(day, opening, counted, notes)
        st.toast("Caja guardada ✅")
        st.rerun()

    if s["movements"]:
        with st.expander(f"Movimientos del día ({len(s['movements'])})"):
            df = pd.DataFrame([{"Hora": m["ts"][11:16], "Concepto": m["concept"], "Método": PAYMENT_LABELS.get(m["method"], m["method"]),
                                "Importe": m["amount_cents"] / 100} for m in s["movements"]])
            st.dataframe(df, hide_index=True, use_container_width=True, column_config={"Importe": st.column_config.NumberColumn(format="%.2f €")})
    hist = cashbox.list_closings(30)
    if hist:
        with st.expander("Historial de cierres"):
            st.dataframe(pd.DataFrame([{"Día": fmt_date(h["date"]), "Esperado": h["expected_cents"] / 100, "Contado": h["counted_cents"] / 100,
                                        "Diferencia": h["diff_cents"] / 100, "Notas": h["notes"]} for h in hist]),
                         hide_index=True, use_container_width=True)


# --------------------------------------------------------------------------- facturas
def _tab_invoices() -> None:
    check = billing.verify_chain()
    if check["ok"]:
        st.success(f"🔗 Cadena de facturación íntegra · {check['checked']} registro(s) verificados")
    else:
        st.error("⚠️ Se han detectado incoherencias en la cadena de facturación:")
        for err in check["errors"][:10]:
            st.write(f"• {err}")

    f1, f2, f3 = st.columns([1, 1, 2])
    start = f1.date_input("Desde", value=today().replace(day=1), format="DD/MM/YYYY", key="inv_from")
    end = f2.date_input("Hasta", value=today(), format="DD/MM/YYYY", key="inv_to")
    text = f3.text_input("Buscar (nº o clienta)", key="inv_text", placeholder="FS-000012 o nombre")
    invoices = billing.list_invoices(start, end, text)
    if not invoices:
        ui.empty_state("No hay facturas en este periodo.", "🧾")
        return
    total = sum(i["total_cents"] for i in invoices)
    ui.kpi_grid([("Facturas", str(len(invoices)), "incluye rectificativas"), ("Importe neto", fmt_eur(total), "ventas − devoluciones")])

    df = pd.DataFrame([{
        "Nº": i["full_number"], "Fecha": fmt_date(i["issued_at"]), "Clienta": i["client_name"] or "—", "Tipo": KIND_LABEL.get(i["kind"], i["kind"]),
        "Base": i["base_cents"] / 100, "IVA": i["vat_cents"] / 100, "Total": i["total_cents"] / 100,
        "Estado": "Rectificada" if i["status"] == "rectificada" else "Emitida",
    } for i in invoices])
    st.dataframe(df, hide_index=True, use_container_width=True,
                 column_config={c: st.column_config.NumberColumn(format="%.2f €") for c in ("Base", "IVA", "Total")})
    st.download_button("⬇️ Descargar listado (CSV)", backup._csv(backup.invoices_register_df(start, end)), file_name=f"facturas_{start}_{end}.csv", mime="text/csv")

    ui.section("Ver o anular una factura")
    by_id = {i["id"]: i for i in invoices}
    sel = st.selectbox("Factura", list(by_id), key="inv_sel",
                       format_func=lambda i: f"{by_id[i]['full_number']} · {fmt_date(by_id[i]['issued_at'])} · {fmt_eur(by_id[i]['total_cents'])} · {by_id[i]['client_name'] or 'sin clienta'}")
    inv = billing.get_invoice(sel)
    if not inv:
        return
    original = billing.get_invoice(inv["rectifies_id"]) if inv["rectifies_id"] else None
    ui.html_table(["Concepto", "Cant.", "IVA", "Importe"],
                  [[ln["description"], f"{ln['qty']:g}", f"{ln['vat_rate']} %", fmt_eur(ln["total_cents"])] for ln in inv["lines"]] +
                  [["TOTAL", "", "", fmt_eur(inv["total_cents"])]], right={1, 2, 3}, bold_last=True)
    st.caption(f"Pago: {billing.payment_summary(inv)} · Huella: {inv['hash'][:20]}…")
    st.download_button("⬇️ Descargar PDF", render_invoice_pdf(inv, settings.all_settings(), original["full_number"] if original else ""),
                       file_name=f"{inv['full_number']}.pdf", mime="application/pdf", key=f"inv_pdf_{sel}")
    if inv["kind"] == INVOICE_SIMPLE and inv["status"] == "emitida":
        with st.expander("↩️ Anular esta factura (crea una rectificativa)"):
            st.caption("La factura original no se borra: se emite una rectificativa por el importe contrario y se devuelve el cobro.")
            reason = st.text_input("Motivo", key=f"inv_reason_{sel}", placeholder="Ej.: cobro duplicado, error en el importe…")
            refund = st.selectbox("Devolver en", ["(mismo método del cobro)"] + [m for m in CASH_IN_METHODS], key=f"inv_refund_{sel}",
                                  format_func=lambda m: m if m.startswith("(") else PAYMENT_LABELS[m])
            if st.checkbox("Entiendo que esta acción queda registrada y no se puede deshacer", key=f"inv_ok_{sel}"):
                if st.button("Emitir rectificativa", type="primary", key=f"inv_rect_{sel}"):
                    try:
                        r = billing.rectify_invoice(sel, reason, None if refund.startswith("(") else refund)
                    except ValueError as exc:
                        st.error(str(exc))
                    else:
                        st.toast(f"Rectificativa {r['full_number']} emitida ✅")
                        st.rerun()
    elif inv["status"] == "rectificada":
        st.info("Esta factura ya fue rectificada.")


# --------------------------------------------------------------------------- gastos
def _tab_expenses() -> None:
    with st.expander("➕ Nuevo gasto", expanded=False):
        with st.form("exp_form", clear_on_submit=True):
            c1, c2 = st.columns(2)
            concept = c1.text_input("Concepto *", placeholder="Ej.: Cera y aceites")
            supplier = c2.text_input("Proveedor")
            c3, c4 = st.columns(2)
            when = c3.date_input("Fecha", value=today(), format="DD/MM/YYYY")
            total = c4.number_input("Total pagado (IVA incluido)", min_value=0.0, step=1.0, format="%.2f")
            c5, c6, c7 = st.columns(3)
            category = c5.selectbox("Categoría", expenses.CATEGORIES)
            rate = c6.selectbox("IVA %", [21, 10, 4, 0])
            method = c7.selectbox("Pagado con", list(expenses.METHODS), format_func=lambda m: expenses.METHODS[m])
            c8, c9 = st.columns(2)
            ref = c8.text_input("Nº de factura del proveedor")
            deductible = c9.checkbox("IVA deducible", value=True, help="Desmárcalo si la factura no permite deducir el IVA.")
            if st.form_submit_button("Guardar gasto", type="primary", use_container_width=True):
                try:
                    expenses.add_expense(concept, round(total * 100), rate, when, supplier, category, method, deductible, ref)
                except ValueError as exc:
                    st.error(str(exc))
                else:
                    st.toast("Gasto guardado ✅")
                    st.rerun()

    q_start, q_end = quarter_bounds(today().year, quarter_of(today()))
    c1, c2 = st.columns(2)
    start = c1.date_input("Desde", value=q_start, format="DD/MM/YYYY", key="exp_from")
    end = c2.date_input("Hasta", value=q_end, format="DD/MM/YYYY", key="exp_to")
    rows = expenses.list_expenses(start, end)
    if not rows:
        ui.empty_state("No hay gastos registrados en este periodo.", "🧾")
        return
    ui.kpi_grid([("Total gastos", fmt_eur(sum(r["total_cents"] for r in rows)), f"{len(rows)} apunte(s)"),
                 ("IVA soportado", fmt_eur(sum(r["vat_cents"] for r in rows if r["vat_deductible"])), "deducible")])
    st.dataframe(pd.DataFrame([{"Fecha": fmt_date(r["date"]), "Concepto": r["concept"], "Proveedor": r["supplier"], "Categoría": r["category"],
                                "Base": r["base_cents"] / 100, "IVA": r["vat_cents"] / 100, "Total": r["total_cents"] / 100,
                                "Pago": expenses.METHODS.get(r["method"], r["method"])} for r in rows]),
                 hide_index=True, use_container_width=True,
                 column_config={c: st.column_config.NumberColumn(format="%.2f €") for c in ("Base", "IVA", "Total")})
    with st.expander("Eliminar un gasto"):
        by_id = {r["id"]: r for r in rows}
        sel = st.selectbox("Gasto", list(by_id), key="exp_del_sel",
                           format_func=lambda i: f"{fmt_date(by_id[i]['date'])} · {by_id[i]['concept']} · {fmt_eur(by_id[i]['total_cents'])}")
        if st.checkbox("Confirmo que quiero eliminarlo", key="exp_del_ok") and st.button("Eliminar gasto", key="exp_del_btn"):
            expenses.delete_expense(sel)
            st.rerun()


# --------------------------------------------------------------------------- impuestos
def _tab_taxes() -> None:
    st.info("Estimaciones orientativas con los datos registrados en la app. La presentación oficial debe revisarla tu gestoría.")
    c1, c2 = st.columns(2)
    year = c1.selectbox("Año", [today().year, today().year - 1, today().year - 2], key="tax_year")
    quarter = c2.selectbox("Trimestre", [1, 2, 3, 4], index=quarter_of(today()) - 1, key="tax_q", format_func=lambda q: f"{q}T")
    iva = taxes.iva_quarter(year, quarter)

    ui.section("Modelo 303 · IVA", f"{fmt_date(iva['start'])} – {fmt_date(iva['end'])}")
    rows = []
    for r in iva["accrued"]:
        cas = taxes.CASILLAS_DEVENGADO.get(r["rate"])
        rows.append([f"IVA devengado {r['rate']} %" + (f" (casillas {cas[0]}/{cas[1]})" if cas else ""), fmt_eur(r["base"]), fmt_eur(r["vat"])])
    rows.append(["TOTAL IVA DEVENGADO", fmt_eur(iva["sales_base_cents"]), fmt_eur(iva["accrued_total_cents"])])
    for r in iva["input"]:
        rows.append([f"IVA soportado deducible {r['rate']} %", fmt_eur(r["base"]), fmt_eur(r["vat"])])
    rows.append(["TOTAL IVA SOPORTADO", "", fmt_eur(iva["input_total_cents"])])
    ui.html_table(["Concepto", "Base", "Cuota"], rows, right={1, 2})
    if iva["result_cents"] > 0:
        ui.kpi_grid([("A ingresar (303)", fmt_eur(iva["to_pay_cents"]), "devengado − soportado")])
    else:
        ui.kpi_grid([("Resultado 303", fmt_eur(0), f"a compensar {fmt_eur(iva['to_offset_cents'])}")])

    ui.section("Modelo 130 · IRPF", "Pago fraccionado acumulado del año (estimación directa)")
    auto_prev = taxes.irpf_130(year, quarter)["previous_payments_cents"]
    p1, p2 = st.columns(2)
    with p1:
        prev = ui.money_input("Pagos 130 de trimestres anteriores", auto_prev, key=f"tax_prev_{year}_{quarter}", help="Se calculan con los datos de la app; ajústalo con lo que realmente ingresaste.")
    with p2:
        withh = ui.money_input("Retenciones soportadas (acumuladas)", 0, key=f"tax_wh_{year}_{quarter}", help="Solo si tus clientes te retienen IRPF en factura.")
    irpf = taxes.irpf_130(year, quarter, previous_payments_cents=prev, withholdings_cents=withh)
    ui.html_table(["Concepto", "Importe"], [
        ["Ingresos acumulados (bases imponibles)", fmt_eur(irpf["income_cents"])],
        ["Gastos deducibles acumulados", fmt_eur(irpf["expenses_cents"])],
        ["Rendimiento neto", fmt_eur(irpf["net_cents"])],
        ["20 % del rendimiento neto", fmt_eur(irpf["gross_payment_cents"])],
        ["− Pagos de trimestres anteriores", fmt_eur(irpf["previous_payments_cents"])],
        ["− Retenciones soportadas", fmt_eur(irpf["withholdings_cents"])],
        ["RESULTADO A INGRESAR (130)", fmt_eur(irpf["to_pay_cents"])],
    ], right={1}, bold_last=True)

    reserve = iva["to_pay_cents"] + irpf["to_pay_cents"]
    ui.html(f'<div class="jd-card gold"><div class="jd-kpi-label">Reserva recomendada este trimestre</div>'
            f'<div class="jd-kpi-value">{fmt_eur(reserve)}</div><div class="jd-kpi-hint">303 + 130 estimados. Aparta este importe para no tener sorpresas.</div></div>')
    st.download_button("⬇️ Paquete para la gestoría (ZIP con libros y resumen)", backup.quarter_pack_zip(year, quarter),
                       file_name=f"gestoria_{year}T{quarter}.zip", mime="application/zip", use_container_width=True, key=f"tax_zip_{year}_{quarter}")


def render() -> None:
    ui.page_header("Caja y finanzas", "Arqueo diario, facturas, gastos e impuestos")
    t1, t2, t3, t4 = st.tabs(["Caja del día", "Facturas", "Gastos", "Impuestos"])
    with t1:
        _tab_cash()
    with t2:
        _tab_invoices()
    with t3:
        _tab_expenses()
    with t4:
        _tab_taxes()
