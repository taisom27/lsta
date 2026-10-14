"""Plataformas de bancos, servicers y subastas (Escrapalia, Sareb, Aliseda, Altamira...).

Sus webs cargan los inmuebles con JavaScript, así que no basta con descargar la página: Claude
busca en la web restringido al dominio de cada plataforma, abre las fichas y anota lo que ve.
Después esas notas se convierten en anuncios con la misma extracción que los portales.
"""
from __future__ import annotations

import logging

from ..config import radio_km
from ..modelos import Piso
from . import portales

log = logging.getLogger(__name__)


def criterios(cfg: dict) -> str:
    b = cfg["busqueda"]
    return (
        f"Pisos o viviendas en venta (o subasta) en {b['ciudad']} (Galicia, España), en un radio de "
        f"unos {radio_km(cfg):.1f} km de {b['centro']['nombre']} (centro de la ciudad), con al menos "
        f"{b['habitaciones_min']} habitaciones y precio de hasta {b['precio_max']} €. Interesa "
        "especialmente el certificado energético y si tiene garaje o trastero. Busca primero los "
        "más baratos."
    )


def buscar(plataforma: dict, ia, cfg: dict) -> list[Piso]:
    notas = ia.investigar_plataforma(
        plataforma["nombre"], plataforma["dominio"], criterios(cfg),
        cfg["fuentes"].get("max_busquedas_por_plataforma", 5),
    )
    if not notas.strip():
        return []
    anuncios = ia.extraer_anuncios(f"https://{plataforma['dominio']}/", notas)
    dominio = plataforma["dominio"].removeprefix("www.")
    pisos = []
    for a in anuncios:
        # Solo fichas del propio dominio: evita URLs inventadas o de otras webs.
        if dominio not in (a.get("url") or ""):
            continue
        p = portales.a_piso(plataforma["nombre"], a)
        if p:
            pisos.append(p)
    log.info("%s: %d anuncios", plataforma["nombre"], len(pisos))
    return pisos
