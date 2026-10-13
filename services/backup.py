"""Exportaciones para la gestoría y copias de seguridad (descarga y restauración de la base de datos).

AVISO: en Streamlit Community Cloud el disco es efímero y se borra al reiniciar la app. Descarga una
copia de seguridad con regularidad (o usa un servidor/volumen persistente).
"""
from __future__ import annotations

import io
import sqlite3
import tempfile
import zipfile
from datetime import date
from pathlib import Path

import pandas as pd

from core.config import db_path
from core.database import fetch_all, init_db
from core.utils import fmt_eur, now, quarter_bounds
from services import taxes
from services.expenses import METHODS

SENSITIVE_BLOB_TABLES = {"consents": ("signature_png",)}


# --------------------------------------------------------------------------- CSV para la gestoría
def _csv(df: pd.DataFrame) -> bytes:
    """CSV listo para Excel en España: separador ';', coma decimal y UTF-8 con BOM."""
    return df.to_csv(index=False, sep=";", decimal=",", encoding="utf-8-sig").encode("utf-8-sig")


csv_bytes = _csv  # alias público


def invoices_register_df(date_from: date, date_to: date) -> pd.DataFrame:
    rows = fetch_all(
        "SELECT full_number, kind, issued_at, client_name, base_cents, vat_cents, total_cents, status, hash "
        "FROM invoices WHERE issued_at >= ? AND issued_at <= ? ORDER BY id", (date_from.isoformat(), date_to.isoformat()),
    )
    return pd.DataFrame([{
        "Nº factura": r["full_number"], "Tipo": r["kind"], "Fecha": r["issued_at"], "Cliente": r["client_name"],
        "Base imponible": r["base_cents"] / 100, "Cuota IVA": r["vat_cents"] / 100, "Total": r["total_cents"] / 100,
        "Estado": r["status"], "Huella SHA-256": r["hash"],
    } for r in rows])


def vat_breakdown_df(date_from: date, date_to: date) -> pd.DataFrame:
    rows = fetch_all(
        "SELECT i.full_number, i.issued_at, l.vat_rate, l.base_cents, l.vat_cents FROM invoice_lines l "
        "JOIN invoices i ON i.id = l.invoice_id WHERE i.issued_at >= ? AND i.issued_at <= ? ORDER BY i.id",
        (date_from.isoformat(), date_to.isoformat()),
    )
    return pd.DataFrame([{"Nº factura": r["full_number"], "Fecha": r["issued_at"], "Tipo IVA %": r["vat_rate"],
                          "Base": r["base_cents"] / 100, "Cuota": r["vat_cents"] / 100} for r in rows])


def expenses_register_df(date_from: date, date_to: date) -> pd.DataFrame:
    rows = fetch_all("SELECT * FROM expenses WHERE date >= ? AND date <= ? ORDER BY date", (date_from.isoformat(), date_to.isoformat()))
    return pd.DataFrame([{
        "Fecha": r["date"], "Concepto": r["concept"], "Proveedor": r["supplier"], "Nº factura proveedor": r["invoice_ref"],
        "Categoría": r["category"], "Base": r["base_cents"] / 100, "Tipo IVA %": r["vat_rate"], "Cuota IVA": r["vat_cents"] / 100,
        "Total": r["total_cents"] / 100, "IVA deducible": "Sí" if r["vat_deductible"] else "No",
        "Pago": METHODS.get(r["method"], r["method"]),
    } for r in rows])


