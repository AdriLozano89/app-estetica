"""Monedero virtual de cada cliente (saldo a favor para futuros servicios).

El saldo es siempre la suma de los movimientos: no se guarda duplicado, así no se desincroniza.
"""
from __future__ import annotations

import sqlite3

from core.config import CASH_IN_METHODS
from core.database import audit, execute, fetch_all, get_conn
from core.utils import now


def _ts() -> str:
    return now().isoformat(timespec="seconds")


def balance(client_id: int, conn: sqlite3.Connection | None = None) -> int:
    rows = fetch_all("SELECT COALESCE(SUM(amount_cents),0) AS s FROM wallet_movements WHERE client_id = ?", (client_id,), conn)
    return int(rows[0]["s"])


def movements(client_id: int) -> list[dict]:
    return fetch_all("SELECT * FROM wallet_movements WHERE client_id = ? ORDER BY ts DESC, id DESC", (client_id,))


def topup(client_id: int, amount_cents: int, method: str, concept: str = "Recarga de monedero") -> int:
    """Recarga con dinero real (efectivo/tarjeta/bizum). Entra en el arqueo del día."""
    if amount_cents <= 0:
        raise ValueError("El importe de la recarga debe ser positivo.")
    if method not in CASH_IN_METHODS:
        raise ValueError("Una recarga solo puede pagarse en efectivo, tarjeta o Bizum.")
    with get_conn() as conn:
        mov_id = execute(
            "INSERT INTO wallet_movements(client_id, ts, amount_cents, concept, method) VALUES (?,?,?,?,?)",
            (client_id, _ts(), amount_cents, concept, method), conn,
        )
        execute(
            "INSERT INTO payments(ts, kind, ref_id, method, amount_cents, client_id, concept) VALUES (?,?,?,?,?,?,?)",
            (_ts(), "wallet_topup", mov_id, method, amount_cents, client_id, concept), conn,
        )
        audit("wallet_topup", f"cliente={client_id} importe={amount_cents} método={method}", conn)
    return mov_id


def adjust(client_id: int, amount_cents: int, concept: str) -> int:
    """Ajuste manual (regalo, corrección). No mueve dinero real, por eso no entra en caja."""
    if amount_cents == 0:
        raise ValueError("El ajuste no puede ser 0.")
    with get_conn() as conn:
        if amount_cents < 0 and balance(client_id, conn) + amount_cents < 0:
            raise ValueError("El ajuste dejaría el saldo en negativo.")
        mov_id = execute(
            "INSERT INTO wallet_movements(client_id, ts, amount_cents, concept, method) VALUES (?,?,?,?,?)",
            (client_id, _ts(), amount_cents, concept or "Ajuste manual", "ajuste"), conn,
        )
        audit("wallet_adjust", f"cliente={client_id} importe={amount_cents} motivo={concept}", conn)
    return mov_id


# ---- operaciones dentro de una transacción ajena (las usa facturación) ----------------------------
def spend_tx(conn: sqlite3.Connection, client_id: int | None, amount_cents: int, concept: str, invoice_id: int) -> None:
    if not client_id:
        raise ValueError("Para pagar con monedero hay que seleccionar un cliente.")
    if balance(client_id, conn) < amount_cents:
        raise ValueError("Saldo insuficiente en el monedero.")
    execute(
        "INSERT INTO wallet_movements(client_id, ts, amount_cents, concept, invoice_id, method) VALUES (?,?,?,?,?,?)",
        (client_id, _ts(), -amount_cents, concept, invoice_id, "monedero"), conn,
    )


def refund_tx(conn: sqlite3.Connection, client_id: int, amount_cents: int, concept: str, invoice_id: int) -> None:
    execute(
        "INSERT INTO wallet_movements(client_id, ts, amount_cents, concept, invoice_id, method) VALUES (?,?,?,?,?,?)",
        (client_id, _ts(), amount_cents, concept, invoice_id, "monedero"), conn,
    )
