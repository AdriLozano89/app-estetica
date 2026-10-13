"""Tarjetas regalo: emisión, saldo, caducidad y canje.

Criterio fiscal aplicado (confírmalo con tu gestor): la venta de la tarjeta se registra como
cobro en caja pero **no** genera factura ni IVA; el IVA se devenga al canjearla, cuando se
factura el servicio (el pago con tarjeta regalo aparece como medio de pago en esa factura).
"""
from __future__ import annotations

import secrets
import sqlite3
from calendar import monthrange
from datetime import date

from core.config import CASH_IN_METHODS, GIFT_ACTIVE, GIFT_EMPTY, GIFT_EXPIRED, GIFT_VOID
from core.database import audit, execute, fetch_all, fetch_one, get_conn
from core.utils import now, parse_date, today
from services import settings

_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # sin I, O, 0, 1 para evitar confusiones


def add_months(d: date, months: int) -> date:
    month_index = d.month - 1 + months
    year, month = d.year + month_index // 12, month_index % 12 + 1
    return date(year, month, min(d.day, monthrange(year, month)[1]))


def _new_code(conn: sqlite3.Connection) -> str:
    while True:
        raw = "".join(secrets.choice(_ALPHABET) for _ in range(8))
        code = f"JD-{raw[:4]}-{raw[4:]}"
        if not fetch_one("SELECT id FROM gift_cards WHERE code = ?", (code,), conn):
            return code


def normalize_code(code: str) -> str:
    return (code or "").strip().upper().replace(" ", "")


def issue(
    amount_cents: int,
    payment_method: str = "efectivo",
    buyer_name: str = "",
    buyer_phone: str = "",
    recipient_name: str = "",
    recipient_phone: str = "",
    message: str = "",
    for_service: str = "",
    validity_months: int | None = None,
) -> dict:
    """Emite una tarjeta regalo y registra el cobro en caja."""
    if amount_cents <= 0:
        raise ValueError("El importe de la tarjeta debe ser positivo.")
    if payment_method not in CASH_IN_METHODS:
        raise ValueError("La tarjeta regalo se paga en efectivo, tarjeta o Bizum.")
    months = validity_months or int(settings.get("gift_validity_months", "12") or 12)
    issued = today()
    expires = add_months(issued, months)
    with get_conn() as conn:
        code = _new_code(conn)
        gid = execute(
            "INSERT INTO gift_cards(code, initial_cents, balance_cents, buyer_name, buyer_phone, recipient_name, recipient_phone,"
            " message, for_service, issued_at, expires_at, status, payment_method) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (code, amount_cents, amount_cents, buyer_name.strip(), buyer_phone.strip(), recipient_name.strip(), recipient_phone.strip(),
             message.strip(), for_service.strip(), issued.isoformat(), expires.isoformat(), GIFT_ACTIVE, payment_method), conn,
        )
        ts = now().isoformat(timespec="seconds")
        execute("INSERT INTO gift_card_movements(gift_card_id, ts, amount_cents, concept) VALUES (?,?,?,?)",
                (gid, ts, amount_cents, "Emisión de la tarjeta"), conn)
        execute("INSERT INTO payments(ts, kind, ref_id, method, amount_cents, concept) VALUES (?,?,?,?,?,?)",
                (ts, "giftcard_sale", gid, payment_method, amount_cents, f"Venta tarjeta regalo {code}"), conn)
        audit("giftcard_issue", f"{code} importe={amount_cents}", conn)
    return get(gid)  # type: ignore[return-value]


def get(gift_id: int) -> dict | None:
    return fetch_one("SELECT * FROM gift_cards WHERE id = ?", (gift_id,))


def get_by_code(code: str, conn: sqlite3.Connection | None = None) -> dict | None:
    return fetch_one("SELECT * FROM gift_cards WHERE code = ?", (normalize_code(code),), conn)


def effective_status(card: dict) -> str:
    """Estado real teniendo en cuenta la caducidad (sin tocar la base de datos)."""
    if card["status"] == GIFT_ACTIVE:
        exp = parse_date(card["expires_at"])
        if exp and exp < today():
            return GIFT_EXPIRED
    return card["status"]


def list_cards(status: str | None = None, text: str = "") -> list[dict]:
    cards = fetch_all("SELECT * FROM gift_cards ORDER BY issued_at DESC, id DESC")
    out = []
    needle = (text or "").strip().lower()
    for c in cards:
        c["effective_status"] = effective_status(c)
        if status and status != "todas" and c["effective_status"] != status:
            continue
        if needle and needle not in " ".join(str(c[k]).lower() for k in ("code", "buyer_name", "recipient_name")):
            continue
        out.append(c)
    return out


