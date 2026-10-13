"""Fichero de clientes (CRM): altas, búsqueda, historial de tratamientos, cumpleaños y RGPD."""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

from core.config import STATUS_DONE, STATUS_NOSHOW
from core.database import audit, execute, fetch_all, fetch_one, get_conn
from core.utils import norm, now, parse_date, today
from services import wallet

EDITABLE_FIELDS = (
    "first_name", "last_name", "phone", "email", "birthdate", "dni", "address",
    "notes_tech", "notes_medical", "allergies", "source", "marketing_consent", "active",
)


def full_name(client: dict | None) -> str:
    if not client:
        return ""
    return f"{client.get('first_name', '')} {client.get('last_name', '')}".strip()


# --------------------------------------------------------------------------- CRUD
def create_client(first_name: str, last_name: str = "", phone: str = "", email: str = "", birthdate=None,
                  dni: str = "", address: str = "", notes_tech: str = "", notes_medical: str = "",
                  allergies: str = "", source: str = "", marketing_consent: bool = False) -> int:
    first_name = (first_name or "").strip()
    if not first_name:
        raise ValueError("El nombre es obligatorio.")
    bd = parse_date(birthdate)
    cid = execute(
        "INSERT INTO clients(first_name, last_name, phone, email, birthdate, dni, address, notes_tech, notes_medical,"
        " allergies, source, marketing_consent, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (first_name, (last_name or "").strip(), (phone or "").strip(), (email or "").strip(),
         bd.isoformat() if bd else None, (dni or "").strip().upper(), (address or "").strip(),
         notes_tech, notes_medical, allergies, source, 1 if marketing_consent else 0,
         now().isoformat(timespec="seconds")),
    )
    audit("client_create", f"id={cid}")
    return cid


def update_client(client_id: int, **fields) -> None:
    data = {k: v for k, v in fields.items() if k in EDITABLE_FIELDS}
    if not data:
        return
    if "first_name" in data and not str(data["first_name"]).strip():
        raise ValueError("El nombre es obligatorio.")
    if "birthdate" in data:
        bd = parse_date(data["birthdate"])
        data["birthdate"] = bd.isoformat() if bd else None
    if "dni" in data:
        data["dni"] = str(data["dni"]).strip().upper()
    for flag in ("marketing_consent", "active"):
        if flag in data:
            data[flag] = 1 if data[flag] else 0
    sets = ", ".join(f"{k} = ?" for k in data)
    execute(f"UPDATE clients SET {sets} WHERE id = ?", (*data.values(), client_id))


def get_client(client_id: int | None) -> dict | None:
    if not client_id:
        return None
    return fetch_one("SELECT * FROM clients WHERE id = ?", (client_id,))


# --------------------------------------------------------------------------- listados y búsqueda
_LIST_SQL = """
SELECT c.*,
  COALESCE((SELECT SUM(amount_cents) FROM wallet_movements w WHERE w.client_id = c.id), 0) AS wallet_cents,
  (SELECT MAX(substr(a.start_ts, 1, 10)) FROM appointments a WHERE a.client_id = c.id AND a.status = ?) AS last_visit
FROM clients c
WHERE c.active = 1 AND c.anonymized = 0
ORDER BY c.first_name COLLATE NOCASE, c.last_name COLLATE NOCASE
"""

FILTERS = {
    "todos": "Todos",
    "saldo": "Con saldo en monedero",
    "cumple": "Cumplen este mes",
    "inactivos": "Inactivos (+90 días)",
    "sin_rgpd": "Sin RGPD firmado",
}


def search_clients(query: str = "", filter_key: str = "todos", inactive_days: int = 90) -> list[dict]:
    rows = fetch_all(_LIST_SQL, (STATUS_DONE,))
    q = norm(query)
    limit_day = today() - timedelta(days=inactive_days)
    out = []
    for r in rows:
        if q:
            haystack = norm(" ".join(str(r.get(k) or "") for k in ("first_name", "last_name", "phone", "email", "dni")))
            if not all(token in haystack for token in q.split()):
                continue
        if filter_key == "saldo" and r["wallet_cents"] <= 0:
            continue
        if filter_key == "cumple":
            bd = parse_date(r["birthdate"])
            if not bd or bd.month != today().month:
                continue
        if filter_key == "inactivos":
            last = parse_date(r["last_visit"])
            created = parse_date(r["created_at"]) or today()
            if (last and last > limit_day) or (not last and created > limit_day):
                continue
        if filter_key == "sin_rgpd" and r["rgpd_signed"]:
            continue
        out.append(r)
    return out


