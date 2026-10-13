"""Configuración global: rutas, marca, catálogos y valores por defecto.

Todo lo que es "constante de negocio" vive aquí para no repartir números mágicos
por el resto del código.
"""
from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
ASSETS_DIR = BASE_DIR / "assets"
FONTS_DIR = ASSETS_DIR / "fonts"
TIMEZONE = "Europe/Madrid"


def db_path() -> Path:
    """Ruta de la base de datos (se lee en cada llamada para poder cambiarla en tests)."""
    env = os.environ.get("JD_DB_PATH")
    if env:
        return Path(env)
    data_dir = Path(os.environ.get("JD_DATA_DIR", BASE_DIR / "data"))
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / "judit_domingo.db"


# --------------------------------------------------------------------------- marca
BRAND_NAME = "Judit Domingo"
BRAND_TAGLINE = "CENTRE D'ESTÈTICA"


class Colors:
    """Paleta de marca (negro azabache + oro)."""

    BG = "#0b0a0f"
    SURFACE = "#15131c"
    SURFACE_2 = "#1d1a26"
    BORDER = "#2c2838"
    GOLD = "#e6c566"
    GOLD_DEEP = "#ba9530"
    GOLD_SOFT = "#f3e3ad"
    TEXT = "#f3efe6"
    MUTED = "#a39c8e"
    OK = "#7fb89a"
    WARN = "#e0a458"
    DANGER = "#d9777f"


# --------------------------------------------------------------------------- negocio
VAT_RATES = (0, 4, 10, 21)
DEFAULT_VAT = 21

# (clave, etiqueta, icono, ¿entra dinero en caja/banco?)
PAYMENT_METHODS = (
    ("efectivo", "Efectivo", "💶", True),
    ("tarjeta", "Tarjeta", "💳", True),
    ("bizum", "Bizum", "📲", True),
    ("monedero", "Monedero", "👛", False),
    ("tarjeta_regalo", "Tarjeta regalo", "🎁", False),
)
PAYMENT_LABELS = {k: lbl for k, lbl, _, _ in PAYMENT_METHODS}
PAYMENT_ICONS = {k: ico for k, _, ico, _ in PAYMENT_METHODS}
CASH_IN_METHODS = tuple(k for k, _, _, cash_in in PAYMENT_METHODS if cash_in)

# Estados de una cita
STATUS_PENDING = "pendiente"
STATUS_CONFIRMED = "confirmada"
STATUS_DONE = "completada"
STATUS_CANCELLED = "cancelada"
STATUS_NOSHOW = "no_show"
APPOINTMENT_STATUSES = (
    (STATUS_PENDING, "Pendiente", "🕓"),
    (STATUS_CONFIRMED, "Confirmada", "✅"),
    (STATUS_DONE, "Completada", "✔️"),
    (STATUS_CANCELLED, "Cancelada", "✖️"),
    (STATUS_NOSHOW, "No se presentó", "🚫"),
)
STATUS_LABELS = {k: lbl for k, lbl, _ in APPOINTMENT_STATUSES}
STATUS_ICONS = {k: ico for k, _, ico in APPOINTMENT_STATUSES}

# Tipos de factura (códigos de la normativa de facturación)
INVOICE_SIMPLE = "F2"  # factura simplificada (ticket)
INVOICE_RECTIFY = "R5"  # rectificativa de factura simplificada

GIFT_ACTIVE = "activa"
GIFT_EMPTY = "agotada"
GIFT_EXPIRED = "caducada"
GIFT_VOID = "anulada"

# Servicios de ejemplo (editables en Ajustes → Servicios). Los precios llevan IVA.
# (nombre, categoría, minutos, precio en céntimos, color, descripción)
DEFAULT_SERVICES = (
    ("Limpieza facial profunda", "Facial", 75, 5500, "#c9a24b", "Limpieza en profundidad con extracción y mascarilla."),
    ("Limpieza facial hidratante", "Facial", 60, 4500, "#d8b866", "Limpieza suave con hidratación intensiva."),
    ("Tratamiento facial antiedad", "Facial", 75, 7500, "#b88a3a", "Protocolo reafirmante con activos antiedad."),
    ("Maderoterapia", "Corporal", 60, 6000, "#8f7bb5", "Masaje con instrumentos de madera, reductor y drenante."),
    ("Masaje relajante", "Corporal", 50, 5000, "#6f9fb0", "Masaje de cuerpo completo para liberar tensión."),
    ("Drenaje linfático manual", "Corporal", 60, 6000, "#7fa89a", "Técnica suave para favorecer la circulación linfática."),
    ("Presoterapia", "Corporal", 40, 3500, "#7c8fb8", "Compresión secuencial para piernas cansadas."),
    ("Manicura semipermanente", "Manos y pies", 60, 3000, "#c98f9d", "Manicura con esmalte semipermanente."),
    ("Pedicura spa", "Manos y pies", 60, 3800, "#b97f8f", "Pedicura con exfoliación e hidratación."),
    ("Depilación cera (piernas)", "Depilación", 45, 2800, "#9aa56b", "Depilación con cera de piernas completas."),
    ("Lifting de pestañas", "Mirada", 60, 4500, "#a57fa8", "Curvatura y tinte de pestañas."),
    ("Diseño de cejas", "Mirada", 30, 1500, "#8a8f9e", "Diseño y perfilado de cejas."),
)

DEFAULT_SETTINGS = {
    "business_name": "Judit Domingo - Centre d'Estètica",
    "legal_name": "",
    "nif": "",
    "address": "",
    "city": "",
    "postal_code": "",
    "phone": "",
    "email": "",
    "invoice_series": "FS",
    "gift_validity_months": "12",
    "open_days": "1,2,3,4,5,6",  # 0 = domingo ... 6 = sábado
    "open_time": "09:00",
    "close_time": "20:00",
    "slot_minutes": "15",
    "default_country_code": "34",
    "verifactu_mode": "preparado",
    "tpl_reminder": (
        "Hola {nombre} 👋 Te recordamos tu cita en {centro}: {servicio}, "
        "{fecha} a las {hora}. Si necesitas cambiarla, avísanos con antelación. ¡Te esperamos! ✨"
    ),
    "tpl_birthday": (
        "¡Feliz cumpleaños, {nombre}! 🎂✨ Desde {centro} queremos celebrarlo contigo: "
        "te esperamos este mes con un detalle especial."
    ),
    "tpl_reactivation": (
        "Hola {nombre}, hace tiempo que no te vemos por {centro} y te echamos de menos 💛 "
        "¿Te reservamos un hueco para mimarte? Escríbenos y lo organizamos."
    ),
    "tpl_giftcard": (
        "Hola {nombre} 🎁 Te han regalado una tarjeta de {importe} para {centro}. "
        "Código: {codigo}. Válida hasta el {caducidad}. ¡Reserva tu cita cuando quieras!"
    ),
    "tpl_receipt": (
        "Gracias por visitarnos, {nombre} 💛 Tu ticket {numero} por {importe} en {centro}. ¡Hasta pronto!"
    ),
}

# Paleta apagada y elegante para colorear categorías en el calendario
CATEGORY_FALLBACK_COLOR = "#a39c8e"
