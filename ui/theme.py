"""Tema visual: negro azabache, dorados, tipografía clara y componentes propios (mobile first).

Streamlit aplica la paleta base desde ``.streamlit/config.toml``; aquí se refina con CSS. Los contenedores
con ``key=`` generan la clase ``st-key-<key>``, que usamos como ancla estable (mejor que selectores internos).
"""
from __future__ import annotations

import math
from urllib.parse import quote

import streamlit as st

from core.config import Colors as C


def _star_svg(color: str = C.GOLD) -> str:
    """Marca de agua: estrella de 8 puntas con flor central (SVG en data-URI)."""
    cx = cy = 200
    parts = []
    for radius, width in ((188, 2.4), (156, 1.4)):
        for off in (0, 45):
            pts = " ".join(
                f"{cx + radius * math.cos(math.radians(off + 90 * k - 90)):.1f},{cy + radius * math.sin(math.radians(off + 90 * k - 90)):.1f}"
                for k in range(4)
            )
            parts.append(f'<polygon points="{pts}" fill="none" stroke="{color}" stroke-width="{width}"/>')
    for k in range(8):
        ang = math.radians(45 * k)
        parts.append(f'<circle cx="{cx + 60 * math.cos(ang):.1f}" cy="{cy + 60 * math.sin(ang):.1f}" r="60" fill="none" stroke="{color}" stroke-width="1.4"/>')
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 400">{"".join(parts)}</svg>'
    return "data:image/svg+xml," + quote(svg)


_FONTS = (
    "@import url('https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@500;600;700&"
    "family=Great+Vibes&family=Inter:wght@400;500;600;700&display=swap');"
)

