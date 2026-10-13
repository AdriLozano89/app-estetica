"""Generador visual de tarjetas regalo (PNG) con el logotipo de la casa como marca de agua."""
from __future__ import annotations

import io

from PIL import Image, ImageDraw, ImageOps

from core.utils import fmt_date, fmt_eur
from documents import brand
from documents.fonts import get_font

WIDTH, HEIGHT = 1800, 1100


def _background() -> Image.Image:
    img = Image.new("RGB", (WIDTH, HEIGHT), brand.BG)
    glow = ImageOps.invert(Image.radial_gradient("L")).resize((int(WIDTH * 1.1), int(HEIGHT * 1.5)), Image.LANCZOS)
    glow = glow.point(lambda v: int(v * 0.55))
    layer = Image.new("RGB", glow.size, brand.SURFACE_2)
    img.paste(layer, (int(WIDTH * 0.32), -int(HEIGHT * 0.25)), glow)
    return img


def _frame(img: Image.Image) -> None:
    d = ImageDraw.Draw(img)
    d.rectangle([34, 34, WIDTH - 35, HEIGHT - 35], outline=brand.GOLD_DEEP, width=3)
    d.rectangle([58, 58, WIDTH - 59, HEIGHT - 59], outline=(*brand.GOLD_DEEP,), width=1)
    for cx, cy in ((58, 58), (WIDTH - 59, 58), (58, HEIGHT - 59), (WIDTH - 59, HEIGHT - 59)):  # rombos en las esquinas
        r = 16
        d.polygon([(cx, cy - r), (cx + r, cy), (cx, cy + r), (cx - r, cy)], fill=brand.BG, outline=brand.GOLD, width=2)


def _amount_text(cents: int) -> str:
    return fmt_eur(cents).replace(",00 €", " €")


def render_giftcard(card: dict, business_name: str = "Judit Domingo", phone: str = "", address: str = "") -> bytes:
    """Devuelve el PNG de la tarjeta. ``card`` es una fila de ``gift_cards``."""
    img = _background()

    mark = brand.logo_mark(980, color=brand.GOLD, opacity=0.10, line=0.008)  # marca de agua grande a la derecha
    img.paste(mark, (WIDTH - 1040, (HEIGHT - 980) // 2), mark)
    _frame(img)
    d = ImageDraw.Draw(img)

    left, col_w = 130, 1080
    # Marca
    script = brand.fit_font("script", "Judit Domingo", col_w, 150, 90)
    box = brand.draw_gold_text(img, (left, 84), "Judit Domingo", script)
    tag_font = get_font("sans_medium", 28)
    brand.draw_spaced(d, left + 6, box[3] + 14, "CENTRE D'ESTÈTICA", tag_font, brand.GOLD, tracking=11)

    # Título
    y = box[3] + 80
    brand.draw_spaced(d, left, y, "TARJETA REGALO", get_font("serif_bold", 44), brand.GOLD_SOFT, tracking=14)

    # Importe
    amount = _amount_text(card["initial_cents"])
    amount_font = brand.fit_font("serif_bold", amount, col_w, 170, 100)
    abox = brand.draw_gold_text(img, (left - 6, y + 62), amount, amount_font)

    # Destinatario, tratamiento y mensaje
    cursor = abox[3] + 30
    limit_y = HEIGHT - 205 - 24  # el contenido no puede invadir el pie
    body_font = get_font("sans", 36)
    if card.get("recipient_name"):
        d.text((left, cursor), "PARA", font=get_font("sans_medium", 24), fill=brand.MUTED)
        d.text((left + 90, cursor - 6), card["recipient_name"], font=get_font("serif_bold", 46), fill=brand.TEXT)
        cursor += 58
    if card.get("for_service"):
        d.text((left, cursor), f"Válida para: {card['for_service']}", font=body_font, fill=brand.TEXT)
        cursor += 56
    if card.get("message"):
        msg_font = get_font("serif_italic", 36)
        lines = brand.wrap_text(f"“{card['message'].strip()}”", msg_font, col_w)
        room = max((limit_y - 34 - cursor) // 46, 0)  # líneas que caben sin tocar el pie
        if len(lines) > room > 0:  # no cabe entero: se recorta con puntos suspensivos
            lines = lines[:room]
            lines[-1] = lines[-1].rstrip("”").rstrip(" ,.;") + "…”"
        for line in lines[:room or 0]:
            d.text((left, cursor), line, font=msg_font, fill=brand.GOLD_SOFT)
            cursor += 46
        if card.get("buyer_name") and cursor + 34 <= limit_y:
            d.text((left, cursor + 2), f"— {card['buyer_name']}", font=get_font("sans", 26), fill=brand.MUTED)

    # Pie: código y validez
    foot_y = HEIGHT - 205
    d.line([(left, foot_y), (WIDTH - 130, foot_y)], fill=brand.GOLD_DEEP, width=1)
    d.text((left, foot_y + 24), "CÓDIGO", font=get_font("sans_medium", 22), fill=brand.MUTED)
    brand.draw_spaced(d, left, foot_y + 54, card["code"], get_font("sans_bold", 52), brand.GOLD, tracking=8)
    valid = f"Válida hasta el {fmt_date(card['expires_at'])}"
    right_font = get_font("sans", 30)
    d.text((WIDTH - 130 - right_font.getlength(valid), foot_y + 40), valid, font=right_font, fill=brand.TEXT)
    contact = " · ".join(x for x in (business_name, address, phone) if x)
    small = get_font("sans", 24)
    d.text((WIDTH - 130 - small.getlength(contact), foot_y + 92), contact, font=small, fill=brand.MUTED)

    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=True)
    return buf.getvalue()
