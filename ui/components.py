"""Componentes de interfaz reutilizables (todo texto de usuario se escapa antes de ir a HTML)."""
from __future__ import annotations

from html import escape
from typing import Iterable

import streamlit as st

from core.config import PAYMENT_ICONS, PAYMENT_LABELS, STATUS_CANCELLED, STATUS_CONFIRMED, STATUS_DONE, STATUS_LABELS, STATUS_NOSHOW
from core.utils import fmt_eur, fmt_time, to_cents
from services import clients as clients_svc


def esc(value) -> str:
    return escape(str(value if value is not None else ""))


def html(markup: str) -> None:
    st.markdown(markup, unsafe_allow_html=True)


# --------------------------------------------------------------------------- estructura
def page_header(title: str, subtitle: str = "") -> None:
    html(f'<div class="jd-title">{esc(title)}</div>' + (f'<div class="jd-sub">{esc(subtitle)}</div>' if subtitle else ""))


def section(title: str, subtitle: str = "") -> None:
    html(f'<div style="margin:1.1rem 0 .4rem"><div style="font-family:var(--font-title);font-size:1.5rem;font-weight:600;color:var(--text)">{esc(title)}</div>'
         + (f'<div class="jd-muted" style="font-size:.9rem">{esc(subtitle)}</div>' if subtitle else "") + "</div>")


def kpi_grid(items: Iterable[tuple[str, str, str]]) -> None:
    """Tarjetas de cifras en una rejilla que se adapta sola (2 columnas en móvil, más en pantallas grandes)."""
    cards = "".join(
        f'<div class="jd-kpi"><div class="jd-kpi-label">{esc(label)}</div><div class="jd-kpi-value">{esc(value)}</div>'
        + (f'<div class="jd-kpi-hint">{esc(hint)}</div>' if hint else "") + "</div>"
        for label, value, hint in items
    )
    html(f'<div class="jd-kpis">{cards}</div>')


def empty_state(message: str, icon: str = "🌿") -> None:
    html(f'<div class="jd-empty"><span class="ico">{icon}</span>{esc(message)}</div>')


def badge(text: str, kind: str = "") -> str:
    return f'<span class="jd-badge {kind}">{esc(text)}</span>'


def status_badge(status: str, paid: bool = False) -> str:
    if paid:
        return badge("Cobrada", "ok")
    kind = {STATUS_CONFIRMED: "gold", STATUS_DONE: "warn", STATUS_CANCELLED: "bad", STATUS_NOSHOW: "bad"}.get(status, "")
    label = "Pendiente de cobro" if status == STATUS_DONE else STATUS_LABELS.get(status, status)
    return badge(label, kind)


def appointment_card(a: dict) -> str:
    """Tarjeta HTML de una cita (hora grande, clienta, servicio, estado)."""
    allergy = ' <span title="Alergias o notas médicas">⚠️</span>' if (a.get("allergies") or "").strip() else ""
    return (
        f'<div class="jd-appt" style="border-left-color:{esc(a["color"])}">'
        f'<div class="jd-appt-time">{fmt_time(a["start_ts"])}</div>'
        f'<div class="jd-appt-main"><div class="jd-appt-name">{esc(a["client_name"])}{allergy}</div>'
        f'<div class="jd-appt-meta">{esc(a["service_name"])} · {fmt_eur(a["price_cents"])}</div></div>'
        f'<div>{status_badge(a["status"], a["paid"])}</div></div>'
    )


def legend(services: list[dict]) -> None:
    seen, items = set(), []
    for s in services:
        if s["category"] in seen:
            continue
        seen.add(s["category"])
        items.append(f'<span><span class="jd-dot" style="background:{esc(s["color"])}"></span>{esc(s["category"])}</span>')
    items.append('<span>✓ cobrada</span><span>● confirmada</span><span>€ pendiente de cobro</span>')
    html(f'<div class="jd-legend">{"".join(items)}</div>')


def payment_label(method: str) -> str:
    return f"{PAYMENT_ICONS.get(method, '')} {PAYMENT_LABELS.get(method, method)}".strip()


