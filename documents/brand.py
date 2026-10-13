"""Elementos gráficos de marca para las imágenes: logotipo vectorial propio, degradado dorado, texto espaciado."""
from __future__ import annotations

import math

from PIL import Image, ImageDraw, ImageFont

from core.config import ASSETS_DIR, Colors


def hex_to_rgb(value: str) -> tuple[int, int, int]:
    v = value.lstrip("#")
    return tuple(int(v[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


GOLD = hex_to_rgb(Colors.GOLD)
GOLD_DEEP = hex_to_rgb(Colors.GOLD_DEEP)
GOLD_SOFT = hex_to_rgb(Colors.GOLD_SOFT)
BG = hex_to_rgb(Colors.BG)
SURFACE_2 = hex_to_rgb(Colors.SURFACE_2)
TEXT = hex_to_rgb(Colors.TEXT)
MUTED = hex_to_rgb(Colors.MUTED)


def logo_mark(size: int, color: tuple[int, int, int] = GOLD, opacity: float = 1.0, line: float = 0.012) -> Image.Image:
    """Marca de la casa: estrella de ocho puntas con flor central, dibujada a 4× para que quede nítida.

    Si existe ``assets/logo.png`` (logotipo real), se usa ese archivo en su lugar.
    """
    custom = ASSETS_DIR / "logo.png"
    if custom.exists():
        try:
            img = Image.open(custom).convert("RGBA")
            img.thumbnail((size, size), Image.LANCZOS)
            canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
            canvas.paste(img, ((size - img.width) // 2, (size - img.height) // 2), img)
            alpha = canvas.getchannel("A").point(lambda a: int(a * opacity))
            canvas.putalpha(alpha)
            return canvas
        except OSError:
            pass
    scale = 4
    s = size * scale
    layer = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    cx = cy = s / 2
    w = max(2, int(s * line))
    rgba = (*color, int(255 * opacity))

    def star(radius: float, width: int) -> None:
        for offset in (0, 45):  # dos cuadrados girados = estrella de 8 puntas
            pts = [(cx + radius * math.cos(math.radians(offset + 90 * k - 90)),
                    cy + radius * math.sin(math.radians(offset + 90 * k - 90))) for k in range(4)]
            d.line(pts + [pts[0]], fill=rgba, width=width, joint="curve")

    star(s * 0.47, w)
    star(s * 0.39, max(1, int(w * 0.6)))
    petal_r = s * 0.15
    for k in range(8):  # flor central
        ang = math.radians(45 * k)
        px, py = cx + petal_r * math.cos(ang), cy + petal_r * math.sin(ang)
        d.ellipse([px - petal_r, py - petal_r, px + petal_r, py + petal_r], outline=rgba, width=max(1, int(w * 0.7)))
    d.ellipse([cx - s * 0.035, cy - s * 0.035, cx + s * 0.035, cy + s * 0.035], fill=rgba)
    return layer.resize((size, size), Image.LANCZOS)


def gold_gradient(width: int, height: int) -> Image.Image:
    """Degradado metálico vertical: claro arriba, dorado en el centro y profundo abajo."""
    img = Image.new("RGB", (max(width, 1), max(height, 1)))
    d = ImageDraw.Draw(img)
    stops = [(0.0, GOLD_SOFT), (0.45, GOLD), (1.0, GOLD_DEEP)]
    for y in range(img.height):
        t = y / max(img.height - 1, 1)
        for (t0, c0), (t1, c1) in zip(stops, stops[1:]):
            if t0 <= t <= t1:
                k = (t - t0) / (t1 - t0)
                color = tuple(int(c0[i] + (c1[i] - c0[i]) * k) for i in range(3))
                break
        d.line([(0, y), (img.width, y)], fill=color)
    return img


def text_size(text: str, font) -> tuple[int, int]:
    left, top, right, bottom = font.getbbox(text)
    return right - left, bottom - top


def draw_gold_text(img: Image.Image, xy: tuple[int, int], text: str, font, anchor: str = "la") -> tuple[int, int, int, int]:
    """Dibuja texto con degradado dorado. Devuelve la caja (x0, y0, x1, y1) ocupada."""
    mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(mask).text(xy, text, font=font, fill=255, anchor=anchor)
    box = mask.getbbox()
    if not box:
        return (*xy, *xy)
    gradient = gold_gradient(box[2] - box[0], box[3] - box[1])
    full = Image.new("RGB", img.size, GOLD)
    full.paste(gradient, (box[0], box[1]))
    img.paste(full, (0, 0), mask)
    return box


def spaced_width(text: str, font, tracking: int) -> int:
    return int(sum(font.getlength(c) for c in text) + tracking * max(len(text) - 1, 0))


def draw_spaced(draw: ImageDraw.ImageDraw, x: int, y: int, text: str, font, fill, tracking: int = 6, align: str = "left") -> int:
    """Texto con espaciado entre letras. ``align``: left | center | right respecto a x. Devuelve el ancho."""
    width = spaced_width(text, font, tracking)
    start = x if align == "left" else x - width // 2 if align == "center" else x - width
    cursor = start
    for ch in text:
        draw.text((cursor, y), ch, font=font, fill=fill)
        cursor += font.getlength(ch) + tracking
    return width


def wrap_text(text: str, font, max_width: int) -> list[str]:
    """Ajusta el texto a un ancho en píxeles respetando saltos de línea."""
    lines: list[str] = []
    for paragraph in (text or "").splitlines() or [""]:
        words, current = paragraph.split(), ""
        if not words:
            lines.append("")
            continue
        for word in words:
            trial = f"{current} {word}".strip()
            if font.getlength(trial) <= max_width or not current:
                current = trial
            else:
                lines.append(current)
                current = word
        lines.append(current)
    return lines


def fit_font(role: str, text: str, max_width: int, start_size: int, min_size: int = 20):
    """Reduce el tamaño de la fuente hasta que el texto cabe en ``max_width``."""
    from documents.fonts import get_font

    size = start_size
    font: ImageFont.ImageFont = get_font(role, size)
    while size > min_size and font.getlength(text) > max_width:
        size -= 4
        font = get_font(role, size)
    return font
