"""Decide qué alertas dar a partir de lo que ve el Bluetooth. Sin efectos secundarios."""
from __future__ import annotations

from dataclasses import dataclass, field

from .bluez import Dispositivo
from .lista import MisDispositivos

CERCA_RSSI = -70  # dBm: más fuerte que esto suele ser la misma casa o la de al lado
ESCANEOS_PARA_SOSPECHAR = 3


@dataclass(frozen=True)
class Alerta:
    clave: str  # identifica la situación para no repetir el aviso mientras siga igual
    nivel: str  # "aviso" | "peligro"
    texto: str
    mac: str = ""


def revisar_visibles(visibles: dict[str, Dispositivo], mios: MisDispositivos) -> list[Alerta]:
    """Tus aparatos de Bluetooth clásico que aparecen en una búsqueda están en modo visible/emparejamiento:
    en ese momento cualquiera cerca (por ejemplo, un vecino) puede verlos e intentar conectarse."""
    alertas = []
    for mac, d in visibles.items():
        if mac in mios and d.clasico:
            nombre = mios.nombre(mac)
            alertas.append(
                Alerta(
                    f"visible:{mac}",
                    "peligro",
                    f"«{nombre}» está en modo emparejamiento y cualquiera cercano puede conectarse. "
                    "Conéctalo ya a tu móvil o apágalo.",
                    mac,
                )
            )
    return alertas


def revisar_equipo(emparejados: list[Dispositivo], conectados: list[Dispositivo], mios: MisDispositivos) -> list[Alerta]:
    """Dispositivos ajenos emparejados o conectados a ESTE equipo."""
    alertas = []
    for d in conectados:
        if d.mac not in mios:
            texto = f"Un dispositivo que no es tuyo está conectado a este equipo: {d.nombre or d.mac}"
            alertas.append(Alerta(f"conectado:{d.mac}", "peligro", texto, d.mac))
    ya = {a.mac for a in alertas}
    for d in emparejados:
        if d.mac not in mios and d.mac not in ya:
            texto = f"Dispositivo emparejado que no está en tu lista: {d.nombre or d.mac}"
            alertas.append(Alerta(f"emparejado:{d.mac}", "aviso", texto, d.mac))
    return alertas


@dataclass
class Vigilante:
    """Guarda el estado entre búsquedas para avisar solo de lo nuevo."""

    mios: MisDispositivos
    vigilar_desconocidos: bool = False
    activas: set[str] = field(default_factory=set)
    vistos: dict[str, int] = field(default_factory=dict)

    def revisar(self, visibles: dict[str, Dispositivo], emparejados: list[Dispositivo], conectados: list[Dispositivo]) -> list[Alerta]:
        alertas = revisar_visibles(visibles, self.mios) + revisar_equipo(emparejados, conectados, self.mios)
        if self.vigilar_desconocidos:
            alertas += self._desconocidos_cerca(visibles)
        claves = {a.clave for a in alertas}
        nuevas = [a for a in alertas if a.clave not in self.activas]
        # Las de desconocidos se avisan una sola vez; el resto vuelve a sonar si desaparece y reaparece.
        self.activas = claves | {c for c in self.activas if c.startswith("cerca:")}
        return nuevas

    def _desconocidos_cerca(self, visibles: dict[str, Dispositivo]) -> list[Alerta]:
        alertas = []
        for mac, d in visibles.items():
            if mac in self.mios or d.rssi is None or d.rssi < CERCA_RSSI:
                continue
            self.vistos[mac] = self.vistos.get(mac, 0) + 1
            if self.vistos[mac] >= ESCANEOS_PARA_SOSPECHAR:
                texto = f"Dispositivo desconocido muy cerca de forma continuada: {d.nombre or mac} ({d.rssi} dBm)"
                alertas.append(Alerta(f"cerca:{mac}", "aviso", texto, mac))
        return alertas