# --------------------------------------------------------------------------- entradas
def money_input(label: str, value_cents: int = 0, key: str | None = None, min_cents: int = 0, max_cents: int | None = None,
                help: str | None = None) -> int:
    """Campo de importe en euros que devuelve céntimos enteros."""
    if max_cents is not None and max_cents <= 0:  # nada que elegir (p. ej. monedero sin saldo)
        st.caption(f"{label}: no disponible")
        return 0
    value = st.number_input(
        label, min_value=min_cents / 100, max_value=(max_cents / 100) if max_cents is not None else None,
        value=max(value_cents, min_cents) / 100, step=1.0, format="%.2f", key=key, help=help,
    )
    return to_cents(value)


def client_label(c: dict) -> str:
    name = clients_svc.full_name(c)
    return f"{name} · {c['phone']}" if c.get("phone") else name


def client_picker(label: str, key: str, default_id: int | None = None, allow_none: bool = True,
                  none_label: str = "— Sin clienta (venta rápida) —") -> int | None:
    """Selector de clienta con búsqueda al escribir. Devuelve su id (o None)."""
    rows = clients_svc.search_clients()
    ids = [r["id"] for r in rows]
    names = {r["id"]: client_label(r) for r in rows}
    options: list[int | None] = ([None] if allow_none else []) + ids
    if default_id and default_id not in ids:  # clienta inactiva/anonimizada: no se puede elegir
        default_id = None
    index = options.index(default_id) if default_id in options else 0
    return st.selectbox(label, options, index=index, key=key, format_func=lambda i: none_label if i is None else names.get(i, "—"))


def whatsapp_button(label: str, url: str, key: str | None = None, primary: bool = False, full_width: bool = True) -> None:
    """Botón que abre WhatsApp con el mensaje escrito. Si no hay teléfono válido queda desactivado."""
    if url:
        st.link_button(label, url, type="primary" if primary else "secondary", use_container_width=full_width)
    else:
        st.button(label, disabled=True, key=key or f"wa_disabled_{label}", use_container_width=full_width, help="La clienta no tiene un teléfono válido.")


def goto(page: str, **state) -> None:
    """Pide cambiar de sección en la siguiente ejecución (y guarda datos de contexto)."""
    st.session_state["_goto"] = page
    for k, v in state.items():
        st.session_state[k] = v
    st.rerun()


def choice(label: str, options: list, key: str, default=None, format_func=None):
    """Selector de una opción tipo «pastillas» (segmented control); en versiones antiguas usa radio horizontal.

    Nunca devuelve None: si la usuaria desmarca, se conserva la última opción.
    """
    default = options[0] if default is None else default
    fmt = format_func or (lambda x: x)
    try:
        value = st.segmented_control(label, options, selection_mode="single", default=None if key in st.session_state else default,
                                     key=key, format_func=fmt, label_visibility="collapsed")
    except AttributeError:
        value = st.radio(label, options, horizontal=True, key=key, format_func=fmt, label_visibility="collapsed",
                         index=options.index(default) if key not in st.session_state else None)
    memo = f"_{key}_last"
    if value is None:
        return st.session_state.get(memo, default)
    st.session_state[memo] = value
    return value


def html_table(headers: list[str], rows: list[list], right: set[int] | None = None, bold_last: bool = False) -> None:
    """Tabla HTML sencilla con el estilo de la casa (las celdas se escapan; usa str ya formateados)."""
    right = right or set()
    head = "".join(f'<th class="{"r" if i in right else ""}">{esc(h)}</th>' for i, h in enumerate(headers))
    body = ""
    for n, row in enumerate(rows):
        strong = bold_last and n == len(rows) - 1
        cells = "".join(
            f'<td class="{"r" if i in right else ""}">' + (f"<b>{esc(c)}</b>" if strong else esc(c)) + "</td>" for i, c in enumerate(row)
        )
        body += f"<tr>{cells}</tr>"
    html(f'<div class="jd-card" style="padding:.5rem .8rem"><table class="jd-lines"><tr>{head}</tr>{body}</table></div>')
