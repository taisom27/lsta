"""Detección por reglas de datos que los portales suelen dejar en el texto libre."""
from __future__ import annotations

import re

_ENERGIA = re.compile(
    r"(?:certificad[oa]|calificaci[oó]n|eficiencia|clase)\s+(?:de\s+)?energ[ée]tic[oa]"
    r"(?:\s*\(?(?:consumo|emisiones)\)?)?\s*[:\-–]?\s*(?:letra\s+)?\(?([A-G])\)?(?![A-Za-z])",
    re.IGNORECASE,
)
_ENERGIA_TRAMITE = re.compile(r"energ[ée]tic[oa][^.\n]{0,30}\b(?:en\s+tr[aá]mite|pendiente)", re.I)
_ENERGIA_EXENTO = re.compile(r"energ[ée]tic[oa][^.\n]{0,30}\bexent[oa]", re.I)

_GARAJE = re.compile(r"\b(garaje|plaza de (?:garaje|aparcamiento|parking)|parking)\b", re.I)
_SIN_GARAJE = re.compile(r"\bsin\s+(garaje|plaza de (?:garaje|aparcamiento|parking)|parking)\b", re.I)
_TRASTERO = re.compile(r"\btrasteros?\b", re.I)
_SIN_TRASTERO = re.compile(r"\bsin\s+trasteros?\b", re.I)


def energia(texto: str) -> str | None:
    """Devuelve la letra (A-G), 'en trámite', 'exento' o None."""
    if not texto:
        return None
    m = _ENERGIA.search(texto)
    if m:
        return m.group(1).upper()
    if _ENERGIA_TRAMITE.search(texto):
        return "en trámite"
    if _ENERGIA_EXENTO.search(texto):
        return "exento"
    return None


def menciona_garaje(texto: str) -> bool:
    return bool(texto) and bool(_GARAJE.search(texto)) and not _SIN_GARAJE.search(texto)


def menciona_trastero(texto: str) -> bool:
    return bool(texto) and bool(_TRASTERO.search(texto)) and not _SIN_TRASTERO.search(texto)


def enriquecer(piso) -> None:
    """Completa energía, garaje y trastero a partir de título y descripción."""
    texto = f"{piso.titulo}\n{piso.descripcion}"
    if piso.energia is None:
        piso.energia = energia(texto)
    piso.garaje = piso.garaje or menciona_garaje(texto)
    piso.trastero = piso.trastero or menciona_trastero(texto)