def clients_dataframe(rows: list[dict]) -> pd.DataFrame:
    """Tabla compacta para mostrar en pantalla (el índice original queda en la columna id)."""
    from core.utils import fmt_date, fmt_eur

    return pd.DataFrame(
        [
            {
                "id": r["id"],
                "Cliente": full_name(r),
                "Teléfono": r["phone"],
                "Última visita": fmt_date(r["last_visit"]) or "—",
                "Monedero": fmt_eur(r["wallet_cents"]),
                "RGPD": "✓" if r["rgpd_signed"] else "✗",
            }
            for r in rows
        ],
        columns=["id", "Cliente", "Teléfono", "Última visita", "Monedero", "RGPD"],
    )


def birthdays_in_month(month: int) -> list[dict]:
    rows = fetch_all(
        "SELECT * FROM clients WHERE active = 1 AND anonymized = 0 AND birthdate IS NOT NULL "
        "AND CAST(strftime('%m', birthdate) AS INTEGER) = ? ORDER BY CAST(strftime('%d', birthdate) AS INTEGER)",
        (month,),
    )
    ref = today()
    for r in rows:
        bd = parse_date(r["birthdate"])
        r["day"] = bd.day if bd else 0
        r["turns"] = (ref.year - bd.year) if bd else None
    return rows


def birthdays_between(start: date, end: date) -> list[dict]:
    """Clientes que cumplen años entre dos fechas (ambas incluidas), p. ej. «esta semana»."""
    found = []
    for r in fetch_all("SELECT * FROM clients WHERE active = 1 AND anonymized = 0 AND birthdate IS NOT NULL"):
        bd = parse_date(r["birthdate"])
        if not bd:
            continue
        for year in {start.year, end.year}:
            try:
                this_year = bd.replace(year=year)
            except ValueError:  # 29 de febrero
                this_year = date(year, 2, 28)
            if start <= this_year <= end:
                r["day"] = this_year.day
                r["date"] = this_year
                found.append(r)
                break
    return sorted(found, key=lambda r: r["date"])


def inactive_clients(days: int = 90, only_with_consent: bool = True) -> tuple[list[dict], int]:
    """Clientes sin visitas completadas desde hace ``days`` días.

    Devuelve (contactables, excluidos_por_no_tener_consentimiento_de_marketing).
    """
    rows = search_clients(filter_key="inactivos", inactive_days=days)
    if not only_with_consent:
        return rows, 0
    ok = [r for r in rows if r["marketing_consent"] and r["phone"]]
    return ok, len(rows) - len(ok)


# --------------------------------------------------------------------------- estadísticas y fichas
def client_stats(client_id: int) -> dict:
    visits = fetch_one(
        "SELECT COUNT(*) AS n, MAX(substr(start_ts,1,10)) AS last FROM appointments WHERE client_id = ? AND status = ?",
        (client_id, STATUS_DONE),
    ) or {"n": 0, "last": None}
    noshow = fetch_one("SELECT COUNT(*) AS n FROM appointments WHERE client_id = ? AND status = ?", (client_id, STATUS_NOSHOW))["n"]
    spent = fetch_one("SELECT COALESCE(SUM(total_cents),0) AS s FROM invoices WHERE client_id = ?", (client_id,))["s"]
    nxt = fetch_one(
        "SELECT start_ts, service_name FROM appointments WHERE client_id = ? AND start_ts >= ? "
        "AND status IN ('pendiente','confirmada') ORDER BY start_ts LIMIT 1",
        (client_id, now().strftime("%Y-%m-%dT%H:%M")),
    )
    return {
        "visits": visits["n"], "last_visit": visits["last"], "no_shows": noshow,
        "spent_cents": spent, "next": nxt, "wallet_cents": wallet.balance(client_id),
    }


def add_treatment(client_id: int, date_value, service_name: str, notes: str = "", products: str = "",
                  professional: str = "", appointment_id: int | None = None) -> int:
    d = parse_date(date_value) or today()
    return execute(
        "INSERT INTO treatments(client_id, date, service_name, appointment_id, notes, products, professional, created_at)"
        " VALUES (?,?,?,?,?,?,?,?)",
        (client_id, d.isoformat(), service_name.strip(), appointment_id, notes, products, professional,
         now().isoformat(timespec="seconds")),
    )


def list_treatments(client_id: int) -> list[dict]:
    return fetch_all("SELECT * FROM treatments WHERE client_id = ? ORDER BY date DESC, id DESC", (client_id,))


