"""Utilidades puras (sin Streamlit ni base de datos): dinero, fechas, teléfonos, plantillas."""
from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from urllib.parse import quote
from zoneinfo import ZoneInfo

from core.config import TIMEZONE

TZ = ZoneInfo(TIMEZONE)

WEEKDAYS_ES = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")
WEEKDAYS_SHORT = ("lun", "mar", "mié", "jue", "vie", "sáb", "dom")
MONTHS_ES = (
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
)


# --------------------------------------------------------------------------- tiempo
def now() -> datetime:
    """Fecha y hora actuales en la zona horaria del centro (sin tzinfo, hora local)."""
    return datetime.now(TZ).replace(tzinfo=None, microsecond=0)


def now_with_tz() -> datetime:
    """Fecha y hora actuales con zona horaria (para sellos de registro de facturación)."""
    return datetime.now(TZ).replace(microsecond=0)


def today() -> date:
    return now().date()


def parse_date(value) -> date | None:
    """Convierte str ISO / datetime / date en date. Devuelve None si no se puede."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        pass
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%d/%m/%y", "%d.%m.%Y"):  # formatos habituales en España
        try:
            return datetime.strptime(text[:10], fmt).date()
        except ValueError:
            continue
    return None


def parse_dt(value) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    try:
        return datetime.fromisoformat(str(value).replace("Z", "")).replace(tzinfo=None)
    except ValueError:
        return None


def iso_minute(dt: datetime) -> str:
    """'2026-10-11T12:30' — formato canónico de las citas."""
    return dt.strftime("%Y-%m-%dT%H:%M")


def fmt_date(value) -> str:
    d = parse_date(value)
    return d.strftime("%d/%m/%Y") if d else ""


def fmt_time(value) -> str:
    dt = parse_dt(value)
    return dt.strftime("%H:%M") if dt else ""


def fmt_datetime(value) -> str:
    dt = parse_dt(value)
    return dt.strftime("%d/%m/%Y %H:%M") if dt else ""


def fmt_long_date(value) -> str:
    """'domingo 11 de octubre'."""
    d = parse_date(value)
    if not d:
        return ""
    return f"{WEEKDAYS_ES[d.weekday()]} {d.day} de {MONTHS_ES[d.month - 1]}"


def quarter_of(d: date) -> int:
    return (d.month - 1) // 3 + 1


def quarter_bounds(year: int, quarter: int) -> tuple[date, date]:
    """Primer y último día del trimestre."""
    start_month = 3 * (quarter - 1) + 1
    start = date(year, start_month, 1)
    if quarter == 4:
        end = date(year, 12, 31)
    else:
        end = date.fromordinal(date(year, start_month + 3, 1).toordinal() - 1)
    return start, end


def age_from(birthdate, ref: date | None = None) -> int | None:
    b = parse_date(birthdate)
    if not b:
        return None
    ref = ref or today()
    return ref.year - b.year - ((ref.month, ref.day) < (b.month, b.day))


# --------------------------------------------------------------------------- dinero
def to_cents(value) -> int:
    """Euros (float/str/Decimal) → céntimos enteros con redondeo comercial."""
    if value is None or value == "":
        return 0
    if isinstance(value, str):
        value = value.replace("€", "").replace(" ", "")
        if "," in value:  # formato español: 1.234,56
            value = value.replace(".", "").replace(",", ".")
    d =Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return int(d * 100)


def from_cents(cents: int) -> float:
    return round((cents or 0) / 100, 2)


def fmt_eur(cents: int | None, sign: bool = False) -> str:
    """12345 → '123,45 €' (formato español)."""
    cents = int(cents or 0)
    neg = cents < 0
    whole, frac = divmod(abs(cents), 100)
    text = f"{whole:,}".replace(",", ".") + f",{frac:02d} €"
    if neg:
        return "−" + text
    return ("+" + text) if sign and cents > 0 else text


def split_vat(gross_cents: int, rate: int | float) -> tuple[int, int]:
    """Precio con IVA → (base, cuota). La base absorbe el redondeo para que base+cuota == bruto."""
    if not rate:
        return gross_cents, 0
    base = int((Decimal(gross_cents) / (Decimal(1) + Decimal(str(rate)) / 100)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    return base, gross_cents - base


def add_vat(base_cents: int, rate: int | float) -> tuple[int, int]:
    """Base → (cuota, total)."""
    vat = int((Decimal(base_cents) * Decimal(str(rate)) / 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    return vat, base_cents + vat


# --------------------------------------------------------------------------- texto
def strip_accents(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", text or "") if unicodedata.category(c) != "Mn")


def norm(text: str) -> str:
    """Minúsculas, sin acentos ni signos: para buscar y comparar."""
    return re.sub(r"[^a-z0-9ñ ]+", " ", strip_accents(text or "").lower()).strip()


def render_template(template: str, **values) -> str:
    """Sustituye {clave} sin fallar si falta alguna o el texto contiene otras llaves."""
    out = template or ""
    for key, val in values.items():
        out = out.replace("{" + key + "}", "" if val is None else str(val))
    return out


# --------------------------------------------------------------------------- contacto
def normalize_phone(raw: str | None, default_cc: str = "34") -> str:
    """Devuelve el teléfono en formato internacional sin '+' (p. ej. 34600123456) o '' si no es válido."""
    if not raw:
        return ""
    digits = re.sub(r"\D", "", str(raw))
    if str(raw).strip().startswith("00"):
        digits = digits[2:]
    elif len(digits) == 9:  # nacional sin prefijo
        digits = default_cc + digits
    if not 10 <= len(digits) <= 15:
        return ""
    return digits


def whatsapp_link(phone: str | None, text: str = "", default_cc: str = "34") -> str:
    """Enlace api.whatsapp.com listo para abrir (con el mensaje ya escrito)."""
    num = normalize_phone(phone, default_cc)
    if not num:
        return ""
    return f"https://api.whatsapp.com/send?phone={num}&text={quote(text, safe='')}"


def initials(name: str) -> str:
    parts = [p for p in re.split(r"\s+", (name or "").strip()) if p]
    return "".join(p[0].upper() for p in parts[:2]) or "?"
