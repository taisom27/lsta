"""Control de Bluetooth en Linux a través de `bluetoothctl` (BlueZ)."""
from __future__ import annotations

import re
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass

_ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]|[\x01\x02\r]")
_MAC = r"(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}"
_RE_MAC = re.compile(rf"^{_MAC}$")
_RE_LISTA = re.compile(rf"^Device ({_MAC})(?: (.*))?$")
_RE_EVENTO = re.compile(rf"\[(NEW|CHG|DEL)\] Device ({_MAC}) ?(.*)$")
_RE_RSSI = re.compile(r"RSSI: (?:0x[0-9a-fA-F]+ \()?(-?\d+)\)?")


@dataclass
class Dispositivo:
    mac: str
    nombre: str = ""
    emparejado: bool = False
    confiado: bool = False
    bloqueado: bool = False
    conectado: bool = False
    rssi: int | None = None
    clase: str | None = None  # solo la tienen los dispositivos de Bluetooth clásico (altavoces, cascos...)

    @property
    def clasico(self) -> bool:
        return self.clase is not None


def normalizar_mac(mac: str) -> str:
    mac = mac.strip().upper().replace("-", ":")
    if not _RE_MAC.match(mac):
        raise ValueError(f"Dirección Bluetooth no válida: {mac!r} (formato AA:BB:CC:DD:EE:FF)")
    return mac


def limpiar(salida: str) -> str:
    return _ANSI.sub("", salida)


def parsear_lista(salida: str) -> list[Dispositivo]:
    """Salida de `bluetoothctl devices`: líneas «Device AA:BB:... Nombre»."""
    dispositivos = []
    for linea in limpiar(salida).splitlines():
        m = _RE_LISTA.match(linea.strip())
        if m:
            dispositivos.append(Dispositivo(mac=m[1].upper(), nombre=(m[2] or "").strip()))
    return dispositivos


def parsear_info(salida: str) -> Dispositivo | None:
    """Salida de `bluetoothctl info MAC`."""
    texto = limpiar(salida)
    m = re.search(rf"Device ({_MAC})", texto)
    if not m:
        return None
    d = Dispositivo(mac=m[1].upper())
    si = lambda clave: re.search(rf"^\s*{clave}: yes", texto, re.M) is not None  # noqa: E731
    d.emparejado, d.confiado, d.bloqueado, d.conectado = si("Paired"), si("Trusted"), si("Blocked"), si("Connected")
    if n := re.search(r"^\s*(?:Alias|Name): (.+)$", texto, re.M):
        d.nombre = n[1].strip()
    if c := re.search(r"^\s*Class: (0x[0-9a-fA-F]+)", texto, re.M):
        d.clase = c[1]
    if r := _RE_RSSI.search(texto):
        d.rssi = int(r[1])
    return d


def parsear_escaneo(salida: str) -> dict[str, Dispositivo]:
    """Dispositivos detectados durante `bluetoothctl scan on`.

    Al arrancar, bluetoothctl lista como [NEW] los aparatos que ya conoce aunque no estén cerca;
    por eso solo cuenta lo que llega después de empezar la búsqueda ("Discovering: yes").
    """
    lineas = limpiar(salida).splitlines()
    inicio = next((i for i, linea in enumerate(lineas) if "Discovering: yes" in linea), -1)
    visibles: dict[str, Dispositivo] = {}
    for linea in lineas[inicio + 1 :]:
        m = _RE_EVENTO.search(linea)
        if not m:
            continue
        tipo, mac, resto = m[1], m[2].upper(), m[3].strip()
        if tipo == "DEL":
            visibles.pop(mac, None)
            continue
        d = visibles.setdefault(mac, Dispositivo(mac=mac))
        if r := _RE_RSSI.search(resto):
            d.rssi = int(r[1])
        elif c := re.match(r"Class: (0x[0-9a-fA-F]+)", resto):
            d.clase = c[1]
        elif n := re.match(r"(?:Name|Alias): (.+)", resto):
            d.nombre = n[1].strip()
        elif tipo == "NEW" and not d.nombre and resto:
            d.nombre = resto
    return visibles


Ejecutor = Callable[[list[str], int], str]


def _subproceso(args: list[str], timeout: int) -> str:
    r = subprocess.run(["bluetoothctl", *args], capture_output=True, text=True, timeout=timeout)
    return r.stdout + r.stderr


class Bluetoothctl:
    def __init__(self, ejecutar: Ejecutor | None = None):
        self._ejecutar = ejecutar or _subproceso

    @staticmethod
    def disponible() -> bool:
        return shutil.which("bluetoothctl") is not None

    def _run(self, *args: str, timeout: int = 15) -> str:
        return self._ejecutar(list(args), timeout)

    def dispositivos(self) -> list[Dispositivo]:
        return parsear_lista(self._run("devices"))

    def emparejados(self) -> list[Dispositivo]:
        salida = self._run("devices", "Paired")
        if "Invalid" in salida or "Usage" in salida:  # BlueZ antiguo (< 5.65)
            salida = self._run("paired-devices")
        return parsear_lista(salida)

    def info(self, mac: str) -> Dispositivo | None:
        return parsear_info(self._run("info", normalizar_mac(mac)))

    def escanear(self, segundos: int = 12) -> dict[str, Dispositivo]:
        return parsear_escaneo(self._run("--timeout", str(segundos), "scan", "on", timeout=segundos + 10))

    def ocultar(self) -> None:
        """Este equipo deja de ser visible y de aceptar emparejamientos nuevos."""
        self._run("discoverable", "off")
        self._run("pairable", "off")

    def expulsar(self, mac: str) -> None:
        """Desconecta, bloquea y olvida un dispositivo en este equipo."""
        mac = normalizar_mac(mac)
        self._run("disconnect", mac)
        self._run("block", mac)
        self._run("remove", mac)