def quarter_summary_text(year: int, quarter: int) -> str:
    iva, irpf = taxes.iva_quarter(year, quarter), taxes.irpf_130(year, quarter)
    lines = [
        f"RESUMEN TRIMESTRAL {quarter}T {year} (estimación orientativa; revisar con la gestoría)",
        f"Generado: {now():%d/%m/%Y %H:%M}", "",
        "MODELO 303 — IVA",
        f"  Ventas (base imponible): {fmt_eur(iva['sales_base_cents'])}",
    ]
    for r in iva["accrued"]:
        lines.append(f"  IVA devengado {r['rate']} %: base {fmt_eur(r['base'])} · cuota {fmt_eur(r['vat'])}")
    lines += [f"  Total IVA devengado: {fmt_eur(iva['accrued_total_cents'])}",
              f"  Total IVA soportado deducible: {fmt_eur(iva['input_total_cents'])}",
              f"  Resultado: {fmt_eur(iva['result_cents'])} ({'a ingresar' if iva['result_cents'] > 0 else 'a compensar / sin ingreso'})", "",
              "MODELO 130 — IRPF (pago fraccionado, acumulado del año)",
              f"  Ingresos acumulados: {fmt_eur(irpf['income_cents'])}",
              f"  Gastos deducibles acumulados: {fmt_eur(irpf['expenses_cents'])}",
              f"  Rendimiento neto: {fmt_eur(irpf['net_cents'])}",
              f"  20 % del rendimiento: {fmt_eur(irpf['gross_payment_cents'])}",
              f"  Pagos de trimestres anteriores: {fmt_eur(irpf['previous_payments_cents'])}",
              f"  Resultado a ingresar: {fmt_eur(irpf['to_pay_cents'])}"]
    return "\n".join(lines)


def quarter_pack_zip(year: int, quarter: int) -> bytes:
    """ZIP con el libro de facturas, desglose de IVA, libro de gastos y el resumen del trimestre."""
    start, end = quarter_bounds(year, quarter)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(f"facturas_emitidas_{year}T{quarter}.csv", _csv(invoices_register_df(start, end)))
        z.writestr(f"desglose_iva_{year}T{quarter}.csv", _csv(vat_breakdown_df(start, end)))
        z.writestr(f"gastos_{year}T{quarter}.csv", _csv(expenses_register_df(start, end)))
        z.writestr(f"resumen_{year}T{quarter}.txt", quarter_summary_text(year, quarter))
    return buf.getvalue()


# --------------------------------------------------------------------------- copia de seguridad
def backup_db_bytes() -> bytes:
    """Copia consistente de la base de datos (usa la API de copia de SQLite, válida con la app en uso)."""
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "backup.db"
        src = sqlite3.connect(str(db_path()))
        dst = sqlite3.connect(str(target))
        try:
            src.backup(dst)
        finally:
            dst.close()
            src.close()
        return target.read_bytes()


def export_all_csv_zip() -> bytes:
    """Todas las tablas en CSV (sin las firmas binarias) para portabilidad y auditoría."""
    tables = [r["name"] for r in fetch_all("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name in tables:
            df = pd.DataFrame(fetch_all(f"SELECT * FROM {name}"))
            for col in SENSITIVE_BLOB_TABLES.get(name, ()):
                if col in df.columns:
                    df = df.drop(columns=[col])
            z.writestr(f"{name}.csv", _csv(df))
    return buf.getvalue()


def restore_db(data: bytes) -> dict:
    """Restaura una copia de seguridad. Antes guarda una copia de seguridad de lo que hubiera."""
    if not data.startswith(b"SQLite format 3\x00"):
        raise ValueError("El archivo no es una base de datos SQLite válida.")
    with tempfile.TemporaryDirectory() as tmp:
        incoming = Path(tmp) / "incoming.db"
        incoming.write_bytes(data)
        probe = sqlite3.connect(str(incoming))
        try:
            tables = {r[0] for r in probe.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if not {"clients", "appointments", "invoices"} <= tables:
                raise ValueError("La copia no parece de esta aplicación (faltan tablas básicas).")
            if probe.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ValueError("La copia está dañada (falló la comprobación de integridad).")
            safety = db_path().with_name(f"antes_de_restaurar_{now():%Y%m%d_%H%M%S}.db")
            current = sqlite3.connect(str(db_path()))
            try:
                with sqlite3.connect(str(safety)) as keep:
                    current.backup(keep)
                probe.backup(current)  # sustituye el contenido manteniendo el archivo
            finally:
                current.close()
            clients = probe.execute("SELECT COUNT(*) FROM clients").fetchone()[0]
            invoices = probe.execute("SELECT COUNT(*) FROM invoices").fetchone()[0]
        finally:
            probe.close()
    init_db()  # aplica migraciones si la copia era de una versión anterior
    return {"clientes": clients, "facturas": invoices, "copia_previa": safety.name}
