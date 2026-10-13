"""Facturación simplificada con registro encadenado SHA-256 (preparado para Veri*Factu).

Garantías de diseño:
* Una factura emitida **no se modifica ni se borra**. Un error se corrige con una factura
  rectificativa (tipo R5) que anula el importe y se encadena como un registro más.
* Cada registro guarda la huella del anterior: si alguien altera un dato a mano, ``verify_chain``
  lo detecta.
* Cobro, descuento de monedero/tarjeta regalo, marcado de la cita y alta de la factura ocurren en
  **una sola transacción**: o se hace todo o no se hace nada.

La huella sigue la estructura del registro de alta de la especificación técnica (campos concatenados
``clave=valor&…`` → SHA-256 en mayúsculas hexadecimales). Es una implementación *preparada*, no una
certificación: el envío a la AEAT y la declaración responsable del software son pasos aparte.
"""
from __future__ import annotations

import hashlib
import sqlite3
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from core.config import CASH_IN_METHODS, INVOICE_RECTIFY, INVOICE_SIMPLE, PAYMENT_LABELS
from core.database import audit, execute, fetch_all, fetch_one, get_conn
from core.utils import fmt_eur, now_with_tz, parse_date, split_vat, today
from services import appointments, giftcards, settings, wallet


# --------------------------------------------------------------------------- huella
def _amount(cents: int) -> str:
    sign = "-" if cents < 0 else ""
    return f"{sign}{abs(cents) // 100}.{abs(cents) % 100:02d}"


def compute_hash(issuer_nif: str, full_number: str, issued_at: str, kind: str, vat_cents: int,
                 total_cents: int, prev_hash: str, generated_at: str) -> str:
    """Huella SHA-256 (hex en mayúsculas) del registro de facturación."""
    d = parse_date(issued_at)
    payload = (
        f"IDEmisorFactura={issuer_nif}&NumSerieFactura={full_number}"
        f"&FechaExpedicionFactura={d.strftime('%d-%m-%Y') if d else issued_at}&TipoFactura={kind}"
        f"&CuotaTotal={_amount(vat_cents)}&ImporteTotal={_amount(total_cents)}"
        f"&Huella={prev_hash or ''}&FechaHoraHusoGenRegistro={generated_at}"
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest().upper()


# --------------------------------------------------------------------------- cálculo de líneas
def _distribute_discount(gross: list[int], discount: int) -> list[int]:
    """Reparte un descuento (en céntimos) proporcionalmente entre líneas; el resto cae en la última."""
    total = sum(gross)
    if discount <= 0 or total <= 0:
        return [0] * len(gross)
    shares = [int((Decimal(discount) * g / total).quantize(Decimal("1"), rounding=ROUND_HALF_UP)) for g in gross]
    shares[-1] += discount - sum(shares)
    return shares


def compute_lines(lines: list[dict], discount_cents: int = 0) -> list[dict]:
    """Valida y calcula base/IVA/total de cada línea (los precios introducidos llevan IVA incluido)."""
    if not lines:
        raise ValueError("Añade al menos un concepto.")
    gross = []
    for ln in lines:
        qty = float(ln.get("qty", 1) or 0)
        if qty <= 0:
            raise ValueError("La cantidad debe ser mayor que 0.")
        if int(ln.get("unit_cents", 0)) < 0:
            raise ValueError("El precio no puede ser negativo.")
        gross.append(int((Decimal(str(qty)) * int(ln["unit_cents"])).quantize(Decimal("1"), rounding=ROUND_HALF_UP)))
    if discount_cents < 0 or discount_cents > sum(gross):
        raise ValueError("El descuento no es válido.")
    shares = _distribute_discount(gross, discount_cents)
    out = []
    for ln, g, d in zip(lines, gross, shares):
        net = g - d
        rate = int(ln.get("vat_rate", 21))
        base, vat = split_vat(net, rate)
        desc = str(ln.get("description", "")).strip() or "Servicio"
        if d:
            desc += f" (dto. −{fmt_eur(d)})"
        out.append({
            "description": desc, "qty": float(ln.get("qty", 1)), "unit_cents": int(ln["unit_cents"]),
            "vat_rate": rate, "base_cents": base, "vat_cents": vat, "total_cents": net,
            "service_id": ln.get("service_id"),
        })
    return out


def _next_number(conn: sqlite3.Connection, series: str) -> int:
    return fetch_one("SELECT COALESCE(MAX(number), 0) + 1 AS n FROM invoices WHERE series = ?", (series,), conn)["n"]


def _insert_record(conn: sqlite3.Connection, *, series: str, kind: str, lines: list[dict], client: dict | None,
                   client_nif: str, appointment_id: int | None, rectifies_id: int | None = None,
                   reason: str = "", issued_on: date | None = None) -> int:
    cfg = settings.all_settings()
    number = _next_number(conn, series)
    full_number = f"{series}-{number:06d}"
    issued = (issued_on or today()).isoformat()
    generated_at = now_with_tz().isoformat(timespec="seconds")
    prev = fetch_one("SELECT hash FROM invoices ORDER BY id DESC LIMIT 1", (), conn)
    prev_hash = prev["hash"] if prev else ""
    base = sum(ln["base_cents"] for ln in lines)
    vat = sum(ln["vat_cents"] for ln in lines)
    total = sum(ln["total_cents"] for ln in lines)
    issuer_nif = cfg.get("nif", "").strip().upper()
    digest = compute_hash(issuer_nif, full_number, issued, kind, vat, total, prev_hash, generated_at)
    client_name = ""
    if client:
        client_name = f"{client.get('first_name', '')} {client.get('last_name', '')}".strip()
    inv_id = execute(
        "INSERT INTO invoices(series, number, full_number, kind, rectifies_id, rectify_reason, issued_at, generated_at, client_id,"
        " client_name, client_nif, base_cents, vat_cents, total_cents, prev_hash, hash, issuer_nif, status, appointment_id)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (series, number, full_number, kind, rectifies_id, reason, issued, generated_at, client["id"] if client else None,
         client_name, client_nif.strip().upper(), base, vat, total, prev_hash, digest, issuer_nif, "emitida", appointment_id), conn,
    )
    for ln in lines:
        execute(
            "INSERT INTO invoice_lines(invoice_id, description, qty, unit_cents, vat_rate, base_cents, vat_cents, total_cents, service_id)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            (inv_id, ln["description"], ln["qty"], ln["unit_cents"], ln["vat_rate"], ln["base_cents"], ln["vat_cents"],
             ln["total_cents"], ln.get("service_id")), conn,
        )
    return inv_id


