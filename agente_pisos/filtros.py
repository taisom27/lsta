from __future__ import annotations

import re

from .config import radio_km
from .geo import distancia_km
from .modelos import Piso


def calcular_distancia(p: Piso, cfg: dict) -> None:
    c = cfg["busqueda"]["centro"]
    if p.lat is not None and p.lon is not None:
        p.distancia_km = round(distancia_km(c["lat"], c["lon"], p.lat, p.lon), 2)
        p.calcular_minutos(cfg["busqueda"]["modo"])


def motivo_descarte(p: Piso, cfg: dict, comprobar_energia: bool = True) -> str | None:
    """None si el piso cumple todos los criterios; si no, el motivo."""
    b = cfg["busqueda"]
    if p.precio > b["precio_max"]:
        return "precio"
    if p.habitaciones is not None and p.habitaciones < b["habitaciones_min"]:
        return "habitaciones"
    if p.habitaciones is None:
        return "habitaciones desconocidas"
    if b.get("solo_segunda_mano") and p.obra_nueva:
        return "obra nueva"
    if p.distancia_km is None:
        if b.get("descartar_sin_ubicacion"):
            return "ubicación desconocida"
    elif p.distancia_km > radio_km(cfg):
        return "lejos del centro"
    if comprobar_energia and b.get("exigir_calificacion_energetica") and not p.energia_letra:
        return "sin calificación energética"
    return None


def ordenar(pisos: list[Piso]) -> list[Piso]:
    """Del más barato al más caro; a igual precio, primero los que tienen garaje/trastero."""
    return sorted(pisos, key=lambda p: (p.precio, not p.tiene_extras, -(p.metros or 0)))


def _clave_duplicado(p: Piso) -> tuple:
    calle = re.sub(r"\W+", "", (p.direccion or p.barrio).lower())[:20]
    return (p.precio, round(p.metros or 0), p.habitaciones, calle)


def quitar_duplicados(pisos: list[Piso]) -> list[Piso]:
    """El mismo piso publicado en varios portales se queda una vez (con los datos combinados)."""
    unicos: dict[tuple, Piso] = {}
    por_id: set[str] = set()
    for p in pisos:
        if p.id in por_id:
            continue
        por_id.add(p.id)
        clave = _clave_duplicado(p)
        if clave not in unicos:
            unicos[clave] = p
            continue
        base = unicos[clave]
        base.otras_fuentes.append(p.url)
        base.energia = base.energia_letra or p.energia_letra or base.energia or p.energia
        base.garaje = base.garaje or p.garaje
        base.trastero = base.trastero or p.trastero
        if base.lat is None and p.lat is not None:
            base.lat, base.lon = p.lat, p.lon
    return list(unicos.values())
