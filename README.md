# Judit Domingo · Centre d'Estètica — app de gestión

Streamlit + SQLite + Pandas + Pillow. Agenda, caja y facturación, clientas (RGPD), marketing y tarjetas regalo, analítica y asistente virtual.

## Arrancar
```
pip install -r requirements.txt
streamlit run app.py
```
En el primer acceso se crea la contraseña. En un servidor, define mejor el secreto `APP_PASSWORD` (`.streamlit/secrets.toml` o variable `JD_APP_PASSWORD`).
En Streamlit Community Cloud, `packages.txt` instala las tipografías del sistema.

## Estructura
- `app.py` — entrada, cabecera, navegación (barra inferior en móvil), asistente flotante.
- `core/` — configuración, utilidades (dinero en céntimos), base de datos con migraciones, seguridad.
- `services/` — lógica de negocio sin interfaz: agenda, facturación encadenada, caja, impuestos, clientes, monedero, tarjetas regalo, consentimientos, analítica, copias, asistente.
- `documents/` — PNG de tarjeta regalo, PDF de factura y de consentimiento (Pillow).
- `ui/` — tema CSS, componentes, diálogos y páginas (`ui/pages/`).
- `tests/` — `python -m tests.test_core` (lógica) y `python -m tests.smoke_runner` (páginas con un Streamlit simulado).

## Personalización
Fuentes y logo propios: ver `assets/fonts/README.txt`. Servicios y precios (de ejemplo) en Ajustes → Servicios. Plantillas de WhatsApp en Marketing → Plantillas.

## Importante
- **Copias de seguridad**: en Community Cloud el disco se borra al reiniciar. Descarga una copia en Ajustes → Copias con regularidad.
- **Veri*Factu**: la facturación está *preparada* (numeración correlativa, huella SHA-256 encadenada, rectificativas), **no certificada**. Consulta con la gestoría.
- **IVA/IRPF**: los Modelos 303 y 130 son estimaciones orientativas. Las tarjetas regalo se cobran pero no se facturan hasta su canje (criterio a confirmar con la gestoría).
- **RGPD**: los textos de consentimiento son una base; que los revise un profesional.
- **Limitaciones conocidas**: la interfaz se verificó con un Streamlit simulado (no se pudo instalar Streamlit en el entorno de desarrollo), así que conviene una primera pasada visual real. Volver a pulsar la misma cita del calendario dos veces seguidas puede no reabrirla; usa los botones «Abrir» de las listas.