# --------------------------------------------------------------------------- emisión
def create_invoice(lines: list[dict], payments: list[dict], client_id: int | None = None,
                   appointment_id: int | None = None, discount_cents: int = 0, client_nif: str = "") -> dict:
    """Emite una factura simplificada y registra los cobros en una única transacción.

    ``payments``: lista de ``{"method": str, "amount_cents": int, "gift_code": str (solo tarjeta regalo)}``.
    La suma de los pagos debe coincidir exactamente con el total.
    """
    computed = compute_lines(lines, discount_cents)
    total = sum(ln["total_cents"] for ln in computed)
    if total <= 0:
        raise ValueError("El importe total debe ser mayor que 0.")
    clean = [p for p in payments if int(p.get("amount_cents", 0)) > 0]
    if sum(int(p["amount_cents"]) for p in clean) != total:
        raise ValueError(f"Los pagos ({fmt_eur(sum(int(p['amount_cents']) for p in clean))}) no coinciden con el total ({fmt_eur(total)}).")
    for p in clean:
        if p["method"] not in PAYMENT_LABELS:
            raise ValueError("Método de pago no válido.")
    series = settings.get("invoice_series", "FS").strip().upper() or "FS"

    with get_conn() as conn:
        conn.execute("BEGIN IMMEDIATE")  # bloquea escritores: numeración y cadena sin carreras
        client = fetch_one("SELECT * FROM clients WHERE id = ?", (client_id,), conn) if client_id else None
        if appointment_id:
            appt = fetch_one("SELECT invoice_id FROM appointments WHERE id = ?", (appointment_id,), conn)
            if appt and appt["invoice_id"]:
                raise ValueError("Esta cita ya está cobrada.")
        inv_id = _insert_record(conn, series=series, kind=INVOICE_SIMPLE, lines=computed, client=client,
                                client_nif=client_nif, appointment_id=appointment_id)
        full_number = fetch_one("SELECT full_number FROM invoices WHERE id = ?", (inv_id,), conn)["full_number"]
        ts = now_with_tz().replace(tzinfo=None).isoformat(timespec="seconds")
        for p in clean:
            method, amount = p["method"], int(p["amount_cents"])
            if method == "monedero":
                wallet.spend_tx(conn, client_id, amount, f"Pago factura {full_number}", inv_id)
            elif method == "tarjeta_regalo":
                giftcards.redeem_tx(conn, p.get("gift_code", ""), amount, f"Pago factura {full_number}", inv_id)
            execute(
                "INSERT INTO payments(ts, kind, ref_id, invoice_id, method, amount_cents, client_id, concept) VALUES (?,?,?,?,?,?,?,?)",
                (ts, "invoice", inv_id, inv_id, method, amount, client_id, f"Factura {full_number}"), conn,
            )
        if appointment_id:
            appointments.mark_paid_tx(conn, appointment_id, inv_id)
        audit("invoice_create", f"{full_number} total={total}", conn)
    return get_invoice(inv_id)  # type: ignore[return-value]


