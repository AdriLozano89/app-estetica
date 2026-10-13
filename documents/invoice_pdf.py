"""Factura simplificada / rectificativa en PDF (tamaño A5, generada con Pillow, sin dependencias extra)."""
from __future__ import annotations

import io

from PIL import Image, ImageDraw

from core.config import INVOICE_RECTIFY, PAYMENT_LABELS
from core.utils import fmt_date, fmt_eur
from documents import brand
from documents.fonts import get_font

DPI = 200
W, MIN_H = 1165, 1654  # A5 a 200 ppp
PAPER, INK, MUTED = (253, 251, 246), (26, 24, 34), (125, 118, 104)
GOLD_INK = (150, 119, 24)  # dorado oscuro legible sobre blanco
RULE = (222, 212, 180)
MARGIN = 80


def _qty(q: float) -> str:
    return str(int(q)) if float(q).is_integer() else f"{q:g}".replace(".", ",")


def render_invoice_pdf(invoice: dict, business: dict, rectifies_number: str = "") -> bytes:
    """Genera el PDF de una factura. ``invoice`` viene de ``billing.get_invoice`` y ``business`` de ``settings.all_settings``."""
    lines = invoice.get("lines", [])
    height = max(MIN_H, 1150 + 62 * len(lines) + 40 * len(invoice.get("payments", [])))
    img = Image.new("RGB", (W, height), PAPER)
    d = ImageDraw.Draw(img)
    is_rect = invoice["kind"] == INVOICE_RECTIFY

    # --- cabecera
    script = get_font("script", 92)
    d.text((MARGIN, 64), "Judit Domingo", font=script, fill=GOLD_INK)
    brand.draw_spaced(d, MARGIN + 4, 176, "CENTRE D'ESTÈTICA", get_font("sans_medium", 20), MUTED, tracking=8)
    title = "FACTURA RECTIFICATIVA" if is_rect else "FACTURA SIMPLIFICADA"
    tf = get_font("sans_bold", 28)
    d.text((W - MARGIN - tf.getlength(title), 74), title, font=tf, fill=INK)
    nf = get_font("serif_bold", 44)
    d.text((W - MARGIN - nf.getlength(invoice["full_number"]), 116), invoice["full_number"], font=nf, fill=GOLD_INK)
    d.line([(MARGIN, 230), (W - MARGIN, 230)], fill=GOLD_INK, width=3)

    # --- emisor y datos
    small, small_b = get_font("sans", 21), get_font("sans_medium", 21)
    y = 256
    issuer = [business.get("legal_name") or business.get("business_name", "")]
    if business.get("nif"):
        issuer.append(f"NIF: {business['nif']}")
    addr = " · ".join(x for x in (business.get("address"), business.get("postal_code"), business.get("city")) if x)
    if addr:
        issuer.append(addr)
    contact = " · ".join(x for x in (business.get("phone"), business.get("email")) if x)
    if contact:
        issuer.append(contact)
    for i, text in enumerate(issuer):
        d.text((MARGIN, y), text, font=small_b if i == 0 else small, fill=INK if i == 0 else MUTED)
        y += 30
    right_y = 256
    meta = [("Fecha de expedición", fmt_date(invoice["issued_at"]))]
    if invoice.get("client_name"):
        meta.append(("Cliente", invoice["client_name"]))
    if invoice.get("client_nif"):
        meta.append(("NIF cliente", invoice["client_nif"]))
    for label, value in meta:
        d.text((W - MARGIN - small_b.getlength(value), right_y), value, font=small_b, fill=INK)
        d.text((W - MARGIN - small_b.getlength(value) - small.getlength(label + "  "), right_y), label + "  ", font=small, fill=MUTED)
        right_y += 30
    y = max(y, right_y) + 14
    if is_rect:
        note = f"Rectifica la factura {rectifies_number}. Motivo: {invoice.get('rectify_reason', '')}"
        for line in brand.wrap_text(note, small, W - 2 * MARGIN):
            d.text((MARGIN, y), line, font=small, fill=INK)
            y += 28
        y += 6

    # --- tabla de conceptos
    y += 18
    cols = {"desc": MARGIN, "qty": 640, "unit": 790, "vat": 905, "total": W - MARGIN}
    head = get_font("sans_medium", 19)
    d.rectangle([MARGIN - 10, y - 8, W - MARGIN + 10, y + 36], fill=(244, 238, 220))
    d.text((cols["desc"], y), "CONCEPTO", font=head, fill=MUTED)
    for key, label in (("qty", "CANT."), ("unit", "PRECIO"), ("vat", "IVA"), ("total", "IMPORTE")):
        d.text((cols[key] - head.getlength(label), y), label, font=head, fill=MUTED)
    y += 56
    row_f = get_font("sans", 23)
    for ln in lines:
        desc_lines = brand.wrap_text(ln["description"], row_f, 520)
        d.text((cols["desc"], y), desc_lines[0], font=row_f, fill=INK)
        for key, text in (("qty", _qty(ln["qty"])), ("unit", fmt_eur(ln["unit_cents"])),
                          ("vat", f"{ln['vat_rate']} %"), ("total", fmt_eur(ln["total_cents"]))):
            d.text((cols[key] - row_f.getlength(text), y), text, font=row_f, fill=INK)
        for extra in desc_lines[1:3]:
            y += 28
            d.text((cols["desc"], y), extra, font=row_f, fill=MUTED)
        y += 48
        d.line([(MARGIN, y - 10), (W - MARGIN, y - 10)], fill=RULE, width=1)

    # --- totales (desglose por tipo de IVA)
    y += 24
    by_rate: dict[int, list[int]] = {}
    for ln in lines:
        acc = by_rate.setdefault(ln["vat_rate"], [0, 0])
        acc[0] += ln["base_cents"]
        acc[1] += ln["vat_cents"]
    label_x, value_x = 640, W - MARGIN
    for rate in sorted(by_rate):
        base, vat = by_rate[rate]
        for label, value in ((f"Base imponible ({rate} %)", base), (f"IVA {rate} %", vat)):
            d.text((label_x, y), label, font=small, fill=MUTED)
            d.text((value_x - small.getlength(fmt_eur(value)), y), fmt_eur(value), font=small, fill=INK)
            y += 32
    y += 8
    d.line([(label_x, y), (value_x, y)], fill=GOLD_INK, width=2)
    y += 14
    d.text((label_x, y + 10), "TOTAL", font=get_font("sans_bold", 28), fill=INK)
    tot = fmt_eur(invoice["total_cents"])
    big = get_font("serif_bold", 54)
    d.text((value_x - big.getlength(tot), y), tot, font=big, fill=GOLD_INK)
    y += 100

    # --- cobro
    pays = invoice.get("payments", [])
    if pays:
        d.text((MARGIN, y), "FORMA DE PAGO" if not is_rect else "DEVOLUCIÓN", font=head, fill=MUTED)
        y += 32
        for p in pays:
            label = PAYMENT_LABELS.get(p["method"], p["method"])
            d.text((MARGIN, y), f"{label}: {fmt_eur(abs(p['amount_cents']))}", font=small, fill=INK)
            y += 30

    # --- pie: huella de encadenado
    fy = height - 190
    d.line([(MARGIN, fy), (W - MARGIN, fy)], fill=RULE, width=1)
    tiny = get_font("sans", 17)
    d.text((MARGIN, fy + 16), "Registro de facturación encadenado (SHA-256) · preparado para Veri*Factu", font=tiny, fill=MUTED)
    h = invoice["hash"]
    d.text((MARGIN, fy + 44), "Huella: " + h[:32], font=tiny, fill=MUTED)
    d.text((MARGIN + tiny.getlength("Huella: "), fy + 68), h[32:], font=tiny, fill=MUTED)
    d.text((MARGIN, fy + 112), f"Generada el {invoice['generated_at'].replace('T', ' ')}", font=tiny, fill=MUTED)
    if not business.get("nif"):
        d.text((MARGIN, fy + 136), "⚠ Falta el NIF del emisor en Ajustes: completa los datos fiscales antes de emitir facturas reales.", font=tiny, fill=(170, 60, 60))

    buf = io.BytesIO()
    img.save(buf, "PDF", resolution=DPI)
    return buf.getvalue()
