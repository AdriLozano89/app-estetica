"""Ajustes: datos del centro, servicios, horario, seguridad y copias de seguridad."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from core import security
from core.utils import now, to_cents
from documents.fonts import fonts_report
from services import backup, catalog, clients, settings
from ui import components as ui

DAYS = [(1, "Lun"), (2, "Mar"), (3, "Mié"), (4, "Jue"), (5, "Vie"), (6, "Sáb"), (0, "Dom")]


def _center() -> None:
    cfg = settings.all_settings()
    with st.form("set_center"):
        name = st.text_input("Nombre comercial", cfg["business_name"])
        legal = st.text_input("Razón social / titular", cfg["legal_name"])
        a, b = st.columns(2)
        nif = a.text_input("NIF", cfg["nif"])
        phone = b.text_input("Teléfono", cfg["phone"])
        address = st.text_input("Dirección", cfg["address"])
        a, b, c = st.columns(3)
        postal = a.text_input("C.P.", cfg["postal_code"])
        city = b.text_input("Población", cfg["city"])
        email = c.text_input("Email", cfg["email"])
        a, b, c = st.columns(3)
        series = a.text_input("Serie de facturas", cfg["invoice_series"], max_chars=6)
        cc = b.text_input("Prefijo país (WhatsApp)", cfg["default_country_code"])
        gift = c.number_input("Validez tarjetas regalo (meses)", 1, 36, int(cfg["gift_validity_months"] or 12))
        if st.form_submit_button("Guardar", type="primary", use_container_width=True):
            settings.set_many({"business_name": name, "legal_name": legal, "nif": nif, "phone": phone, "address": address,
                               "postal_code": postal, "city": city, "email": email, "invoice_series": series.strip().upper() or "FS",
                               "default_country_code": cc.strip().lstrip("+") or "34", "gift_validity_months": gift})
            st.toast("Datos guardados ✅")
            st.rerun()
    if not cfg["nif"]:
        st.warning("Falta el NIF: es obligatorio para que las facturas sean válidas.")


def _services() -> None:
    rows = catalog.list_services(active_only=False)
    df = pd.DataFrame([{"id": r["id"], "Servicio": r["name"], "Categoría": r["category"], "Duración (min)": r["duration_min"],
                        "Precio (€, IVA incl.)": r["price_cents"] / 100, "IVA %": r["vat_rate"], "Color": r["color"],
                        "Activo": bool(r["active"])} for r in rows])
    st.caption("Los precios son de ejemplo: edítalos aquí. Añade filas al final para crear servicios.")
    edited = st.data_editor(df, num_rows="dynamic", hide_index=True, use_container_width=True, key="svc_editor",
                            column_config={"id": None, "Duración (min)": st.column_config.NumberColumn(min_value=5, step=5),
                                           "Precio (€, IVA incl.)": st.column_config.NumberColumn(min_value=0, format="%.2f"),
                                           "IVA %": st.column_config.SelectboxColumn(options=[0, 4, 10, 21]),
                                           "Color": st.column_config.TextColumn(help="Código hex, p. ej. #c9a24b")})
    if st.button("Guardar servicios", type="primary", use_container_width=True, key="svc_save"):
        try:
            for _, r in edited.iterrows():
                if pd.isna(r["Servicio"]) or not str(r["Servicio"]).strip():
                    continue
                sid = None if pd.isna(r.get("id")) else int(r["id"])
                catalog.save_service(str(r["Servicio"]), str(r["Categoría"] if not pd.isna(r["Categoría"]) else "General"),
                                     int(r["Duración (min)"] if not pd.isna(r["Duración (min)"]) else 60),
                                     to_cents(r["Precio (€, IVA incl.)"] if not pd.isna(r["Precio (€, IVA incl.)"]) else 0),
                                     int(r["IVA %"] if not pd.isna(r["IVA %"]) else 21),
                                     str(r["Color"]) if not pd.isna(r["Color"]) and str(r["Color"]).startswith("#") else "#c9a24b",
                                     "", bool(r["Activo"]) if not pd.isna(r["Activo"]) else True, sid)
        except ValueError as exc:
            st.error(str(exc))
        else:
            st.toast("Servicios guardados ✅")
            st.rerun()
    st.caption("Los servicios no se borran para conservar el histórico: desmarca «Activo» para ocultarlos.")


def _schedule() -> None:
    cfg = settings.all_settings()
    current = {int(x) for x in cfg["open_days"].split(",") if x.strip().isdigit()}
    with st.form("set_schedule"):
        picked = st.multiselect("Días de apertura", [d for d, _ in DAYS], default=[d for d, _ in DAYS if d in current],
                                format_func=dict(DAYS).get)
        a, b, c = st.columns(3)
        o = a.text_input("Apertura", cfg["open_time"])
        cl = b.text_input("Cierre", cfg["close_time"])
        slot = c.selectbox("Franja de la agenda (min)", [10, 15, 30, 60], index=[10, 15, 30, 60].index(int(cfg["slot_minutes"])) if int(cfg["slot_minutes"]) in (10, 15, 30, 60) else 1)
        if st.form_submit_button("Guardar horario", type="primary", use_container_width=True):
            def ok(t: str) -> bool:
                try:
                    h, m = t.split(":")
                    return 0 <= int(h) <= 23 and 0 <= int(m) <= 59
                except ValueError:
                    return False
            if not (ok(o) and ok(cl)) or o >= cl:
                st.error("Usa el formato HH:MM y que la apertura sea anterior al cierre.")
            elif not picked:
                st.error("Elige al menos un día.")
            else:
                settings.set_many({"open_days": ",".join(map(str, picked)), "open_time": o, "close_time": cl, "slot_minutes": slot})
                st.toast("Horario guardado ✅")
                st.rerun()


def _security() -> None:
    if security.deployment_password():
        st.info("El acceso está protegido con el secreto APP_PASSWORD del servidor. Para cambiarlo, edítalo allí.")
        return
    with st.form("set_pw"):
        old = st.text_input("Contraseña actual", type="password")
        p1 = st.text_input("Nueva contraseña", type="password")
        p2 = st.text_input("Repite la nueva", type="password")
        if st.form_submit_button("Cambiar contraseña", type="primary", use_container_width=True):
            err = security.password_strength_error(p1)
            if not security.verify_password(old):
                st.error("La contraseña actual no es correcta.")
            elif err:
                st.error(err)
            elif p1 != p2:
                st.error("Las contraseñas no coinciden.")
            else:
                security.set_password(p1)
                st.success("Contraseña cambiada.")


def _backups() -> None:
    st.warning("Si la app está en Streamlit Community Cloud, el disco se borra al reiniciar. **Descarga una copia con regularidad.**")
    a, b = st.columns(2)
    a.download_button("💾 Copia de seguridad (.db)", backup.backup_db_bytes(), file_name=f"judit_copia_{now():%Y%m%d_%H%M}.db",
                      mime="application/octet-stream", use_container_width=True, type="primary", key="bk_db")
    b.download_button("📦 Todo en CSV (.zip)", backup.export_all_csv_zip(), file_name=f"judit_datos_{now():%Y%m%d}.zip",
                      mime="application/zip", use_container_width=True, key="bk_zip")
    st.markdown("##### Restaurar copia")
    up = st.file_uploader("Archivo .db", type=["db", "sqlite"], key="bk_up")
    if up and st.checkbox("Entiendo que se sustituirán todos los datos actuales", key="bk_ok") and st.button("Restaurar", key="bk_restore"):
        try:
            info = backup.restore_db(up.getvalue())
        except ValueError as exc:
            st.error(str(exc))
        else:
            st.success(f"Restaurado: {info['clientes']} clientas, {info['facturas']} facturas. Copia previa: {info['copia_previa']}")
    st.markdown("##### Importar clientas (CSV)")
    csv = st.file_uploader("CSV o Excel con columnas como nombre, apellidos, teléfono, email", type=["csv", "xlsx"], key="imp_up")
    if csv and st.button("Importar", key="imp_go"):
        try:
            df = pd.read_excel(csv) if csv.name.endswith("xlsx") else pd.read_csv(csv, sep=None, engine="python")
            res = clients.import_clients_df(df)
        except Exception as exc:
            st.error(f"No se pudo importar: {exc}")
        else:
            st.success(f"Importadas: {res.get('created', 0)} · omitidas: {res.get('skipped', 0)}")
            for e in res.get("errors", [])[:5]:
                st.caption(e)
    with st.expander("Tipografías de los documentos"):
        for role, name in fonts_report().items():
            st.write(f"**{role}**: {name}")
        st.caption("Para usar tus propias fuentes o tu logo, mira assets/fonts/README.txt.")


def render() -> None:
    ui.page_header("Ajustes", "Datos del centro, servicios y seguridad")
    t = st.tabs(["Centro", "Servicios", "Horario", "Seguridad", "Copias"])
    for tab, fn in zip(t, (_center, _services, _schedule, _security, _backups)):
        with tab:
            fn()