def rectify_invoice(invoice_id: int, reason: str, refund_method: str | None = None) -> dict:
    """Anula una factura creando una rectificativa por el importe íntegro y devolviendo los cobros."""
    if not (reason or "").strip():
        raise ValueError("Indica el motivo de la rectificación.")
    with get_conn() as conn:
        conn.execute("BEGIN IMMEDIATE")
        orig = fetch_one("SELECT * FROM invoices WHERE id = ?", (invoice_id,), conn)
        if not orig:
            raise ValueError("Factura no encontrada.")
        if orig["kind"] != INVOICE_SIMPLE or orig["status"] != "emitida":
            raise ValueError("Solo se pueden rectificar facturas emitidas que no estén ya rectificadas.")
        lines = fetch_all("SELECT * FROM invoice_lines WHERE invoice_id = ?", (invoice_id,), conn)
        negated = [{
            "description": ln["description"], "qty": ln["qty"], "unit_cents": ln["unit_cents"], "vat_rate": ln["vat_rate"],
            "base_cents": -ln["base_cents"], "vat_cents": -ln["vat_cents"], "total_cents": -ln["total_cents"],
            "service_id": ln["service_id"],
        } for ln in lines]
        series = (settings.get("invoice_series", "FS").strip().upper() or "FS") + "R"
        client = fetch_one("SELECT * FROM clients WHERE id = ?", (orig["client_id"],), conn) if orig["client_id"] else None
        rid = _insert_record(conn, series=series, kind=INVOICE_RECTIFY, lines=negated, client=client,
                             client_nif=orig["client_nif"], appointment_id=orig["appointment_id"],
                             rectifies_id=invoice_id, reason=reason.strip())
        rect_number = fetch_one("SELECT full_number FROM invoices WHERE id = ?", (rid,), conn)["full_number"]
        ts = now_with_tz().replace(tzinfo=None).isoformat(timespec="seconds")
        for p in fetch_all("SELECT * FROM payments WHERE invoice_id = ? AND kind = 'invoice'", (invoice_id,), conn):
            method = p["method"]
            if method == "monedero" and orig["client_id"]:
                wallet.refund_tx(conn, orig["client_id"], p["amount_cents"], f"Devolución {rect_number}", rid)
            elif method == "tarjeta_regalo":
                for mv in fetch_all("SELECT * FROM gift_card_movements WHERE invoice_id = ? AND amount_cents < 0", (invoice_id,), conn):
                    giftcards.restore_tx(conn, mv["gift_card_id"], -mv["amount_cents"], f"Devolución {rect_number}", rid)
            elif refund_method in CASH_IN_METHODS:
                method = refund_method
            execute(
                "INSERT INTO payments(ts, kind, ref_id, invoice_id, method, amount_cents, client_id, concept) VALUES (?,?,?,?,?,?,?,?)",
                (ts, "rectify", rid, rid, method, -p["amount_cents"], orig["client_id"], f"Rectificativa {rect_number}"), conn,
            )
        execute("UPDATE invoices SET status = 'rectificada' WHERE id = ?", (invoice_id,), conn)
        appointments.unmark_paid_tx(conn, invoice_id)
        audit("invoice_rectify", f"{orig['full_number']} → {rect_number}: {reason}", conn)
    return get_invoice(rid)  # type: ignore[return-value]


