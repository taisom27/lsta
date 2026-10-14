from __future__ import annotations

from pathlib import Path

import yaml

from .modelos import VELOCIDAD_M_MIN


def cargar(ruta: str | Path = "config.yaml") -> dict:
    with open(ruta, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    modo = cfg["busqueda"]["modo"]
    if modo not in VELOCIDAD_M_MIN:
        raise ValueError(f"modo '{modo}' no válido; usa uno de {sorted(VELOCIDAD_M_MIN)}")
    return cfg


def radio_km(cfg: dict) -> float:
    b = cfg["busqueda"]
    return b["minutos_max"] * VELOCIDAD_M_MIN[b["modo"]] / 1000
