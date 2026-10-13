"""Ajustes del centro guardados en la tabla ``settings`` (clave/valor)."""
from __future__ import annotations

from core.config import DEFAULT_SETTINGS
from core.database import fetch_all, get_conn


def all_settings() -> dict[str, str]:
    data = dict(DEFAULT_SETTINGS)
    data.update({r["key"]: r["value"] for r in fetch_all("SELECT key, value FROM settings")})
    return data


def get(key: str, default: str | None = None) -> str:
    value = all_settings().get(key)
    return value if value is not None else (default if default is not None else "")


def set_many(values: dict[str, str]) -> None:
    with get_conn() as conn:
        for key, value in values.items():
            conn.execute(
                "INSERT INTO settings(key, value) VALUES (?,?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, "" if value is None else str(value)),
            )


def open_days() -> list[int]:
    """Días de apertura con la convención de FullCalendar: 0 = domingo … 6 = sábado."""
    raw = get("open_days", "1,2,3,4,5,6")
    return [int(x) for x in raw.split(",") if x.strip().isdigit()]


def default_cc() -> str:
    return get("default_country_code", "34") or "34"


def center_name() -> str:
    return get("business_name", "Judit Domingo - Centre d'Estètica")
