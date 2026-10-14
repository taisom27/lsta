"""Recuerda los pisos ya avisados para enviar solo novedades y bajadas de precio."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from .modelos import Piso

RUTA = Path("data/vistos.json")


class Almacen:
    def __init__(self, ruta: Path = RUTA):
        self.ruta = ruta
        self.datos: dict[str, dict] = {}
        if ruta.exists():
            self.datos = json.loads(ruta.read_text(encoding="utf-8"))

    def clasificar(self, pisos: list[Piso]) -> tuple[list[Piso], list[tuple[Piso, int]]]:
        """Devuelve (nuevos, [(piso, precio_anterior)] con bajada de precio) y los registra."""
        hoy = date.today().isoformat()
        nuevos, bajadas = [], []
        for p in pisos:
            previo = self.datos.get(p.id)
            if previo is None:
                nuevos.append(p)
                self.datos[p.id] = {"precio": p.precio, "visto": hoy, "ultimo": hoy, "url": p.url}
                continue
            if p.precio < previo["precio"]:
                bajadas.append((p, previo["precio"]))
            previo.update(precio=p.precio, ultimo=hoy)
        return nuevos, bajadas

    def guardar(self) -> None:
        self.ruta.parent.mkdir(parents=True, exist_ok=True)
        self.ruta.write_text(json.dumps(self.datos, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
