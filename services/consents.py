"""RGPD y consentimientos informados con firma: textos, registro con huella y estado por cliente.

Los textos son plantillas razonables, no asesoramiento jurídico: revísalas con tu asesoría
antes de usarlas con clientas.
"""
from __future__ import annotations

import hashlib

from core.database import audit, execute, fetch_all, fetch_one, get_conn
from core.utils import fmt_date, now
from services import settings
from services.knowledge import treatment_for_service

TEXT_VERSION = "2026-1"
KIND_RGPD = "rgpd"
KIND_TREATMENT = "tratamiento"


def rgpd_text() -> str:
    cfg = settings.all_settings()
    owner = cfg["legal_name"] or cfg["business_name"]
    nif = f" (NIF {cfg['nif']})" if cfg["nif"] else ""
    contact = ", ".join(x for x in (cfg["address"], cfg["email"], cfg["phone"]) if x) or "los datos de contacto del centro"
    return (
        "INFORMACIÓN SOBRE PROTECCIÓN DE DATOS Y CONSENTIMIENTO\n\n"
        f"Responsable del tratamiento: {owner}{nif}. Contacto: {contact}.\n\n"
        "Finalidad: gestionar tus citas, tu historial de tratamientos y su seguimiento, la facturación y la comunicación "
        "relacionada con tus servicios (recordatorios de cita, por ejemplo por WhatsApp o SMS).\n\n"
        "Base jurídica: la ejecución del servicio que solicitas, el cumplimiento de obligaciones legales (fiscales y contables) y "
        "tu consentimiento explícito para los datos de salud que facilites (alergias, medicación, patologías) y que son necesarios "
        "para realizar los tratamientos con seguridad.\n\n"
        "Destinatarios: no cedemos tus datos a terceros salvo obligación legal (por ejemplo, Administración Tributaria) o proveedores "
        "que nos prestan servicios necesarios (gestoría, alojamiento del software) con contrato de encargado de tratamiento.\n\n"
        "Conservación: mientras dure la relación y, después, durante los plazos exigidos por la ley.\n\n"
        "Derechos: puedes ejercer los derechos de acceso, rectificación, supresión, oposición, limitación y portabilidad, y retirar "
        "tu consentimiento en cualquier momento, escribiendo al contacto indicado. También puedes reclamar ante la Agencia Española "
        "de Protección de Datos (aepd.es).\n\n"
        "Declaro que he leído y comprendido esta información y consiento el tratamiento de mis datos, incluidos los de salud, para "
        "las finalidades descritas."
    )


MARKETING_TEXT = (
    "Autorizo además que el centro me envíe comunicaciones comerciales y felicitaciones (por ejemplo, por WhatsApp o correo "
    "electrónico) sobre sus servicios y promociones. Puedo retirar esta autorización cuando quiera."
)


def treatment_consent_text(treatment_name: str) -> str:
    t = treatment_for_service(treatment_name)
    cfg = settings.all_settings()

    def bullets(items) -> str:
        return "\n".join(f"  • {i}" for i in items) or "  • Ninguno indicado"

    return (
        f"CONSENTIMIENTO INFORMADO — {treatment_name.upper() or t.name.upper()}\n\n"
        f"Centro: {cfg['business_name']}.\n\n"
        f"En qué consiste: {t.summary}\n"
        f"Duración aproximada: {t.duration}.\n\n"
        f"Contraindicaciones y precauciones (avisa a la profesional si te afecta alguna):\n{bullets(t.contraindications)}\n\n"
        f"Efectos esperables:\n{bullets(t.effects)}\n\n"
        f"Cuidados posteriores recomendados:\n{bullets(t.aftercare)}\n\n"
        "Declaración: he informado a la profesional de mi estado de salud, alergias, medicación y posible embarazo, y confirmo que "
        "los datos que he facilitado son veraces. He recibido explicación del tratamiento, de sus posibles efectos y de los cuidados "
        "posteriores, he podido hacer preguntas y consiento su realización. Entiendo que los resultados varían entre personas y que "
        "este servicio es estético y no sustituye a una consulta médica."
    )


