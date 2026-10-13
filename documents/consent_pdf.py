"""PDF de consentimientos firmados (RGPD e informados por tratamiento), con firma manuscrita o tipográfica."""
from __future__ import annotations

import io

from PIL import Image, ImageDraw

from core.utils import fmt_datetime
from documents import brand
from documents.fonts import get_font

DPI = 200
W, H = 1654, 2339  # A4 a 200 ppp
PAPER, INK, MUTED, GOLD_INK, RULE = (253, 251, 246), (26, 24, 34), (125, 118, 104), (150, 119, 24), (222, 212, 180)
MARGIN = 140
BODY = 28
LINE_H = 42


def _signature_image(signature_png: bytes | None, signed_name: str, max_w: int = 560, max_h: int = 170) -> Image.Image:
    """Firma dibujada (PNG con transparencia) o, si no hay, el nombre en tipografía caligráfica."""
    if signature_png:
        try:
            raw = Image.open(io.BytesIO(signature_png)).convert("RGBA")
            bg = Image.new("RGBA", raw.size, (*PAPER, 255))
            bg.alpha_composite(raw)
            sig = bg.convert("RGB")
            sig.thumbnail((max_w, max_h), Image.LANCZOS)
            return sig
        except OSError:
            pass
    font = get_font("script", 90)
    probe = Image.new("RGB", (10, 10), PAPER)
    box = ImageDraw.Draw(probe).textbbox((0, 0), signed_name, font=font)
    sig = Image.new("RGB", (box[2] - box[0] + 30, box[3] - box[1] + 40), PAPER)
    ImageDraw.Draw(sig).text((15, 10 - box[1]), signed_name, font=font, fill=(40, 40, 90))
    sig.thumbnail((max_w, max_h), Image.LANCZOS)
    return sig


class _Doc:
    """Pequeño motor de maquetación por páginas."""

    def __init__(self, title: str, footer_note: str):
        self.pages: list[Image.Image] = []
        self.title, self.footer_note = title, footer_note
        self.img: Image.Image
        self.d: ImageDraw.ImageDraw
        self.y = 0
        self._new_page()

    def _new_page(self) -> None:
        self.img = Image.new("RGB", (W, H), PAPER)
        self.d = ImageDraw.Draw(self.img)
        self.pages.append(self.img)
        self.d.text((MARGIN, 90), "Judit Domingo", font=get_font("script", 80), fill=GOLD_INK)
        brand.draw_spaced(self.d, MARGIN + 4, 190, "CENTRE D'ESTÈTICA", get_font("sans_medium", 20), MUTED, tracking=8)
        self.d.line([(MARGIN, 240), (W - MARGIN, 240)], fill=GOLD_INK, width=3)
        self.y = 290

    def ensure(self, needed: int) -> None:
        if self.y + needed > H - 190:
            self._new_page()

    def paragraph(self, text: str, font, fill=INK, indent: int = 0, gap: int = 0) -> None:
        for line in brand.wrap_text(text, font, W - 2 * MARGIN - indent):
            self.ensure(LINE_H)
            self.d.text((MARGIN + indent, self.y), line, font=font, fill=fill)
            self.y += LINE_H
        self.y += gap

    def body(self, text: str) -> None:
        font = get_font("sans", BODY)
        for raw in text.split("\n"):
            if not raw.strip():
                self.y += 14
            elif raw.startswith("  •"):
                self.ensure(LINE_H)
                self.d.text((MARGIN + 20, self.y), "•", font=font, fill=GOLD_INK)
                self.paragraph(raw.replace("  •", "", 1).strip(), font, indent=52)
            elif raw.isupper() and len(raw) < 90:
                self.paragraph(raw, get_font("sans_bold", BODY + 2), fill=GOLD_INK, gap=6)
            else:
                self.paragraph(raw, font)

    def finish(self, doc_hash: str) -> bytes:
        tiny = get_font("sans", 20)
        for n, page in enumerate(self.pages, start=1):
            d = ImageDraw.Draw(page)
            d.line([(MARGIN, H - 150), (W - MARGIN, H - 150)], fill=RULE, width=1)
            d.text((MARGIN, H - 130), self.footer_note, font=tiny, fill=MUTED)
            d.text((MARGIN, H - 98), f"Huella del documento: {doc_hash[:32]}…", font=tiny, fill=MUTED)
            label = f"Página {n} de {len(self.pages)}"
            d.text((W - MARGIN - tiny.getlength(label), H - 130), label, font=tiny, fill=MUTED)
        buf = io.BytesIO()
        self.pages[0].save(buf, "PDF", resolution=DPI, save_all=True, append_images=self.pages[1:])
        return buf.getvalue()


def render_consent_pdf(consent: dict, client_name: str, client_dni: str = "") -> bytes:
    """``consent`` es una fila completa de la tabla ``consents`` (incluye texto firmado y firma)."""
    kind = "Protección de datos (RGPD)" if consent["kind"] == "rgpd" else f"Consentimiento informado: {consent['treatment']}"
    doc = _Doc(kind, f"Documento firmado electrónicamente · versión de texto {consent['text_version']}")
    doc.paragraph(kind, get_font("serif_bold", 52), fill=INK, gap=14)
    ident = f"Clienta: {client_name}" + (f"   ·   DNI/NIE: {client_dni}" if client_dni else "")
    doc.paragraph(ident, get_font("sans_medium", BODY), fill=MUTED, gap=24)
    doc.body(consent["text_body"])

    sig = _signature_image(consent.get("signature_png"), consent["signed_name"])
    doc.ensure(sig.height + 230)
    doc.y += 50
    doc.d.line([(MARGIN, doc.y), (W - MARGIN, doc.y)], fill=RULE, width=1)
    doc.y += 24
    doc.d.text((MARGIN, doc.y), "FIRMA", font=get_font("sans_medium", 22), fill=MUTED)
    doc.y += 34
    doc.img.paste(sig, (MARGIN, doc.y))
    base = doc.y + sig.height + 10
    doc.d.line([(MARGIN, base), (MARGIN + 600, base)], fill=INK, width=2)
    doc.d.text((MARGIN, base + 14), consent["signed_name"], font=get_font("sans_medium", 28), fill=INK)
    doc.d.text((MARGIN, base + 52), f"Firmado el {fmt_datetime(consent['signed_at'])}", font=get_font("sans", 24), fill=MUTED)
    return doc.finish(consent.get("doc_hash", ""))