# --------------------------------------------------------------------------- consulta
def get_invoice(invoice_id: int) -> dict | None:
    inv = fetch_one("SELECT * FROM invoices WHERE id = ?", (invoice_id,))
    if not inv:
        return None
    inv["lines"] = fetch_all("SELECT * FROM invoice_lines WHERE invoice_id = ? ORDER BY id", (invoice_id,))
    inv["payments"] = fetch_all("SELECT * FROM payments WHERE invoice_id = ? ORDER BY id", (invoice_id,))
    return inv


def list_invoices(date_from: date | None = None, date_to: date | None = None, text: str = "", client_id: int | None = None) -> list[dict]:
    sql, params = "SELECT * FROM invoices WHERE 1=1", []
    if date_from:
        sql += " AND issued_at >= ?"
        params.append(date_from.isoformat())
    if date_to:
        sql += " AND issued_at <= ?"
        params.append(date_to.isoformat())
    if client_id:
        sql += " AND client_id = ?"
        params.append(client_id)
    rows = fetch_all(sql + " ORDER BY id DESC", params)
    needle = (text or "").strip().lower()
    if needle:
        rows = [r for r in rows if needle in f"{r['full_number']} {r['client_name']}".lower()]
    return rows


def payment_summary(invoice: dict) -> str:
    return " + ".join(f"{PAYMENT_LABELS.get(p['method'], p['method'])} {fmt_eur(abs(p['amount_cents']))}" for p in invoice.get("payments", []))


def receipt_text(invoice: dict, client_first_name: str = "") -> str:
    cfg = settings.all_settings()
    from core.utils import render_template

    return render_template(
        cfg["tpl_receipt"], nombre=client_first_name or "", centro=cfg["business_name"],
        numero=invoice["full_number"], importe=fmt_eur(invoice["total_cents"]),
    ).replace("  ", " ")


# --------------------------------------------------------------------------- integridad
def verify_chain() -> dict:
    """Recorre todos los registros y comprueba huellas, encadenado, importes y numeración."""
    errors: list[str] = []
    prev_hash = ""
    last_number: dict[str, int] = {}
    rows = fetch_all("SELECT * FROM invoices ORDER BY id")
    for r in rows:
        if r["prev_hash"] != prev_hash:
            errors.append(f"{r['full_number']}: el enlace con el registro anterior no coincide.")
        expected = compute_hash(r["issuer_nif"], r["full_number"], r["issued_at"], r["kind"], r["vat_cents"],
                                r["total_cents"], r["prev_hash"], r["generated_at"])
        if expected != r["hash"]:
            errors.append(f"{r['full_number']}: la huella no coincide (datos alterados).")
        sums = fetch_one(
            "SELECT COALESCE(SUM(base_cents),0) b, COALESCE(SUM(vat_cents),0) v, COALESCE(SUM(total_cents),0) t "
            "FROM invoice_lines WHERE invoice_id = ?", (r["id"],),
        )
        if (sums["b"], sums["v"], sums["t"]) != (r["base_cents"], r["vat_cents"], r["total_cents"]):
            errors.append(f"{r['full_number']}: las líneas no suman el total de la factura.")
        if r["base_cents"] + r["vat_cents"] != r["total_cents"]:
            errors.append(f"{r['full_number']}: base + IVA no es igual al total.")
        expected_number = last_number.get(r["series"], 0) + 1
        if r["number"] != expected_number:
            errors.append(f"Serie {r['series']}: falta o salta la numeración (esperado {expected_number}, hay {r['number']}).")
        last_number[r["series"]] = r["number"]
        prev_hash = r["hash"]
    return {"ok": not errors, "checked": len(rows), "errors": errors, "last_hash": prev_hash}
