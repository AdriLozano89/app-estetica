"""Carga de fuentes para imágenes y PDF con cadena de respaldo (nunca falla por una fuente ausente).

Orden de búsqueda: carpeta ``assets/fonts`` del proyecto → fuentes del sistema → fuente interna de Pillow.
Así, si añades GreatVibes/Cormorant/Montserrat a ``assets/fonts`` se usan; si no, se usa una serif
cursiva o sans del sistema y el resultado sigue siendo elegante y legible.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from PIL import ImageFont

from core.config import FONTS_DIR

# Cada rol lista fuentes por orden de preferencia (nombre sin extensión, en minúsculas).
ROLE_CANDIDATES: dict[str, tuple[str, ...]] = {
    "script": ("greatvibes-regular", "allura-regular", "dancingscript-regular", "lora-italic", "caladea-italic",
               "dejavuserif-italic", "liberationserif-italic"),
    "serif": ("cormorantgaramond-regular", "cormorantgaramond", "lora", "caladea-regular", "dejavuserif", "liberationserif-regular"),
    "serif_bold": ("cormorantgaramond-semibold", "cormorantgaramond-bold", "caladea-bold", "dejavuserif-bold", "liberationserif-bold"),
    "serif_italic": ("cormorantgaramond-italic", "lora-italic", "caladea-italic", "dejavuserif-italic", "liberationserif-italic"),
    "sans": ("montserrat-regular", "montserrat", "poppins-regular", "carlito-regular", "dejavusans", "liberationsans-regular"),
    "sans_medium": ("montserrat-medium", "poppins-medium", "carlito-bold", "dejavusans", "liberationsans-regular"),
    "sans_bold": ("montserrat-semibold", "montserrat-bold", "poppins-bold", "carlito-bold", "dejavusans-bold", "liberationsans-bold"),
}


@lru_cache(maxsize=1)
def _index() -> dict[str, str]:
    """Índice nombre_de_archivo_en_minúsculas → ruta. La carpeta del proyecto tiene prioridad."""
    roots = [FONTS_DIR, Path("/usr/share/fonts"), Path("/usr/local/share/fonts"),
             Path.home() / ".fonts", Path.home() / ".local/share/fonts"]
    found: dict[str, str] = {}
    for root in roots:
        if not root.exists():
            continue
        try:
            for path in root.rglob("*"):
                if path.suffix.lower() in (".ttf", ".otf"):
                    found.setdefault(path.name.lower(), str(path))
        except OSError:
            continue
    return found


def _resolve(role: str) -> str | None:
    index = _index()
    for stem in ROLE_CANDIDATES.get(role, ROLE_CANDIDATES["sans"]):
        for ext in (".ttf", ".otf"):
            if stem + ext in index:
                return index[stem + ext]
        for name, path in index.items():  # variantes variables: Nombre[wght].ttf / Nombre-Variable.ttf
            if name.startswith(stem + "[") or name.startswith(stem + "-variable"):
                return path
    return None


@lru_cache(maxsize=256)
def get_font(role: str, size: int):
    """Fuente del rol pedido al tamaño dado. Si no hay ninguna, usa la interna de Pillow."""
    path = _resolve(role)
    if path:
        try:
            return ImageFont.truetype(path, size=int(size))
        except OSError:
            pass
    return ImageFont.load_default(size=int(size))


def fonts_report() -> dict[str, str]:
    """Qué archivo se usa realmente para cada rol (se muestra en Ajustes para diagnosticar)."""
    return {role: (Path(p).name if (p := _resolve(role)) else "fuente interna de Pillow") for role in ROLE_CANDIDATES}
