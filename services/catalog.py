"""Catálogo de servicios/tratamientos del centro."""
from __future__ import annotations

from core.database import execute, fetch_all, fetch_one


def list_services(active_only: bool = True) -> list[dict]:
    sql = "SELECT * FROM services"
    if active_only:
        sql += " WHERE active = 1"
    return fetch_all(sql + " ORDER BY category, sort, name")


def get_service(service_id: int | None) -> dict | None:
    if not service_id:
        return None
    return fetch_one("SELECT * FROM services WHERE id = ?", (service_id,))


def categories() -> list[str]:
    return [r["category"] for r in fetch_all("SELECT DISTINCT category FROM services ORDER BY category")]


def save_service(
    name: str,
    category: str = "General",
    duration_min: int = 60,
    price_cents: int = 0,
    vat_rate: int = 21,
    color: str = "#c9a24b",
    description: str = "",
    active: bool = True,
    service_id: int | None = None,
) -> int:
    """Crea o actualiza un servicio. Devuelve su id."""
    name = (name or "").strip()
    if not name:
        raise ValueError("El servicio necesita un nombre.")
    if duration_min <= 0:
        raise ValueError("La duración debe ser mayor que 0.")
    if price_cents < 0:
        raise ValueError("El precio no puede ser negativo.")
    params = (name, category.strip() or "General", int(duration_min), int(price_cents), int(vat_rate), color, description, 1 if active else 0)
    if service_id:
        execute(
            "UPDATE services SET name=?, category=?, duration_min=?, price_cents=?, vat_rate=?, color=?, description=?, active=? WHERE id=?",
            params + (service_id,),
        )
        return service_id
    return execute(
        "INSERT INTO services(name, category, duration_min, price_cents, vat_rate, color, description, active) VALUES (?,?,?,?,?,?,?,?)",
        params,
    )


def set_active(service_id: int, active: bool) -> None:
    execute("UPDATE services SET active = ? WHERE id = ?", (1 if active else 0, service_id))