def movements(gift_id: int) -> list[dict]:
    return fetch_all("SELECT * FROM gift_card_movements WHERE gift_card_id = ? ORDER BY ts, id", (gift_id,))


def outstanding_cents() -> int:
    """Saldo total pendiente de consumir en tarjetas vigentes (pasivo del centro)."""
    return sum(c["balance_cents"] for c in list_cards() if c["effective_status"] == GIFT_ACTIVE)


def expiring_soon(days: int = 30) -> list[dict]:
    limit = today().toordinal() + days
    out = []
    for c in list_cards(GIFT_ACTIVE):
        exp = parse_date(c["expires_at"])
        if exp and today().toordinal() <= exp.toordinal() <= limit and c["balance_cents"] > 0:
            out.append(c)
    return sorted(out, key=lambda c: c["expires_at"])


# ---- operaciones dentro de una transacción ajena (facturación) --------------------------------------
def redeem_tx(conn: sqlite3.Connection, code: str, amount_cents: int, concept: str, invoice_id: int) -> dict:
    card = get_by_code(code, conn)
    if not card:
        raise ValueError(f"No existe la tarjeta regalo «{code}».")
    status = effective_status(card)
    if status != GIFT_ACTIVE:
        raise ValueError(f"La tarjeta {card['code']} no está disponible ({status}).")
    if card["balance_cents"] < amount_cents:
        raise ValueError(f"Saldo insuficiente en la tarjeta {card['code']}.")
    new_balance = card["balance_cents"] - amount_cents
    execute("UPDATE gift_cards SET balance_cents = ?, status = ? WHERE id = ?",
            (new_balance, GIFT_EMPTY if new_balance == 0 else GIFT_ACTIVE, card["id"]), conn)
    execute("INSERT INTO gift_card_movements(gift_card_id, ts, amount_cents, concept, invoice_id) VALUES (?,?,?,?,?)",
            (card["id"], now().isoformat(timespec="seconds"), -amount_cents, concept, invoice_id), conn)
    return card


def restore_tx(conn: sqlite3.Connection, gift_id: int, amount_cents: int, concept: str, invoice_id: int) -> None:
    card = fetch_one("SELECT * FROM gift_cards WHERE id = ?", (gift_id,), conn)
    if not card or card["status"] == GIFT_VOID:
        return
    execute("UPDATE gift_cards SET balance_cents = balance_cents + ?, status = ? WHERE id = ?",
            (amount_cents, GIFT_ACTIVE, gift_id), conn)
    execute("INSERT INTO gift_card_movements(gift_card_id, ts, amount_cents, concept, invoice_id) VALUES (?,?,?,?,?)",
            (gift_id, now().isoformat(timespec="seconds"), amount_cents, concept, invoice_id), conn)


def void(gift_id: int, refund_method: str | None = None) -> None:
    """Anula una tarjeta. Si se indica método, devuelve el saldo restante al comprador."""
    with get_conn() as conn:
        card = fetch_one("SELECT * FROM gift_cards WHERE id = ?", (gift_id,), conn)
        if not card or card["status"] == GIFT_VOID:
            raise ValueError("Tarjeta no encontrada o ya anulada.")
        ts = now().isoformat(timespec="seconds")
        remaining = card["balance_cents"]
        if remaining > 0:
            execute("INSERT INTO gift_card_movements(gift_card_id, ts, amount_cents, concept) VALUES (?,?,?,?)",
                    (gift_id, ts, -remaining, "Anulación de la tarjeta"), conn)
            if refund_method:
                if refund_method not in CASH_IN_METHODS:
                    raise ValueError("La devolución se hace en efectivo, tarjeta o Bizum.")
                execute("INSERT INTO payments(ts, kind, ref_id, method, amount_cents, concept) VALUES (?,?,?,?,?,?)",
                        (ts, "giftcard_refund", gift_id, refund_method, -remaining, f"Devolución tarjeta regalo {card['code']}"), conn)
        execute("UPDATE gift_cards SET status = ?, balance_cents = 0 WHERE id = ?", (GIFT_VOID, gift_id), conn)
        audit("giftcard_void", f"{card['code']} devuelto={remaining if refund_method else 0}", conn)
