"""Lista de «mis dispositivos». Se guarda en el equipo del usuario, nunca en el repositorio."""
from __future__ import annotations

import json
import os
from pathlib import Path

from .bluez import normalizar_mac


def ruta_por_defecto() -> Path:
    return Path(os.environ.get("GUARDIAN_BT_LISTA") or Path.home() / ".config" / "guardian-bluetooth" / "mis_dispositivos.json")


class MisDispositivos:
    def __init__(self, ruta: Path | None = None):
        self.ruta = Path(ruta or ruta_por_defecto())
        self.dispositivos: dict[str, str] = {}
        if self.ruta.exists():
            self.dispositivos = {normalizar_mac(k): v for k, v in json.loads(self.ruta.read_text(encoding="utf-8")).items()}

    def guardar(self) -> None:
        self.ruta.parent.mkdir(parents=True, exist_ok=True)
        self.ruta.write_text(json.dumps(self.dispositivos, ensure_ascii=False, indent=2), encoding="utf-8")

    def anadir(self, mac: str, nombre: str = "") -> str:
        mac = normalizar_mac(mac)
        self.dispositivos[mac] = nombre or self.dispositivos.get(mac, "") or mac
        self.guardar()
        return mac

    def quitar(self, mac: str) -> bool:
        borrado = self.dispositivos.pop(normalizar_mac(mac), None) is not None
        self.guardar()
        return borrado

    def __contains__(self, mac: str) -> bool:
        return mac.upper() in self.dispositivos

    def nombre(self, mac: str) -> str:
        return self.dispositivos.get(mac.upper(), mac)