def delete_treatment(treatment_id: int) -> None:
    execute("DELETE FROM treatments WHERE id = ?", (treatment_id,))


# --------------------------------------------------------------------------- RGPD
def export_client_data(client_id: int) -> dict:
    """Derecho de acceso/portabilidad: todos los datos de la clienta en un diccionario."""
    client = get_client(client_id)
    if not client:
        raise ValueError("Cliente no encontrado.")
    consents = fetch_all(
        "SELECT id, kind, treatment, text_version, signed_name, signed_at, revoked FROM consents WHERE client_id = ?",
        (client_id,),
    )
    return {
        "exportado_el": now().isoformat(timespec="seconds"),
        "cliente": client,
        "citas": fetch_all("SELECT * FROM appointments WHERE client_id = ? ORDER BY start_ts", (client_id,)),
        "tratamientos": list_treatments(client_id),
        "consentimientos": consents,
        "monedero": wallet.movements(client_id),
        "facturas": fetch_all(
            "SELECT full_number, issued_at, total_cents, kind FROM invoices WHERE client_id = ? ORDER BY issued_at", (client_id,)
        ),
    }


def anonymize_client(client_id: int) -> None:
    """Derecho de supresión: borra los datos personales pero conserva facturas y estadísticas.

    Las facturas se conservan por obligación legal; el hash encadenado no incluye datos del cliente,
    por lo que la cadena sigue siendo válida.
    """
    with get_conn() as conn:
        execute(
            "UPDATE clients SET first_name = ?, last_name = '', phone = '', email = '', birthdate = NULL, dni = '', address = '',"
            " notes_tech = '', notes_medical = '', allergies = '', source = '', marketing_consent = 0, rgpd_signed = 0,"
            " active = 0, anonymized = 1 WHERE id = ?",
            (f"Cliente anonimizado #{client_id}", client_id), conn,
        )
        execute("DELETE FROM consents WHERE client_id = ?", (client_id,), conn)
        execute("UPDATE invoices SET client_name = '', client_nif = '' WHERE client_id = ?", (client_id,), conn)
        execute("UPDATE appointments SET notes = '' WHERE client_id = ?", (client_id,), conn)
        execute("UPDATE treatments SET notes = '', products = '' WHERE client_id = ?", (client_id,), conn)
        audit("client_anonymize", f"id={client_id}", conn)


# --------------------------------------------------------------------------- importación CSV
_ALIASES = {
    "first_name": ("nombre", "name", "first_name", "nom"),
    "last_name": ("apellidos", "apellido", "last_name", "cognoms"),
    "phone": ("telefono", "teléfono", "movil", "móvil", "phone", "tel", "telefon"),
    "email": ("email", "correo", "mail", "e-mail"),
    "birthdate": ("fecha_nacimiento", "nacimiento", "cumpleaños", "birthdate", "fecha nacimiento", "data_naixement"),
    "dni": ("dni", "nif", "nie"),
    "address": ("direccion", "dirección", "address", "adreça"),
}


def import_clients_df(df: pd.DataFrame) -> dict:
    """Importa clientes desde un DataFrame (CSV/Excel). Detecta columnas por nombre habitual."""
    mapping: dict[str, str] = {}
    for col in df.columns:
        key = norm(str(col)).replace(" ", "_")
        for field, aliases in _ALIASES.items():
            if key in {norm(a).replace(" ", "_") for a in aliases} and field not in mapping:
                mapping[field] = col
    if "first_name" not in mapping:
        raise ValueError("No encuentro la columna del nombre (usa «nombre»).")
    created = skipped = 0
    errors: list[str] = []
    existing = {norm(full_name(c)) + "|" + "".join(ch for ch in c["phone"] if ch.isdigit()) for c in fetch_all("SELECT * FROM clients")}
    for idx, row in df.iterrows():
        values = {f: ("" if pd.isna(row[c]) else str(row[c]).strip()) for f, c in mapping.items()}
        if not values.get("first_name"):
            skipped += 1
            continue
        key = norm(f"{values.get('first_name', '')} {values.get('last_name', '')}") + "|" + "".join(ch for ch in values.get("phone", "") if ch.isdigit())
        if key in existing:
            skipped += 1
            continue
        try:
            create_client(**values)
            existing.add(key)
            created += 1
        except Exception as exc:  # fila rara: seguimos con el resto
            errors.append(f"Fila {idx + 2}: {exc}")
    return {"creados": created, "omitidos": skipped, "errores": errors}
