"""Autenticación: contraseña de acceso con PBKDF2 (o secreto de despliegue) y límite de intentos."""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import time

from core.database import execute, fetch_one
from core.utils import now

PBKDF2_ITERATIONS = 240_000
MAX_ATTEMPTS = 5
LOCK_SECONDS = 60


def _hash(password: str, salt: bytes) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS).hex()


def deployment_password() -> str | None:
    """Contraseña definida fuera de la base de datos (recomendado en la nube).

    Se busca en ``st.secrets["APP_PASSWORD"]`` y, si no, en la variable ``JD_APP_PASSWORD``.
    """
    try:
        import streamlit as st

        value = st.secrets.get("APP_PASSWORD")
        if value:
            return str(value)
    except Exception:  # sin archivo de secretos o fuera de Streamlit
        pass
    return os.environ.get("JD_APP_PASSWORD") or None


def has_db_password() -> bool:
    return fetch_one("SELECT id FROM users LIMIT 1") is not None


def needs_setup() -> bool:
    """True si todavía no hay ninguna contraseña configurada (ni secreto ni base de datos)."""
    return deployment_password() is None and not has_db_password()


def set_password(password: str, username: str = "admin") -> None:
    salt = secrets.token_bytes(16)
    execute("DELETE FROM users WHERE username = ?", (username,))
    execute(
        "INSERT INTO users(username, salt, pw_hash, created_at) VALUES (?,?,?,?)",
        (username, salt.hex(), _hash(password, salt), now().isoformat(timespec="seconds")),
    )


def verify_password(password: str, username: str = "admin") -> bool:
    secret = deployment_password()
    if secret is not None:
        return hmac.compare_digest(password.encode("utf-8"), secret.encode("utf-8"))
    row = fetch_one("SELECT salt, pw_hash FROM users WHERE username = ?", (username,))
    if not row:
        return False
    return hmac.compare_digest(_hash(password, bytes.fromhex(row["salt"])), row["pw_hash"])


def password_strength_error(password: str) -> str | None:
    if len(password) < 8:
        return "La contraseña debe tener al menos 8 caracteres."
    if password.lower() == password or not any(c.isdigit() for c in password):
        return "Usa mayúsculas, minúsculas y al menos un número."
    return None


def throttle_state(store: dict) -> tuple[bool, int]:
    """(bloqueado, segundos_restantes) según el contador guardado en la sesión."""
    until = store.get("lock_until", 0)
    remaining = int(until - time.time())
    return remaining > 0, max(remaining, 0)


def register_attempt(store: dict, ok: bool) -> None:
    if ok:
        store["fails"] = 0
        store["lock_until"] = 0
        return
    store["fails"] = store.get("fails", 0) + 1
    if store["fails"] >= MAX_ATTEMPTS:
        store["lock_until"] = time.time() + LOCK_SECONDS
        store["fails"] = 0
