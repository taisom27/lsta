"""Búsqueda con la API oficial de Idealista (https://developers.idealista.com/access-request)."""
from __future__ import annotations

import base64
import logging
import os

import requests

from ..modelos import Piso

log = logging.getLogger(__name__)

URL_TOKEN = "https://api.idealista.com/oauth/token"
URL_BUSQUEDA = "https://api.idealista.com/3.5/es/search"


def _token(clave: str, secreto: str) -> str:
    cred = base64.b64encode(f"{clave}:{secreto}".encode()).decode()
    r = requests.post(
        URL_TOKEN,
        headers={"Authorization": f"Basic {cred}"},
        data={"grant_type": "client_credentials", "scope": "read"},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["access_token"]


def a_piso(e: dict) -> Piso:
    parking = e.get("parkingSpace") or {}
    return Piso(
        id=f"idealista:{e['propertyCode']}",
        fuente="idealista",
        url=e.get("url") or f"https://www.idealista.com/inmueble/{e['propertyCode']}/",
        titulo=(e.get("suggestedTexts") or {}).get("title") or e.get("address", ""),
        precio=int(e["price"]),
        habitaciones=e.get("rooms"),
        metros=e.get("size"),
        direccion=e.get("address", ""),
        barrio=e.get("neighborhood") or e.get("district") or "",
        lat=e.get("latitude"),
        lon=e.get("longitude"),
        garaje=bool(parking.get("hasParkingSpace")),
        ascensor=e.get("hasLift"),
        planta=str(e.get("floor") or ""),
        descripcion=e.get("description", ""),
        foto=e.get("thumbnail", ""),
    )


def buscar(cfg: dict, radio_km: float) -> list[Piso]:
    clave, secreto = os.environ.get("IDEALISTA_API_KEY"), os.environ.get("IDEALISTA_API_SECRET")
    if not (clave and secreto):
        log.info("Idealista: faltan IDEALISTA_API_KEY / IDEALISTA_API_SECRET, se omite")
        return []
    b = cfg["busqueda"]
    token = _token(clave, secreto)
    pisos: list[Piso] = []
    for pagina in range(1, cfg["fuentes"]["idealista"].get("max_paginas", 5) + 1):
        r = requests.post(
            URL_BUSQUEDA,
            headers={"Authorization": f"Bearer {token}"},
            data={
                "operation": "sale",
                "propertyType": "homes",
                "center": f"{b['centro']['lat']},{b['centro']['lon']}",
                # Margen extra: la distancia exacta se filtra después.
                "distance": int(max(radio_km, 0.5) * 1000 * 1.2),
                "maxPrice": b["precio_max"],
                "bedrooms": ",".join(str(n) for n in range(b["habitaciones_min"], 5)),
                "order": "price",
                "sort": "asc",
                "maxItems": 50,
                "numPage": pagina,
                "language": "es",
            },
            timeout=30,
        )
        r.raise_for_status()
        datos = r.json()
        pisos += [a_piso(e) for e in datos.get("elementList", [])]
        if pagina >= datos.get("totalPages", 1):
            break
    log.info("Idealista: %d anuncios", len(pisos))
    return pisos
