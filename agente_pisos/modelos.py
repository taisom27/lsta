from __future__ import annotations

from dataclasses import asdict, dataclass, field

# Metros por minuto según el modo de desplazamiento (distancia en línea recta).
VELOCIDAD_M_MIN = {"andando": 80, "bus": 250, "coche": 500}


@dataclass
class Piso:
    id: str
    fuente: str
    url: str
    titulo: str
    precio: int
    habitaciones: int | None = None
    metros: float | None = None
    direccion: str = ""
    barrio: str = ""
    lat: float | None = None
    lon: float | None = None
    distancia_km: float | None = None
    minutos_centro: float | None = None
    energia: str | None = None  # "A".."G", "en trámite", "exento" o None
    garaje: bool = False
    trastero: bool = False
    ascensor: bool | None = None
    planta: str = ""
    obra_nueva: bool = False
    descripcion: str = ""
    foto: str = ""
    analisis: str = ""
    otras_fuentes: list[str] = field(default_factory=list)

    @property
    def precio_m2(self) -> int | None:
        if self.metros:
            return round(self.precio / self.metros)
        return None

    @property
    def tiene_extras(self) -> bool:
        return self.garaje or self.trastero

    @property
    def energia_letra(self) -> str | None:
        if self.energia and len(self.energia) == 1:
            return self.energia
        return None

    def calcular_minutos(self, modo: str) -> None:
        if self.distancia_km is not None:
            self.minutos_centro = round(self.distancia_km * 1000 / VELOCIDAD_M_MIN[modo], 1)

    def a_dict(self) -> dict:
        return asdict(self)
