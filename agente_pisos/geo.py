from __future__ import annotations

import json
import logging
import math
import time
from pathlib import Path

import requests

log = logging.getLogger(__name__)

NOMINATIM = "https://nominatim.openstreetmap.org/search"
CACHE = Path("data/geocache.json")


def distancia_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


class Geocodificador:
    """Convierte direcciones en coordenadas con OpenStreetMap (gratis, 1 consulta/s)."""

    def __init__(self, ciudad: str, cache: Path = CACHE):
        self.ciudad = ciudad
        self.cache_path = cache
        self.cache: dict[str, list[float] | None] = {}
        if cache.exists():
            self.cache = json.loads(cache.read_text(encoding="utf-8"))
        self._ultima = 0.0

    def buscar(self, direccion: str) -> tuple[float, float] | None:
        clave = f"{direccion}, {self.ciudad}".strip().lower()
        if clave in self.cache:
            v = self.cache[clave]
            return tuple(v) if v else None
        espera = 1.1 - (time.monotonic() - self._ultima)
        if espera > 0:
            time.sleep(espera)
        self._ultima = time.monotonic()
        try:
            r = requests.get(
                NOMINATIM,
                params={"q": f"{direccion}, {self.ciudad}, España", "format": "json", "limit": 1},
                headers={"User-Agent": "agente-pisos-coruna/1.0"},
                timeout=20,
            )
            r.raise_for_status()
            datos = r.json()
        except (requests.RequestException, ValueError) as e:
            log.warning("No se pudo geolocalizar '%s': %s", direccion, e)
            return None
        coords = (float(datos[0]["lat"]), float(datos[0]["lon"])) if datos else None
        self.cache[clave] = list(coords) if coords else None
        return coords

    def guardar(self) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_path.write_text(json.dumps(self.cache, ensure_ascii=False, indent=1), encoding="utf-8")
