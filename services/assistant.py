"""Asistente virtual del centro: responde sobre tratamientos, uso del software, cobros y datos del día.

Funciona sin servicios externos (reglas + base de conocimiento + consultas a la base de datos), así que es
gratuito, rápido y no envía datos de clientes fuera. ``answer()`` es el único punto de entrada: si algún día
quieres conectar un modelo de lenguaje, solo hay que añadir una llamada en la rama de respaldo (``_fallback``).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta

from core.utils import fmt_date, fmt_eur, fmt_time, norm, today
from services import appointments, cashbox, clients, giftcards, wallet
from services.catalog import list_services
from services.knowledge import Treatment, find_treatment

WELCOME_SUGGESTIONS = [
    "¿Qué citas hay hoy?",
    "¿Cuánto llevamos cobrado hoy?",
    "¿En qué consiste la maderoterapia?",
    "¿Cómo cobro con pago mixto?",
]


@dataclass
class Reply:
    text: str
    suggestions: list[str] = field(default_factory=list)


def welcome() -> Reply:
    return Reply(
        "¡Hola! 👋 Soy el asistente del centro. Puedo ayudarte con **tratamientos** (qué son, contraindicaciones, cuidados), "
        "con **el uso de la aplicación** (citas, cobros, tarjetas regalo, caja) y consultar **datos del día** (agenda, caja, cumpleaños).",
        WELCOME_SUGGESTIONS,
    )


# --------------------------------------------------------------------------- ayuda del software y cobros
HELP_TOPICS: list[dict] = [
    {
        "keys": ("nueva cita", "crear cita", "agendar", "apuntar cita", "reservar", "dar cita", "pedir cita"),
        "text": "**Crear una cita**\n- En **Agenda** pulsa **➕ Nueva cita**, o toca un hueco libre del calendario (la fecha y hora se rellenan solas).\n"
                "- Elige la clienta (o crea una nueva ahí mismo), el servicio y la hora. La duración y el precio salen del servicio, pero puedes cambiarlos.\n"
                "- Si se solapa con otra cita, la app te avisa antes de guardar.",
        "suggestions": ["¿Cómo muevo una cita?", "¿Cómo envío un recordatorio por WhatsApp?"],
    },
    {
        "keys": ("mover cita", "muevo cita", "mueve cita", "cambiar cita", "cambiar hora", "arrastrar", "editar cita", "modificar cita", "cambiar de dia"),
        "text": "**Cambiar una cita**\n- Arrastra la cita a otro hueco del calendario (o estira el borde inferior para cambiar la duración).\n"
                "- También puedes tocarla y elegir **Editar**. Las citas ya cobradas no se pueden mover.",
        "suggestions": ["¿Cómo cancelo una cita?"],
    },
    {
        "keys": ("cancelar cita", "anular cita", "borrar cita", "no se presento", "no show", "no vino", "no ha venido"),
        "text": "**Cancelar o marcar ausencia**\n- Toca la cita en la agenda y elige **Cancelar** (si avisó) o **No se presentó**. "
                "Queda registrado para las estadísticas pero libera el hueco.",
        "suggestions": ["¿Cómo cobro una cita?"],
    },
    {
        "keys": ("cobrar", "cobrar cita", "ticket", "factura simplificada", "emitir factura", "hacer factura"),
        "text": "**Cobrar**\n- Toca la cita y pulsa **💶 Cobrar**; también puedes hacer una **venta rápida** desde **Caja**.\n"
                "- Revisa los conceptos (puedes añadir productos o aplicar un descuento), elige el método de pago y confirma.\n"
                "- Se genera una **factura simplificada** numerada y encadenada. Puedes descargar el PDF o enviar el ticket por WhatsApp.",
        "suggestions": ["¿Cómo cobro con pago mixto?", "¿Cómo anulo una factura?"],
    },
    {
        "keys": ("pago mixto", "mixto", "dividir pago", "pagar mitad", "varios metodos", "combinar pagos", "parte en efectivo", "parte con tarjeta"),
        "text": "**Pago mixto**\n- En el cobro elige **Mixto** y reparte el importe entre efectivo, tarjeta, Bizum, monedero y/o tarjeta regalo.\n"
                "- La suma debe coincidir con el total. Para tarjeta regalo escribe su código; verás el saldo disponible.",
        "suggestions": ["¿Qué diferencia hay entre monedero y tarjeta regalo?"],
    },
    {
        "keys": ("metodos de pago", "formas de pago", "como pagan", "aceptamos", "bizum", "efectivo"),
        "text": "**Métodos de pago** disponibles: efectivo, tarjeta, Bizum, monedero virtual y tarjeta regalo. "
                "Efectivo, tarjeta y Bizum son dinero que entra; monedero y tarjeta regalo se descuentan de un saldo ya cobrado antes.",
        "suggestions": ["¿Qué diferencia hay entre monedero y tarjeta regalo?"],
    },
    {
        "keys": ("diferencia monedero", "monedero y tarjeta regalo", "que es el monedero", "monedero virtual", "recargar monedero", "recarga"),
        "text": "**Monedero vs tarjeta regalo**\n- **Monedero**: saldo a favor *de una clienta* (por ejemplo, una recarga). Se gestiona en su ficha → **Monedero**.\n"
                "- **Tarjeta regalo**: documento con código que se vende a quien regala y la usa otra persona; tiene caducidad. Se crea en **Marketing → Tarjetas regalo**.\n"
                "Ambos se pueden usar como método de pago al cobrar.",
        "suggestions": ["¿Cómo creo una tarjeta regalo?"],
    },
    {
        "keys": ("crear tarjeta regalo", "tarjeta regalo", "vender tarjeta", "regalo", "bono regalo", "generar tarjeta"),
        "text": "**Tarjeta regalo**\n- Ve a **Marketing → Tarjetas regalo**, indica importe, quién la compra y para quién, un mensaje y el método de pago.\n"
                "- Se genera una imagen elegante con el logo que puedes **descargar en PNG** o enviar por **WhatsApp**. Caduca a los 12 meses por defecto (se cambia en Ajustes).\n"
                "- Para canjearla, al cobrar elige *Tarjeta regalo* y escribe el código.",
        "suggestions": ["¿Qué tarjetas regalo caducan pronto?"],
    },
    {
        "keys": ("recordatorio", "whatsapp", "avisar clienta", "mensaje cita", "recordar cita"),
        "text": "**Recordatorios por WhatsApp**\n- En **Agenda**, la sección *Recordatorios de mañana* muestra cada cita con un botón 💬 que abre WhatsApp con el mensaje ya escrito.\n"
                "- También aparece en el detalle de cada cita. El texto se personaliza en **Marketing → Plantillas**.",
        "suggestions": ["¿Qué citas hay mañana?"],
    },
    {
        "keys": ("cierre de caja", "arqueo", "cerrar caja", "cuadrar caja", "cuadre", "descuadre", "contar caja"),
        "text": "**Cierre de caja**\n- En **Caja → Caja del día** ves lo cobrado por método. Indica el fondo con el que empezaste y el efectivo que cuentas ahora.\n"
                "- La app calcula el efectivo esperado (fondo + cobros en efectivo − gastos en efectivo) y te muestra la diferencia. Pulsa **Cerrar caja** para guardarlo.",
        "suggestions": ["¿Cuánto llevamos cobrado hoy?"],
    },
    {
        "keys": ("anular factura", "me equivoque cobrar", "borrar factura", "rectificar", "rectificativa", "error factura", "equivoque", "devolver", "devolucion", "factura mal"),
        "text": "**Corregir una factura**\n- Las facturas emitidas no se borran ni se editan (es un requisito legal). En **Caja → Facturas** elige la factura y pulsa **Anular (rectificativa)**.\n"
                "- Se crea una factura rectificativa por el importe contrario, se devuelve el cobro y la cita vuelve a quedar pendiente. Después puedes cobrar de nuevo correctamente.",
        "suggestions": ["¿Qué es la huella SHA-256?"],
    },
    {
        "keys": ("huella", "sha", "verifactu", "veri factu", "encadenado", "cadena", "integridad"),
        "text": "**Huella y encadenado**\n- Cada factura guarda una huella SHA-256 calculada con sus datos y con la huella de la anterior; así cualquier alteración se detecta.\n"
                "- En **Analítica y Legal → Legal** puedes verificar la cadena completa. Está *preparada* para Veri*Factu, pero el envío a Hacienda y la declaración del software los debe confirmar tu gestoría.",
        "suggestions": ["¿Cómo veo el IVA del trimestre?"],
    },
    {
        "keys": ("iva", "modelo 303", "303", "modelo 130", "130", "irpf", "impuestos", "trimestre", "gestoria"),
        "text": "**Impuestos**\n- En **Caja → Impuestos** eliges año y trimestre y ves la estimación del **Modelo 303** (IVA devengado − soportado) y del **Modelo 130** (20 % del rendimiento neto acumulado).\n"
                "- Para que sea fiable, registra todos los gastos en **Caja → Gastos**. Puedes descargar un ZIP con los libros para tu gestoría. Son cifras orientativas.",
        "suggestions": ["¿Cómo registro un gasto?"],
    },
    {
        "keys": ("registrar gasto", "anotar gasto", "gasto", "compra de producto", "proveedor", "factura proveedor"),
        "text": "**Gastos**\n- **Caja → Gastos → Nuevo gasto**: concepto, proveedor, total pagado, tipo de IVA y cómo se pagó. La app separa base e IVA.\n"
                "- Si pagas en efectivo desde la caja, se descuenta del efectivo esperado en el cierre.",
        "suggestions": ["¿Cómo veo el IVA del trimestre?"],
    },
    {
        "keys": ("nueva clienta", "nuevo cliente", "dar de alta", "alta cliente", "ficha cliente", "ficha de clienta", "importar clientes", "csv"),
        "text": "**Clientas**\n- En **Clientes** pulsa **➕ Nueva clienta**. En su ficha tienes historial de tratamientos, notas técnicas y médicas, alergias, monedero y consentimientos.\n"
                "- Para traer tu lista actual: **Ajustes → Copias e importación → Importar clientes (CSV/Excel)**.",
        "suggestions": ["¿Cómo se firma el RGPD?"],
    },
    {
        "keys": ("rgpd", "proteccion de datos", "firma", "firmar", "consentimiento", "consentimientos", "lopd"),
        "text": "**Firma y RGPD**\n- En la ficha de la clienta → **Consentimientos**: elige *Protección de datos* o *Consentimiento informado* del tratamiento.\n"
                "- La clienta firma con el dedo en la pantalla (o escribes su nombre). Se guarda con fecha y huella y puedes descargar el PDF firmado.\n"
                "- En **Analítica y Legal → RGPD** ves quién aún no ha firmado.",
        "suggestions": ["¿Quién no ha firmado el RGPD?"],
    },
    {
        "keys": ("cambiar precio", "precios", "servicios", "nuevo servicio", "tarifas", "editar servicio", "catalogo"),
        "text": "**Servicios y precios**\n- En **Ajustes → Servicios** puedes añadir, editar o desactivar tratamientos: nombre, categoría, duración, precio (IVA incluido), tipo de IVA y color en la agenda.",
        "suggestions": ["¿Cómo cambio el horario?"],
    },
    {
        "keys": ("horario", "dias de apertura", "abrimos", "hora de apertura", "domingo"),
        "text": "**Horario de la agenda**\n- En **Ajustes → Horario** eliges los días de apertura, la hora de apertura y cierre y el intervalo de la agenda.",
        "suggestions": [],
    },
    {
        "keys": ("copia de seguridad", "backup", "perder datos", "restaurar", "exportar datos", "descargar datos", "respaldo"),
        "text": "**Copias de seguridad**\n- En **Ajustes → Copias** descargas toda la base de datos y puedes restaurarla. Hazlo con regularidad, sobre todo si la app está en un servicio gratuito cuyo disco se reinicia.",
        "suggestions": [],
    },
    {
        "keys": ("contrasena", "cambiar contrasena", "password", "acceso", "salir", "seguridad"),
        "text": "**Acceso**\n- La contraseña se cambia en **Ajustes → Seguridad** (o, si el administrador la definió como secreto del servidor, desde allí). Usa **Salir** arriba a la derecha al terminar.",
        "suggestions": [],
    },
]


def _stem(word: str) -> str:
    """Raíz muy simple (4 letras) para casar «cobro/cobrar/cobrado» o «anulo/anular»."""
    return word[:4] if len(word) >= 5 else word


def _score(question_norm: str, keys: tuple[str, ...]) -> int:
    """Suma puntos por cada expresión clave cuyas raíces aparecen todas en la pregunta (en cualquier orden)."""
    stems = {_stem(w) for w in question_norm.split()}
    score = 0
    for k in keys:
        parts = [_stem(w) for w in norm(k).split()]
        if parts and all(p in stems for p in parts):
            score += 1 + 2 * len(parts)
    return score


# --------------------------------------------------------------------------- tratamientos
def _services_for(t: Treatment) -> str:
    items = [s for s in list_services() if (find_treatment(s["name"]) or t).key == t.key and find_treatment(s["name"])]
    if not items:
        return ""
    return "\n".join(f"- {s['name']}: **{fmt_eur(s['price_cents'])}** · {s['duration_min']} min" for s in items)


def _bullets(items) -> str:
    return "\n".join(f"- {i}" for i in items)


def _treatment_reply(t: Treatment, q: str) -> Reply:
    tail = [f"¿Qué cuidados requiere {t.name.lower()}?", f"¿Qué contraindicaciones tiene {t.name.lower()}?"]
    if any(w in q for w in ("contraindic", "no puedo", "no se puede", "embaraz", "quien no", "riesgo", "precauc", "puede hacerse")):
        return Reply(f"**{t.name}: contraindicaciones y precauciones**\n{_bullets(t.contraindications)}\n\n"
                     "Ante cualquier duda de salud, recomendamos consultar con su médico antes del tratamiento.", tail[:1])
    if any(w in q for w in ("despues", "cuidados", "post", "recomendac", "tras el", "tras la", "que hago")):
        return Reply(f"**{t.name}: cuidados posteriores**\n{_bullets(t.aftercare)}", [tail[1]])
    if any(w in q for w in ("cuanto dura", "duracion", "tiempo", "cuanto tarda", "minutos", "horas")):
        return Reply(f"**{t.name}**: dura aproximadamente **{t.duration}**.", [f"¿Cada cuánto se recomienda {t.name.lower()}?"])
    if any(w in q for w in ("cada cuanto", "frecuencia", "sesiones", "cuantas veces", "pauta", "resultados")):
        return Reply(f"**{t.name}: frecuencia**\n{t.frequency}", tail)
    if any(w in q for w in ("precio", "cuesta", "tarifa", "cuanto vale", "coste", "cuanto es")):
        svc = _services_for(t)
        return Reply(f"**{t.name}: precios**\n{svc}" if svc else f"No tengo cargado el precio de {t.name.lower()}: míralo en **Ajustes → Servicios**.", tail)
    if any(w in q for w in ("duele", "efectos", "marcas", "hematoma", "enrojec", "normal", "molest")):
        return Reply(f"**{t.name}: efectos esperables**\n{_bullets(t.effects)}", [tail[1]])
    steps = f"\n\n**Fases**\n{_bullets(t.steps)}" if t.steps else ""
    price = _services_for(t)
    price_txt = f"\n\n**Servicios y precios**\n{price}" if price else ""
    return Reply(f"**{t.name}**\n{t.summary}\n\nDuración: {t.duration}. {t.frequency}{steps}{price_txt}", tail)


# --------------------------------------------------------------------------- datos en vivo
def _appt_lines(items: list[dict]) -> str:
    return "\n".join(
        f"- **{fmt_time(a['start_ts'])}** · {a['client_name']} · {a['service_name']}" + (" ✓ cobrada" if a["paid"] else "")
        for a in items
    )


def _today_agenda() -> Reply:
    items = appointments.day_appointments(today())
    if not items:
        return Reply("Hoy no hay citas en la agenda. 🌿", ["¿Qué citas hay mañana?"])
    s = appointments.day_summary(today())
    return Reply(f"**Hoy tienes {len(items)} cita(s)** · {s['paid']} cobrada(s), {s['to_collect']} por cobrar\n{_appt_lines(items)}",
                 ["¿Cuánto llevamos cobrado hoy?"])


def _tomorrow_agenda() -> Reply:
    items = appointments.day_appointments(today() + timedelta(days=1))
    if not items:
        return Reply("Mañana no hay citas todavía.", [])
    return Reply(f"**Mañana ({len(items)} cita/s)**\n{_appt_lines(items)}\n\nEn *Agenda → Recordatorios de mañana* tienes los enlaces de WhatsApp.", [])


def _cash_today() -> Reply:
    s = cashbox.day_summary(today())
    if not s["movements"]:
        return Reply("Todavía no hay cobros registrados hoy.", ["¿Qué citas hay hoy?"])
    lines = "\n".join(f"- {label}: **{fmt_eur(s['by_method'].get(key, 0))}**"
                      for key, label in (("efectivo", "Efectivo"), ("tarjeta", "Tarjeta"), ("bizum", "Bizum")))
    extra = f"\n- Consumido de monedero/tarjeta regalo: {fmt_eur(s['consumed_cents'])}" if s["consumed_cents"] else ""
    return Reply(f"**Caja de hoy**: {fmt_eur(s['money_in_cents'])} cobrados en {s['tickets']} ticket(s)\n{lines}{extra}", ["¿Cómo hago el cierre de caja?"])


def _birthdays() -> Reply:
    rows = clients.birthdays_in_month(today().month)
    if not rows:
        return Reply("Este mes no hay cumpleaños registrados.", [])
    lines = "\n".join(f"- {r['day']:02d}/{today().month:02d} · {clients.full_name(r)}" for r in rows[:15])
    return Reply(f"**Cumpleaños de este mes ({len(rows)})**\n{lines}\n\nEn *Marketing → Cumpleaños* puedes felicitarlas por WhatsApp.", [])


def _gift_cards() -> Reply:
    soon = giftcards.expiring_soon(30)
    total = giftcards.outstanding_cents()
    text = f"Saldo pendiente en tarjetas regalo vigentes: **{fmt_eur(total)}**."
    if soon:
        text += "\n\n**Caducan en 30 días**\n" + "\n".join(
            f"- {c['code']} · {fmt_eur(c['balance_cents'])} · {fmt_date(c['expires_at'])}" for c in soon[:10])
    else:
        text += " Ninguna caduca en los próximos 30 días."
    return Reply(text, [])


def _pending_payments() -> Reply:
    items = appointments.pending_payment()
    if not items:
        return Reply("No hay citas pasadas pendientes de cobro. ✅", [])
    lines = "\n".join(f"- {fmt_date(a['start_ts'])} {fmt_time(a['start_ts'])} · {a['client_name']} · {a['service_name']} ({fmt_eur(a['price_cents'])})"
                      for a in items[:12])
    return Reply(f"**Citas pasadas sin cobrar ({len(items)})**\n{lines}", [])


def _find_client(q: str) -> dict | None:
    tokens = set(q.split())
    best, best_score = None, 0
    for c in clients.search_clients():
        first = norm(c["first_name"]).split()
        last = norm(c["last_name"]).split()
        score = sum(2 for t in first if len(t) >= 3 and t in tokens) + sum(1 for t in last if len(t) >= 3 and t in tokens)
        if score > best_score:
            best, best_score = c, score
    return best if best_score >= 2 else None


def _client_reply(c: dict, q: str) -> Reply:
    name = clients.full_name(c)
    st = clients.client_stats(c["id"])
    if any(w in q for w in ("saldo", "monedero")):
        return Reply(f"**{name}** tiene **{fmt_eur(wallet.balance(c['id']))}** en el monedero.", [])
    if any(w in q for w in ("proxima", "siguiente")):
        nxt = st["next"]
        return Reply(f"La próxima cita de **{name}** es el **{fmt_date(nxt['start_ts'])} a las {fmt_time(nxt['start_ts'])}** ({nxt['service_name']})." if nxt
                     else f"**{name}** no tiene citas futuras.", [])
    last = fmt_date(st["last_visit"]) if st["last_visit"] else "sin visitas registradas"
    allergy = f"\n⚠️ Alergias: {c['allergies']}" if c.get("allergies") else ""
    return Reply(f"**{name}** · {st['visits']} visita(s) · última: {last} · gastado: {fmt_eur(st['spent_cents'])} · monedero: {fmt_eur(st['wallet_cents'])}{allergy}", [])


def _live_intent(q: str) -> Reply | None:
    tokens = set(q.split())
    if "hoy" in tokens and tokens & {"cita", "citas", "agenda", "toca", "tenemos"}:
        return _today_agenda()
    if "manana" in tokens and tokens & {"cita", "citas", "agenda", "toca", "tenemos"}:
        return _tomorrow_agenda()
    if ("hoy" in tokens and tokens & {"cobrado", "facturado", "caja", "ingresos", "vendido", "llevamos", "recaudado"}) or "arqueo" in tokens and "hoy" in tokens:
        return _cash_today()
    if tokens & {"cumpleanos", "cumple", "cumples", "cumpleaneras"}:
        return _birthdays()
    if "regalo" in tokens and tokens & {"caducan", "caducidad", "pendientes", "vigentes", "caducadas"}:
        return _gift_cards()
    if (tokens & {"pendientes", "pendiente"} and tokens & {"cobro", "cobrar", "cobrados"}) or "sin cobrar" in q or "por cobrar" in q:
        return _pending_payments()
    if "rgpd" in tokens and tokens & {"quien", "quienes", "falta", "faltan", "pendientes", "sin"}:
        from services import consents

        missing = consents.missing_rgpd()
        return Reply(f"Hay **{len(missing)}** clienta(s) sin RGPD firmado." + ("\n" + "\n".join(f"- {m['first_name']} {m['last_name']}" for m in missing[:12]) if missing else ""), [])
    if tokens & {"saldo", "monedero", "proxima", "siguiente", "ultima", "visita", "visitas", "alergia", "alergias", "cuanto"}:
        c = _find_client(q)
        if c:
            return _client_reply(c, q)
    return None


# --------------------------------------------------------------------------- punto de entrada
def _fallback() -> Reply:
    return Reply(
        "No estoy seguro de haber entendido 🤔. Prueba a preguntarme de otra forma o elige una de estas opciones. "
        "Si es un tema de salud concreto de una clienta, consúltalo con la profesional.",
        WELCOME_SUGGESTIONS,
    )


def answer(question: str) -> Reply:
    q = norm(question)
    if not q:
        return welcome()
    if any(w in q.split() for w in ("hola", "buenas", "buenos", "ayuda", "ayudame")) and len(q.split()) <= 4:
        return welcome()
    if any(w in q.split() for w in ("gracias", "perfecto", "genial", "vale")) and len(q.split()) <= 4:
        return Reply("¡De nada! Aquí estoy para lo que necesites. 💛", [])

    live = _live_intent(q)
    if live:
        return live

    treatment = find_treatment(question)
    best_help, best_score = None, 0
    for topic in HELP_TOPICS:
        score = _score(q, topic["keys"])
        if score > best_score:
            best_help, best_score = topic, score

    # Si la pregunta es claramente del software, gana la ayuda; si nombra un tratamiento, gana el tratamiento.
    if treatment and best_score < 5:
        return _treatment_reply(treatment, q)
    if best_help and best_score >= 3:
        return Reply(best_help["text"], best_help["suggestions"])
    if treatment:
        return _treatment_reply(treatment, q)
    return _fallback()