CSS = f"""
{_FONTS}
:root {{
  --bg:{C.BG}; --surface:{C.SURFACE}; --surface2:{C.SURFACE_2}; --border:{C.BORDER};
  --gold:{C.GOLD}; --gold-deep:{C.GOLD_DEEP}; --gold-soft:{C.GOLD_SOFT};
  --text:{C.TEXT}; --muted:{C.MUTED}; --ok:{C.OK}; --warn:{C.WARN}; --danger:{C.DANGER};
  --radius:14px; --font-body:'Inter',system-ui,-apple-system,'Segoe UI',Roboto,sans-serif;
  --font-title:'Cormorant Garamond',Georgia,'Times New Roman',serif; --font-brand:'Great Vibes','Brush Script MT',cursive;
}}
html, body, .stApp {{ font-family:var(--font-body); font-size:16px; line-height:1.5; }}
.stApp {{
  background:
    radial-gradient(1100px 520px at 85% -10%, rgba(230,197,102,.07), transparent 60%),
    radial-gradient(900px 500px at -10% 110%, rgba(186,149,48,.05), transparent 60%),
    var(--bg);
}}
.stApp::before {{
  content:""; position:fixed; right:-140px; bottom:-140px; width:620px; height:620px; z-index:0;
  background:url("{_star_svg()}") no-repeat center / contain; opacity:.055; pointer-events:none;
}}
[data-testid="stAppViewContainer"], [data-testid="stMain"] {{ position:relative; z-index:1; }}

/* Quitamos el cromo de Streamlit que no aporta */
#MainMenu, footer, [data-testid="stToolbar"], [data-testid="stDecoration"], [data-testid="stStatusWidget"] {{ display:none !important; }}
header[data-testid="stHeader"] {{ background:transparent; height:0; min-height:0; }}
.block-container {{ max-width:1240px; padding:1.1rem 1.4rem 7rem; }}
@media (max-width:640px) {{ .block-container {{ padding:.9rem 16px 8.5rem; }} }}

/* Tipografía */
h1,h2,h3 {{ font-family:var(--font-title) !important; font-weight:600 !important; letter-spacing:.2px; color:var(--text); }}
h1 {{ font-size:2.3rem !important; }} h2 {{ font-size:1.85rem !important; }} h3 {{ font-size:1.45rem !important; }}
p, li, label, .stMarkdown, [data-testid="stCaptionContainer"] {{ font-size:1rem; }}
[data-testid="stCaptionContainer"] {{ color:var(--muted); }}
hr {{ border-color:var(--border) !important; margin:1.2rem 0 !important; }}
a {{ color:var(--gold); }}

/* Botones: grandes, táctiles, dorados */
.stButton > button, .stDownloadButton > button, a[data-testid^="stBaseLinkButton"],
[data-testid="stBaseButton-secondary"], [data-testid="stBaseButton-secondaryFormSubmit"] {{
  min-height:46px; border-radius:12px; border:1px solid var(--border); background:var(--surface2); color:var(--text);
  font-weight:500; font-size:1rem; transition:border-color .15s, background .15s, transform .05s;
}}
.stButton > button:hover, .stDownloadButton > button:hover, a[data-testid^="stBaseLinkButton"]:hover {{
  border-color:var(--gold-deep); background:#241f30; color:var(--gold-soft);
}}
.stButton > button:active {{ transform:scale(.985); }}
[data-testid="stBaseButton-primary"], [data-testid="stBaseButton-primaryFormSubmit"], .stButton > button[kind="primary"],
a[data-testid="stBaseLinkButton-primary"] {{
  background:linear-gradient(180deg,#f0d98c 0%,var(--gold) 45%,var(--gold-deep) 100%) !important;
  color:#17130a !important; border:0 !important; font-weight:600 !important;
  box-shadow:0 6px 18px rgba(186,149,48,.22);
}}
[data-testid="stBaseButton-primary"]:hover {{ filter:brightness(1.06); color:#17130a !important; }}

/* Campos */
[data-baseweb="input"], [data-baseweb="base-input"], [data-baseweb="select"] > div, textarea {{
  background:var(--surface) !important; border-radius:12px !important; border-color:var(--border) !important;
}}
input, textarea, [data-baseweb="select"] div {{ font-size:16px !important; }}  /* 16px evita el zoom en iPhone */
[data-baseweb="input"]:focus-within, [data-baseweb="select"] > div:focus-within, textarea:focus {{ border-color:var(--gold-deep) !important; box-shadow:0 0 0 1px var(--gold-deep) !important; }}
label p {{ color:var(--muted) !important; font-size:.92rem !important; font-weight:500; }}

/* Pestañas */
[data-baseweb="tab-list"] {{ gap:.25rem; border-bottom:1px solid var(--border); overflow-x:auto; scrollbar-width:none; }}
button[data-baseweb="tab"] {{ height:48px; padding:0 1rem; color:var(--muted); font-weight:500; white-space:nowrap; }}
button[data-baseweb="tab"][aria-selected="true"] {{ color:var(--gold); }}
[data-baseweb="tab-highlight"] {{ background:var(--gold) !important; height:2px !important; }}

/* Métricas, alertas, expanders, diálogos */
[data-testid="stMetric"] {{ background:var(--surface); border:1px solid var(--border); border-radius:var(--radius); padding:.9rem 1rem; }}
[data-testid="stMetricLabel"] p {{ color:var(--muted) !important; }}
[data-testid="stMetricValue"] {{ font-family:var(--font-title); font-size:2rem; color:var(--gold-soft); }}
[data-testid="stAlert"] {{ border-radius:12px; border:1px solid var(--border); }}
[data-testid="stExpander"] {{ border:1px solid var(--border) !important; border-radius:var(--radius) !important; background:var(--surface); }}
[data-testid="stExpander"] summary {{ font-weight:500; }}
div[role="dialog"] {{ background:var(--surface) !important; border:1px solid var(--gold-deep); border-radius:20px !important; box-shadow:0 30px 80px rgba(0,0,0,.6); }}
@media (max-width:640px) {{ div[role="dialog"] {{ width:calc(100vw - 16px) !important; max-height:92vh; }} }}
[data-testid="stPopoverBody"] {{ background:var(--surface); border:1px solid var(--gold-deep); border-radius:16px; }}
[data-testid="stDataFrame"] {{ border:1px solid var(--border); border-radius:12px; overflow:hidden; }}

/* ---------- Marca y navegación ---------- */
.jd-brand {{ display:flex; flex-direction:column; line-height:1; padding:.1rem 0 .2rem; }}
.jd-brand-name {{ font-family:var(--font-brand); font-size:3rem; color:var(--gold); line-height:1.05;
  background:linear-gradient(180deg,var(--gold-soft),var(--gold) 50%,var(--gold-deep)); -webkit-background-clip:text; background-clip:text; -webkit-text-fill-color:transparent; }}
.jd-brand-tag {{ font-size:.66rem; letter-spacing:.42em; color:var(--muted); margin-top:.15rem; padding-left:.2rem; }}
@media (max-width:640px) {{ .jd-brand-name {{ font-size:2.4rem; }} .jd-brand-tag {{ font-size:.58rem; }} }}

.st-key-jd_header [data-testid="stHorizontalBlock"] {{ flex-wrap:nowrap !important; align-items:center; }}
.st-key-jd_header [data-testid="stColumn"] {{ min-width:0 !important; }}
.st-key-jd_nav {{ margin:.2rem 0 1rem; overflow-x:auto; scrollbar-width:none; }}
.st-key-jd_nav [data-testid="stSegmentedControl"], .st-key-jd_nav [role="radiogroup"] {{ flex-wrap:nowrap !important; min-width:max-content; }}
.st-key-jd_nav button, .st-key-jd_nav label {{ white-space:nowrap; font-weight:500; }}
@media (max-width:768px) {{  /* en móvil la navegación queda fija abajo, al alcance del pulgar */
  .st-key-jd_nav {{ position:fixed; left:0; right:0; bottom:0; z-index:999; margin:0; padding:8px 10px calc(8px + env(safe-area-inset-bottom));
    background:rgba(11,10,15,.96); backdrop-filter:blur(12px); border-top:1px solid var(--gold-deep); }}
}}
.st-key-jd_bot {{ position:fixed; right:18px; bottom:18px; z-index:1000; }}
@media (max-width:768px) {{ .st-key-jd_bot {{ bottom:84px; right:12px; }} }}
.st-key-jd_bot button {{ border-radius:999px; background:linear-gradient(180deg,#f0d98c,var(--gold-deep)) !important; color:#17130a !important; border:0 !important;
  font-weight:600; box-shadow:0 10px 28px rgba(0,0,0,.5); min-height:50px; padding:0 1.1rem; }}

/* ---------- Componentes propios ---------- */
.jd-title {{ font-family:var(--font-title); font-size:2.2rem; font-weight:600; color:var(--gold-soft); margin:.2rem 0 0; line-height:1.1; }}
.jd-sub {{ color:var(--muted); margin:.15rem 0 1rem; font-size:.98rem; }}
.jd-kpis {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:.7rem; margin:.4rem 0 1rem; }}
.jd-kpi {{ background:linear-gradient(180deg,var(--surface2),var(--surface)); border:1px solid var(--border); border-radius:var(--radius); padding:.85rem 1rem; }}
.jd-kpi-label {{ color:var(--muted); font-size:.78rem; letter-spacing:.08em; text-transform:uppercase; }}
.jd-kpi-value {{ font-family:var(--font-title); font-size:2rem; font-weight:600; color:var(--gold-soft); line-height:1.15; }}
.jd-kpi-hint {{ color:var(--muted); font-size:.82rem; }}
.jd-card {{ background:var(--surface); border:1px solid var(--border); border-radius:var(--radius); padding:1rem 1.1rem; margin-bottom:.7rem; }}
.jd-card.gold {{ border-color:var(--gold-deep); background:linear-gradient(180deg,#1c1810,var(--surface)); }}
.jd-appt {{ display:flex; gap:.9rem; align-items:center; background:var(--surface); border:1px solid var(--border); border-left:4px solid var(--gold);
  border-radius:12px; padding:.7rem .9rem; margin-bottom:.5rem; }}
.jd-appt-time {{ font-family:var(--font-title); font-size:1.5rem; color:var(--gold-soft); min-width:3.6rem; line-height:1; }}
.jd-appt-main {{ flex:1; min-width:0; }}
.jd-appt-name {{ font-weight:600; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }}
.jd-appt-meta {{ color:var(--muted); font-size:.88rem; }}
.jd-badge {{ display:inline-block; padding:.12rem .6rem; border-radius:999px; font-size:.76rem; font-weight:600; border:1px solid var(--border); color:var(--muted); background:var(--surface2); }}
.jd-badge.ok {{ color:var(--ok); border-color:rgba(127,184,154,.4); }} .jd-badge.warn {{ color:var(--warn); border-color:rgba(224,164,88,.4); }}
.jd-badge.bad {{ color:var(--danger); border-color:rgba(217,119,127,.4); }} .jd-badge.gold {{ color:var(--gold); border-color:var(--gold-deep); }}
.jd-alert {{ background:rgba(217,119,127,.10); border:1px solid rgba(217,119,127,.45); border-radius:12px; padding:.6rem .9rem; margin:.4rem 0; }}
.jd-empty {{ text-align:center; color:var(--muted); padding:2rem 1rem; border:1px dashed var(--border); border-radius:var(--radius); }}
.jd-empty .ico {{ font-size:2rem; display:block; margin-bottom:.3rem; }}
.jd-total {{ display:flex; justify-content:space-between; align-items:baseline; border-top:1px solid var(--gold-deep); margin-top:.6rem; padding-top:.6rem; }}
.jd-total b {{ font-family:var(--font-title); font-size:2.4rem; color:var(--gold); font-weight:600; }}
table.jd-lines {{ width:100%; border-collapse:collapse; font-size:.95rem; }}
table.jd-lines th {{ color:var(--muted); font-weight:500; text-align:left; font-size:.76rem; letter-spacing:.08em; text-transform:uppercase; padding:.3rem .4rem; border-bottom:1px solid var(--border); }}
table.jd-lines td {{ padding:.5rem .4rem; border-bottom:1px solid var(--border); }}
table.jd-lines td.r, table.jd-lines th.r {{ text-align:right; white-space:nowrap; }}
.jd-muted {{ color:var(--muted); }}
.jd-legend {{ display:flex; flex-wrap:wrap; gap:.4rem .9rem; margin:.4rem 0 .2rem; font-size:.85rem; color:var(--muted); }}
.jd-dot {{ display:inline-block; width:.7rem; height:.7rem; border-radius:50%; margin-right:.35rem; vertical-align:-1px; }}
"""


