"""Lectura de portales web (pisos.com, Fotocasa, Habitaclia...) con ayuda de Claude.

En vez de depender del HTML exacto de cada portal (que cambia a menudo), se descarga la página
de resultados, se convierte a texto con sus enlaces y Claude extrae los anuncios.
"""
from __future__ import annotations

import hashlib
import logging
from urllib.parse import urljoin, urlsplit

import requests
from bs4 import BeautifulSoup

from ..modelos import Piso

log = logging.getLogger(__name__)

CABECERAS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/128.0 Safari/537.36"
    ),
    "Accept-Language": "es-ES,es;q=0.9",
}


def descargar_texto(url: str) -> str:
    """Texto visible de la página, con los enlaces escritos como [texto](url absoluta)."""
    r = requests.get(url, headers=CABECERAS, timeout=30)
    r.raise_for_status()
    sopa = BeautifulSoup(r.text, "html.parser")
    for etiqueta in sopa(["script", "style", "noscript", "svg", "header", "footer", "nav", "form"]):
        etiqueta.decompose()
    for a in sopa.find_all("a", href=True):
        a.replace_with(f" [{a.get_text(' ', strip=True)}]({urljoin(url, a['href'])}) ")
    lineas = (l.strip() for l in sopa.get_text("\n").splitlines())
    return "\n".join(l for l in lineas if l)


def _id(nombre: str, url: str) -> str:
    partes = urlsplit(url)
    return f"{nombre}:{hashlib.sha1((partes.netloc + partes.path).encode()).hexdigest()[:12]}"


def a_piso(nombre: str, a: dict) -> Piso | None:
    if not a.get("precio") or not a.get("url"):
        return None
    return Piso(
        id=_id(nombre, a["url"]),
        fuente=nombre,
        url=a["url"],
        titulo=a.get("titulo", ""),
        precio=int(a["precio"]),
        habitaciones=a.get("habitaciones"),
        metros=a.get("metros"),
        direccion=a.get("direccion", ""),
        barrio=a.get("barrio", ""),
        energia=a.get("calificacion_energetica"),
        garaje=bool(a.get("garaje")),
        trastero=bool(a.get("trastero")),
        ascensor=a.get("ascensor"),
        obra_nueva=bool(a.get("obra_nueva")),
        planta=a.get("planta", ""),
        descripcion=a.get("descripcion", ""),
    )


def buscar(portal: dict, ia) -> list[Piso]:
    texto = descargar_texto(portal["url"])
    anuncios = ia.extraer_anuncios(portal["url"], texto)
    pisos = [p for p in (a_piso(portal["nombre"], a) for a in anuncios) if p]
    log.info("%s: %d anuncios", portal["nombre"], len(pisos))
    return pisos
