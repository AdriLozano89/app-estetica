"""Base de conocimiento de tratamientos: la comparten el asistente virtual y los consentimientos informados.

Los textos son orientativos y prudentes (no prometen resultados médicos). Edítalos para que reflejen
los protocolos reales de tu centro.
"""
from __future__ import annotations

from dataclasses import dataclass

from core.utils import norm


@dataclass(frozen=True)
class Treatment:
    key: str
    name: str
    keywords: tuple[str, ...]
    summary: str
    steps: tuple[str, ...]
    duration: str
    frequency: str
    contraindications: tuple[str, ...]
    effects: tuple[str, ...]
    aftercare: tuple[str, ...]


TREATMENTS: tuple[Treatment, ...] = (
    Treatment(
        key="limpieza_facial", name="Limpieza facial",
        keywords=("limpieza facial", "limpieza", "facial", "cara", "rostro", "impurezas", "puntos negros", "hidratante"),
        summary="Limpieza en profundidad que elimina impurezas y células muertas y deja la piel hidratada, luminosa y preparada para absorber mejor los cosméticos.",
        steps=("Desmaquillado y análisis de la piel", "Exfoliación suave", "Vaporización o calor para dilatar el poro",
               "Extracción de impurezas si procede", "Mascarilla adaptada a tu tipo de piel", "Sérum, crema e protección solar"),
        duration="60–75 minutos", frequency="Orientativamente cada 4–6 semanas, según el tipo de piel.",
        contraindications=("Acné inflamatorio severo, rosácea o dermatitis en fase activa", "Heridas, quemaduras solares o herpes labial activo",
                           "Tratamiento con isotretinoína (actual o reciente): consultar antes con tu médico",
                           "Embarazo o lactancia: avísanos para elegir cosméticos adecuados"),
        effects=("Enrojecimiento leve y temporal (suele desaparecer en unas horas)", "Sensibilidad ligera en la piel durante el día"),
        aftercare=("Evita el sol directo y las cabinas de bronceado 48 horas", "No te toques ni extraigas la piel", "Hidrátate y usa protector solar SPF 30+",
                   "Evita maquillarte las primeras 6–8 horas"),
    ),
    Treatment(
        key="facial_antiedad", name="Tratamiento facial antiedad",
        keywords=("antiedad", "anti edad", "arrugas", "reafirmante", "rejuvenecedor", "lifting facial", "colageno"),
        summary="Protocolo facial con activos reafirmantes e hidratantes para mejorar la firmeza, la textura y la luminosidad de la piel.",
        steps=("Limpieza y análisis", "Exfoliación adaptada", "Masaje facial", "Aplicación de activos y mascarilla", "Protección final"),
        duration="75 minutos", frequency="Se recomienda en pautas regulares; la profesional te indicará la frecuencia ideal.",
        contraindications=("Heridas o infecciones en la piel", "Alergias conocidas a cosméticos o activos", "Embarazo o lactancia: avísanos",
                           "Tratamientos médicos o estéticos recientes en la zona: consúltanos"),
        effects=("Rojez leve y pasajera",), aftercare=("Protector solar SPF 30+ cada día", "Evita el sol directo 48 horas", "Hidratación constante"),
    ),
    Treatment(
        key="maderoterapia", name="Maderoterapia",
        keywords=("maderoterapia", "madera", "rodillo", "anticelulitico", "celulitis", "reductor", "reductora", "moldeante"),
        summary="Masaje con instrumentos de madera (rodillos, copas, ruedas) que estimula la circulación y el drenaje. Se usa para tonificar, remodelar y mejorar el aspecto de la celulitis y la retención de líquidos.",
        steps=("Valoración de la zona a tratar", "Aplicación de aceite o crema", "Maniobras con rodillos y utensilios de madera", "Masaje final relajante"),
        duration="45–60 minutos",
        frequency="Suele hacerse en series de varias sesiones semanales; la pauta exacta la define la profesional. Los resultados dependen también de hábitos (agua, alimentación y movimiento).",
        contraindications=("Embarazo", "Trombosis, flebitis o varices severas", "Tratamiento con anticoagulantes o problemas de coagulación",
                           "Heridas, infecciones o inflamaciones en la zona", "Cáncer activo u otras patologías graves: consultar antes con tu médico",
                           "Hernias o cirugía reciente en la zona"),
        effects=("Enrojecimiento de la zona", "Posibles marcas o pequeños hematomas leves en pieles sensibles", "Sensación de cansancio o de ganas de orinar tras la sesión"),
        aftercare=("Bebe abundante agua el resto del día", "Evita sol intenso, sauna y calor excesivo ese día", "Mantén una alimentación ligera y actividad física suave"),
    ),
    Treatment(
        key="masaje_relajante", name="Masaje relajante",
        keywords=("masaje", "relajante", "relax", "contractura", "espalda", "estres", "estrés"),
        summary="Masaje de cuerpo completo con maniobras suaves y envolventes para liberar tensión muscular y favorecer el descanso.",
        steps=("Charla previa sobre zonas de tensión", "Masaje con aceite aromático", "Cierre con maniobras de relajación"),
        duration="50 minutos", frequency="Cuando lo necesites; muchas clientas lo reservan una vez al mes.",
        contraindications=("Fiebre o procesos infecciosos", "Heridas o infecciones cutáneas", "Trombosis o lesiones agudas", "Embarazo: avísanos para adaptarlo"),
        effects=("Sensación de relajación profunda o ligero cansancio", "Molestias leves si había contracturas"),
        aftercare=("Bebe agua", "Descansa y evita esfuerzos intensos esa noche"),
    ),
    Treatment(
        key="drenaje", name="Drenaje linfático manual",
        keywords=("drenaje", "linfatico", "linfático", "retencion", "retención de liquidos", "piernas cansadas", "hinchazon"),
        summary="Técnica manual muy suave que favorece la circulación de la linfa y ayuda con la sensación de hinchazón y retención de líquidos.",
        steps=("Valoración", "Maniobras suaves y rítmicas siguiendo el sistema linfático", "Cierre relajante"),
        duration="60 minutos", frequency="Depende de cada caso; la profesional te orientará.",
        contraindications=("Infecciones agudas o fiebre", "Trombosis", "Insuficiencia cardíaca o renal", "Cáncer activo: consultar con tu médico",
                           "Asma bronquial no controlada"),
        effects=("Ganas de orinar tras la sesión", "Sensación de ligereza o ligero cansancio"),
        aftercare=("Bebe abundante agua", "Evita el calor intenso ese día"),
    ),
    Treatment(
        key="presoterapia", name="Presoterapia",
        keywords=("presoterapia", "compresion", "compresión", "botas", "piernas pesadas"),
        summary="Compresión secuencial con aire mediante botas o fajas que mejora la sensación de piernas pesadas y la circulación.",
        steps=("Colocación del equipo", "Programa de compresión progresiva", "Retirada y valoración"),
        duration="40 minutos", frequency="Se pauta según objetivos; suele combinarse con otras técnicas.",
        contraindications=("Trombosis o flebitis", "Insuficiencia cardíaca", "Infecciones o heridas en la zona", "Embarazo: consultar antes"),
        effects=("Sensación de presión y de ligereza al terminar",), aftercare=("Bebe agua", "Camina un poco después de la sesión"),
    ),
    Treatment(
        key="manicura", name="Manicura y pedicura semipermanente",
        keywords=("manicura", "pedicura", "uñas", "unas", "semipermanente", "esmalte", "manos", "pies"),
        summary="Cuidado de manos o pies con limpieza, cutículas y esmaltado semipermanente de larga duración.",
        steps=("Retirada del esmalte anterior", "Limado y cuidado de cutículas", "Esmaltado semipermanente y secado en lámpara", "Hidratación"),
        duration="60 minutos", frequency="El semipermanente suele durar unas 2–3 semanas.",
        contraindications=("Hongos o infecciones en las uñas", "Alergia a esmaltes o acrilatos", "Heridas abiertas en la zona"),
        effects=("Sensibilidad temporal si las uñas están debilitadas",), aftercare=("No arranques el esmalte: pide que te lo retiremos", "Hidrata cutículas con aceite a diario"),
    ),
    Treatment(
        key="depilacion", name="Depilación con cera",
        keywords=("depilacion", "depilación", "cera", "piernas", "axilas", "ingles", "vello"),
        summary="Eliminación del vello de raíz con cera para una piel suave durante varias semanas.",
        steps=("Limpieza de la zona", "Aplicación de cera y retirada", "Calmante e hidratación"),
        duration="15–45 minutos según la zona", frequency="Cada 3–5 semanas, cuando el vello alcance unos milímetros.",
        contraindications=("Piel irritada, quemada o con heridas", "Tratamientos con retinoides o isotretinoína", "Diabetes mal controlada o problemas circulatorios en la zona",
                           "Varices marcadas en la zona a depilar"),
        effects=("Enrojecimiento temporal", "Pequeños granitos ocasionales"),
        aftercare=("Evita sol, sauna y piscina 24–48 horas", "No uses ropa muy ajustada ese día", "Exfolia suavemente a partir del tercer día"),
    ),
    Treatment(
        key="pestanas", name="Lifting de pestañas",
        keywords=("pestañas", "pestanas", "lifting de pestañas", "tinte de pestañas", "curvatura", "mirada"),
        summary="Eleva y curva las pestañas naturales y las tiñe para una mirada más abierta durante semanas.",
        steps=("Test de sensibilidad si es la primera vez", "Moldeado de la pestaña", "Fijación y tinte", "Retirada y cuidado"),
        duration="60 minutos", frequency="Dura entre 4 y 8 semanas según el ciclo natural de la pestaña.",
        contraindications=("Alergia a los productos", "Conjuntivitis o infecciones oculares", "Cirugía ocular reciente", "Embarazo: avísanos"),
        effects=("Ligera irritación o lagrimeo temporal",),
        aftercare=("Evita mojar las pestañas 24 horas", "No uses rizador de pestañas", "Peina con cepillito limpio"),
    ),
    Treatment(
        key="cejas", name="Diseño de cejas",
        keywords=("cejas", "diseño de cejas", "perfilado"),
        summary="Estudio de tu rostro para diseñar y perfilar la ceja que mejor te favorece.",
        steps=("Estudio de proporciones", "Perfilado con cera o pinza", "Calmante"),
        duration="30 minutos", frequency="Cada 3–4 semanas para mantener el diseño.",
        contraindications=("Piel irritada o con heridas en la zona", "Uso de retinoides"), effects=("Enrojecimiento breve",),
        aftercare=("Evita maquillaje en la zona unas horas", "No te toques ni te depiles entre sesiones"),
    ),
)

GENERIC = Treatment(
    key="generico", name="Tratamiento estético", keywords=(),
    summary="Tratamiento estético realizado por una profesional del centro.",
    steps=(), duration="Según el servicio", frequency="La profesional te lo indicará.",
    contraindications=("Heridas, infecciones o inflamaciones en la zona", "Embarazo o lactancia: avísanos", "Alergias conocidas a productos cosméticos",
                       "Enfermedades o medicación que debamos conocer"),
    effects=("Enrojecimiento leve y temporal en la zona",), aftercare=("Sigue las indicaciones de la profesional", "Consúltanos cualquier duda"),
)


def find_treatment(text: str) -> Treatment | None:
    """Busca el tratamiento que mejor encaja con un nombre de servicio o una pregunta."""
    haystack = norm(text)
    best, best_score = None, 0
    for t in TREATMENTS:
        score = 0
        for kw in t.keywords:
            nk = norm(kw)
            if nk and nk in haystack:
                score += len(nk.split()) * 2 + 1
        if norm(t.name) in haystack:
            score += 6
        if score > best_score:
            best, best_score = t, score
    return best


def treatment_for_service(service_name: str) -> Treatment:
    return find_treatment(service_name) or GENERIC
