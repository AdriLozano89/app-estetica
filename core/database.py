"""Acceso a SQLite: conexión, esquema versionado (migraciones), datos iniciales y helpers.

* Todo el dinero se guarda en **céntimos enteros** (sin errores de coma flotante).
* El esquema se versiona con ``PRAGMA user_version``: para añadir columnas o tablas
  en el futuro basta con añadir un script nuevo al final de ``MIGRATIONS``.
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from typing import Any, Iterable, Iterator

from core.config import DEFAULT_SERVICES, DEFAULT_SETTINGS, db_path
from core.utils import now

SCHEMA_V1 = """
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY, username TEXT UNIQUE NOT NULL,
    salt TEXT NOT NULL, pw_hash TEXT NOT NULL, created_at TEXT
);

CREATE TABLE IF NOT EXISTS services (
    id INTEGER PRIMARY KEY, name TEXT NOT NULL, category TEXT DEFAULT 'General',
    duration_min INTEGER DEFAULT 60, price_cents INTEGER DEFAULT 0,
    vat_rate INTEGER DEFAULT 21, color TEXT DEFAULT '#c9a24b',
    description TEXT DEFAULT '', active INTEGER DEFAULT 1, sort INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS clients (
    id INTEGER PRIMARY KEY, first_name TEXT NOT NULL, last_name TEXT DEFAULT '',
    phone TEXT DEFAULT '', email TEXT DEFAULT '', birthdate TEXT, dni TEXT DEFAULT '',
    address TEXT DEFAULT '', notes_tech TEXT DEFAULT '', notes_medical TEXT DEFAULT '',
    allergies TEXT DEFAULT '', source TEXT DEFAULT '',
    marketing_consent INTEGER DEFAULT 0, rgpd_signed INTEGER DEFAULT 0,
    active INTEGER DEFAULT 1, anonymized INTEGER DEFAULT 0, created_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_clients_name ON clients(last_name, first_name);

CREATE TABLE IF NOT EXISTS appointments (
    id INTEGER PRIMARY KEY,
    client_id INTEGER REFERENCES clients(id),
    service_id INTEGER REFERENCES services(id),
    service_name TEXT DEFAULT '',
    start_ts TEXT NOT NULL, end_ts TEXT NOT NULL,
    status TEXT DEFAULT 'pendiente', price_cents INTEGER DEFAULT 0,
    professional TEXT DEFAULT '', notes TEXT DEFAULT '',
    invoice_id INTEGER, reminder_sent INTEGER DEFAULT 0, created_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_appt_start ON appointments(start_ts);
CREATE INDEX IF NOT EXISTS idx_appt_client ON appointments(client_id);

CREATE TABLE IF NOT EXISTS treatments (
    id INTEGER PRIMARY KEY, client_id INTEGER NOT NULL REFERENCES clients(id),
    date TEXT NOT NULL, service_name TEXT DEFAULT '', appointment_id INTEGER,
    notes TEXT DEFAULT '', products TEXT DEFAULT '', professional TEXT DEFAULT '',
    created_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_treat_client ON treatments(client_id, date);

CREATE TABLE IF NOT EXISTS consents (
    id INTEGER PRIMARY KEY, client_id INTEGER NOT NULL REFERENCES clients(id),
    kind TEXT NOT NULL, treatment TEXT DEFAULT '', text_version TEXT DEFAULT '',
    text_body TEXT DEFAULT '', signed_name TEXT DEFAULT '', signed_at TEXT,
    signature_png BLOB, doc_hash TEXT DEFAULT '', revoked INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_consents_client ON consents(client_id);

CREATE TABLE IF NOT EXISTS wallet_movements (
    id INTEGER PRIMARY KEY, client_id INTEGER NOT NULL REFERENCES clients(id),
    ts TEXT NOT NULL, amount_cents INTEGER NOT NULL, concept TEXT DEFAULT '',
    invoice_id INTEGER, method TEXT DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_wallet_client ON wallet_movements(client_id);

CREATE TABLE IF NOT EXISTS gift_cards (
    id INTEGER PRIMARY KEY, code TEXT UNIQUE NOT NULL,
    initial_cents INTEGER NOT NULL, balance_cents INTEGER NOT NULL,
    buyer_name TEXT DEFAULT '', buyer_phone TEXT DEFAULT '',
    recipient_name TEXT DEFAULT '', recipient_phone TEXT DEFAULT '',
    message TEXT DEFAULT '', for_service TEXT DEFAULT '',
    issued_at TEXT NOT NULL, expires_at TEXT NOT NULL,
    status TEXT DEFAULT 'activa', payment_method TEXT DEFAULT 'efectivo'
);

CREATE TABLE IF NOT EXISTS gift_card_movements (
    id INTEGER PRIMARY KEY, gift_card_id INTEGER NOT NULL REFERENCES gift_cards(id),
    ts TEXT NOT NULL, amount_cents INTEGER NOT NULL, concept TEXT DEFAULT '',
    invoice_id INTEGER
);

CREATE TABLE IF NOT EXISTS invoices (
    id INTEGER PRIMARY KEY, series TEXT NOT NULL, number INTEGER NOT NULL,
    full_number TEXT UNIQUE NOT NULL, kind TEXT NOT NULL,
    rectifies_id INTEGER REFERENCES invoices(id), rectify_reason TEXT DEFAULT '',
    issued_at TEXT NOT NULL, generated_at TEXT NOT NULL,
    client_id INTEGER REFERENCES clients(id),
    client_name TEXT DEFAULT '', client_nif TEXT DEFAULT '',
    base_cents INTEGER NOT NULL, vat_cents INTEGER NOT NULL, total_cents INTEGER NOT NULL,
    prev_hash TEXT DEFAULT '', hash TEXT NOT NULL, issuer_nif TEXT DEFAULT '',
    status TEXT DEFAULT 'emitida', appointment_id INTEGER
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_invoices_series_number ON invoices(series, number);
CREATE INDEX IF NOT EXISTS idx_invoices_date ON invoices(issued_at);

CREATE TABLE IF NOT EXISTS invoice_lines (
    id INTEGER PRIMARY KEY, invoice_id INTEGER NOT NULL REFERENCES invoices(id),
    description TEXT NOT NULL, qty REAL NOT NULL, unit_cents INTEGER NOT NULL,
    vat_rate INTEGER NOT NULL, base_cents INTEGER NOT NULL, vat_cents INTEGER NOT NULL,
    total_cents INTEGER NOT NULL, service_id INTEGER
);
CREATE INDEX IF NOT EXISTS idx_lines_invoice ON invoice_lines(invoice_id);

CREATE TABLE IF NOT EXISTS payments (
    id INTEGER PRIMARY KEY, ts TEXT NOT NULL, kind TEXT NOT NULL, ref_id INTEGER,
    invoice_id INTEGER, method TEXT NOT NULL, amount_cents INTEGER NOT NULL,
    client_id INTEGER, concept TEXT DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_payments_ts ON payments(ts);

CREATE TABLE IF NOT EXISTS expenses (
    id INTEGER PRIMARY KEY, date TEXT NOT NULL, concept TEXT NOT NULL,
    supplier TEXT DEFAULT '', category TEXT DEFAULT 'Otros', invoice_ref TEXT DEFAULT '',
    base_cents INTEGER NOT NULL, vat_rate INTEGER DEFAULT 21,
    vat_cents INTEGER NOT NULL, total_cents INTEGER NOT NULL,
    method TEXT DEFAULT 'tarjeta', vat_deductible INTEGER DEFAULT 1, created_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_expenses_date ON expenses(date);

CREATE TABLE IF NOT EXISTS cash_closings (
    id INTEGER PRIMARY KEY, date TEXT UNIQUE NOT NULL,
    opening_cents INTEGER DEFAULT 0, expected_cents INTEGER DEFAULT 0,
    counted_cents INTEGER DEFAULT 0, diff_cents INTEGER DEFAULT 0,
    notes TEXT DEFAULT '', closed_at TEXT
);

CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY, ts TEXT NOT NULL, action TEXT NOT NULL, detail TEXT DEFAULT ''
);
"""

# Añade aquí scripts nuevos (SCHEMA_V2, ...) para evolucionar la base sin perder datos.
MIGRATIONS: list[str] = [SCHEMA_V1]


# --------------------------------------------------------------------------- conexión
@contextmanager
def get_conn(path=None) -> Iterator[sqlite3.Connection]:
    """Conexión con filas tipo dict, claves foráneas y commit/rollback automático."""
    conn = sqlite3.connect(str(path or db_path()), timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def fetch_all(sql: str, params: Iterable[Any] = (), conn: sqlite3.Connection | None = None) -> list[dict]:
    if conn is not None:
        return [dict(r) for r in conn.execute(sql, tuple(params)).fetchall()]
    with get_conn() as c:
        return [dict(r) for r in c.execute(sql, tuple(params)).fetchall()]


def fetch_one(sql: str, params: Iterable[Any] = (), conn: sqlite3.Connection | None = None) -> dict | None:
    rows = fetch_all(sql, params, conn)
    return rows[0] if rows else None


def execute(sql: str, params: Iterable[Any] = (), conn: sqlite3.Connection | None = None) -> int:
    """Ejecuta una escritura y devuelve el ``lastrowid``."""
    if conn is not None:
        return conn.execute(sql, tuple(params)).lastrowid
    with get_conn() as c:
        return c.execute(sql, tuple(params)).lastrowid


def audit(action: str, detail: str = "", conn: sqlite3.Connection | None = None) -> None:
    execute("INSERT INTO audit_log(ts, action, detail) VALUES (?,?,?)", (now().isoformat(timespec="seconds"), action, detail), conn)


# --------------------------------------------------------------------------- init
def init_db() -> None:
    """Crea/actualiza el esquema y siembra los datos iniciales (idempotente)."""
    with get_conn() as conn:
        try:
            conn.execute("PRAGMA journal_mode = WAL")
        except sqlite3.DatabaseError:
            pass
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        for idx, script in enumerate(MIGRATIONS, start=1):
            if idx > version:
                conn.executescript(script)
                conn.execute(f"PRAGMA user_version = {idx}")
        _seed(conn)


def _seed(conn: sqlite3.Connection) -> None:
    for key, value in DEFAULT_SETTINGS.items():
        conn.execute("INSERT OR IGNORE INTO settings(key, value) VALUES (?,?)", (key, value))
    if conn.execute("SELECT COUNT(*) FROM services").fetchone()[0] == 0:
        for i, (name, cat, minutes, price, color, desc) in enumerate(DEFAULT_SERVICES):
            conn.execute(
                "INSERT INTO services(name, category, duration_min, price_cents, vat_rate, color, description, sort)"
                " VALUES (?,?,?,?,21,?,?,?)",
                (name, cat, minutes, price, color, desc, i),
            )