def inject() -> None:
    """Inyecta el tema (llamar una vez por ejecución, al principio de la app)."""
    st.markdown(f"<style>{CSS}</style>", unsafe_allow_html=True)


# CSS que se inyecta dentro del iframe del calendario (FullCalendar tiene su propio documento).
CALENDAR_CSS = f"""
@import url('https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@600&family=Inter:wght@400;500;600&display=swap');
:root {{ --fc-border-color:{C.BORDER}; --fc-page-bg-color:{C.BG}; --fc-neutral-bg-color:{C.SURFACE};
  --fc-today-bg-color:rgba(230,197,102,.07); --fc-now-indicator-color:{C.GOLD};
  --fc-button-bg-color:{C.SURFACE_2}; --fc-button-border-color:{C.BORDER}; --fc-button-text-color:{C.TEXT};
  --fc-button-hover-bg-color:#241f30; --fc-button-hover-border-color:{C.GOLD_DEEP};
  --fc-button-active-bg-color:{C.GOLD_DEEP}; --fc-button-active-border-color:{C.GOLD_DEEP};
  --fc-non-business-color:rgba(255,255,255,.025); --fc-list-event-hover-bg-color:#241f30; }}
body, .fc {{ font-family:'Inter',system-ui,sans-serif; background:{C.BG}; color:{C.TEXT}; }}
.fc .fc-toolbar-title {{ font-family:'Cormorant Garamond',Georgia,serif; font-size:1.55rem; font-weight:600; color:{C.GOLD_SOFT}; text-transform:capitalize; }}
.fc .fc-button {{ border-radius:10px; text-transform:capitalize; font-weight:500; padding:.45rem .8rem; box-shadow:none !important; }}
.fc .fc-button-primary:not(:disabled).fc-button-active, .fc .fc-button-primary:not(:disabled):active {{ color:#17130a; }}
.fc-theme-standard td, .fc-theme-standard th, .fc-theme-standard .fc-scrollgrid {{ border-color:{C.BORDER}; }}
.fc .fc-col-header-cell-cushion {{ color:{C.TEXT}; font-weight:600; font-size:.85rem; text-transform:capitalize; padding:.5rem .2rem; }}
.fc .fc-timegrid-slot-label-cushion, .fc .fc-timegrid-axis-cushion {{ color:{C.MUTED}; font-size:.78rem; }}
.fc .fc-timegrid-slot {{ height:2.1rem; }}
.fc .fc-timegrid-slot-minor {{ border-top-style:dotted; border-color:rgba(255,255,255,.05); }}
.fc .fc-daygrid-day-number {{ color:{C.MUTED}; padding:.3rem .5rem; }}
.fc .fc-day-today .fc-daygrid-day-number {{ color:{C.GOLD}; font-weight:700; }}
.fc .fc-event {{ border-radius:8px; border-width:0 0 0 4px; box-shadow:0 2px 8px rgba(0,0,0,.35); cursor:pointer; font-size:.8rem; }}
.fc .fc-event-main {{ padding:3px 6px; line-height:1.25; }}
.fc .fc-event-title {{ font-weight:600; white-space:normal; }}
.fc .fc-event-time {{ font-weight:500; opacity:.85; }}
.fc .evt-cancelled {{ opacity:.45; text-decoration:line-through; }}
.fc .evt-paid {{ filter:saturate(.8) brightness(.92); }}
.fc .fc-list {{ border-color:{C.BORDER}; }} .fc .fc-list-day-cushion {{ background:{C.SURFACE}; }}
.fc .fc-highlight {{ background:rgba(230,197,102,.18); }}
.fc .fc-scrollgrid-section-sticky > * {{ background:{C.BG}; }}
@media (max-width:640px) {{
  .fc .fc-toolbar {{ flex-wrap:wrap; gap:.4rem; justify-content:space-between; }}
  .fc .fc-toolbar-title {{ font-size:1.15rem; }}
  .fc .fc-col-header-cell-cushion {{ font-size:.7rem; padding:.35rem 0; }}
  .fc .fc-timegrid-slot-label-cushion {{ font-size:.68rem; }}
  .fc .fc-event {{ font-size:.68rem; }} .fc .fc-button {{ padding:.4rem .6rem; }}
}}
"""