def _doc_hash(client_id: int, text: str, signed_name: str, signed_at: str, signature: bytes | None) -> str:
    sig = hashlib.sha256(signature).hexdigest() if signature else ""
    raw = f"{client_id}|{text}|{signed_name}|{signed_at}|{sig}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest().upper()


def save_consent(client_id: int, kind: str, signed_name: str, signature_png: bytes | None, treatment: str = "",
                 marketing: bool | None = None) -> int:
    """Registra un consentimiento firmado (guarda el texto exacto firmado, la firma y una huella)."""
    if kind not in (KIND_RGPD, KIND_TREATMENT):
        raise ValueError("Tipo de consentimiento no válido.")
    if not (signed_name or "").strip():
        raise ValueError("Escribe el nombre completo de quien firma.")
    text = rgpd_text() if kind == KIND_RGPD else treatment_consent_text(treatment)
    if kind == KIND_RGPD and marketing:
        text += "\n\n" + MARKETING_TEXT
    signed_at = now().isoformat(timespec="seconds")
    digest = _doc_hash(client_id, text, signed_name.strip(), signed_at, signature_png)
    with get_conn() as conn:
        cid = execute(
            "INSERT INTO consents(client_id, kind, treatment, text_version, text_body, signed_name, signed_at, signature_png, doc_hash)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            (client_id, kind, treatment, TEXT_VERSION, text, signed_name.strip(), signed_at, signature_png, digest), conn,
        )
        if kind == KIND_RGPD:
            execute("UPDATE clients SET rgpd_signed = 1, marketing_consent = ? WHERE id = ?", (1 if marketing else 0, client_id), conn)
        audit("consent_sign", f"cliente={client_id} tipo={kind} {treatment}", conn)
    return cid


def list_consents(client_id: int) -> list[dict]:
    return fetch_all(
        "SELECT id, kind, treatment, text_version, signed_name, signed_at, doc_hash, revoked FROM consents "
        "WHERE client_id = ? ORDER BY signed_at DESC", (client_id,),
    )


def get_consent(consent_id: int) -> dict | None:
    return fetch_one("SELECT * FROM consents WHERE id = ?", (consent_id,))


def revoke(consent_id: int) -> None:
    c = get_consent(consent_id)
    if not c:
        raise ValueError("Consentimiento no encontrado.")
    execute("UPDATE consents SET revoked = 1 WHERE id = ?", (consent_id,))
    if c["kind"] == KIND_RGPD:
        still = fetch_one("SELECT id FROM consents WHERE client_id = ? AND kind = 'rgpd' AND revoked = 0", (c["client_id"],))
        if not still:
            execute("UPDATE clients SET rgpd_signed = 0, marketing_consent = 0 WHERE id = ?", (c["client_id"],))
    audit("consent_revoke", f"id={consent_id}")


def verify_consent(consent_id: int) -> bool:
    """Comprueba que el documento firmado no se ha alterado desde que se guardó."""
    c = get_consent(consent_id)
    if not c:
        return False
    return _doc_hash(c["client_id"], c["text_body"], c["signed_name"], c["signed_at"], c["signature_png"]) == c["doc_hash"]


def status_for_client(client_id: int) -> dict:
    rows = [c for c in list_consents(client_id) if not c["revoked"]]
    return {
        "rgpd": any(c["kind"] == KIND_RGPD for c in rows),
        "treatments": sorted({c["treatment"] for c in rows if c["kind"] == KIND_TREATMENT}),
    }


def missing_rgpd() -> list[dict]:
    return fetch_all(
        "SELECT id, first_name, last_name, phone FROM clients WHERE active = 1 AND anonymized = 0 AND rgpd_signed = 0 "
        "ORDER BY first_name COLLATE NOCASE"
    )


def valid_today_label(consent: dict) -> str:
    return f"{fmt_date(consent['signed_at'])} · v{consent['text_version']}" + (" · revocado" if consent["revoked"] else "")
