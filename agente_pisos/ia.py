"""Uso de Claude: leer páginas de portales, encontrar el certificado energético y valorar pisos."""
from __future__ import annotations

import json
import logging

import anthropic

log = logging.getLogger(__name__)

# Si el texto de una página supera esto, se avisa: probablemente no es una página de resultados.
MAX_CARACTERES = 400_000


def _nullable(tipo: str) -> dict:
    return {"anyOf": [{"type": tipo}, {"type": "null"}]}


def _objeto(props: dict) -> dict:
    return {"type": "object", "properties": props, "required": list(props), "additionalProperties": False}


ESQUEMA_ANUNCIOS = _objeto({
    "anuncios": {
        "type": "array",
        "items": _objeto({
            "url": {"type": "string"},
            "titulo": {"type": "string"},
            "precio": _nullable("integer"),
            "habitaciones": _nullable("integer"),
            "metros": _nullable("number"),
            "direccion": {"type": "string"},
            "barrio": {"type": "string"},
            "calificacion_energetica": _nullable("string"),
            "garaje": {"type": "boolean"},
            "trastero": {"type": "boolean"},
            "ascensor": _nullable("boolean"),
            "planta": {"type": "string"},
            "descripcion": {"type": "string"},
        }),
    }
})

ESQUEMA_ENERGIA = _objeto({"calificacion_energetica": _nullable("string")})

ESQUEMA_ANALISIS = _objeto({
    "valoraciones": {
        "type": "array",
        "items": _objeto({"id": {"type": "string"}, "valoracion": {"type": "string"}}),
    }
})

SISTEMA_EXTRACCION = (
    "Eres un asistente que lee páginas de portales inmobiliarios españoles y extrae los "
    "anuncios de viviendas en venta exactamente como aparecen. No inventes datos: si un campo "
    "no aparece, usa null (o cadena vacía / false según el tipo). Las URL deben ser absolutas; "
    "si en la página aparecen relativas, complétalas con el dominio de la página. "
    "calificacion_energetica: solo la letra A-G del consumo, o 'en trámite' / 'exento' si así "
    "se indica. Ignora publicidad, promociones de obra nueva destacadas que no sean anuncios "
    "y anuncios de alquiler."
)


class ClaudeInmobiliario:
    def __init__(self, modelo: str, esfuerzo: str = "low"):
        self.cliente = anthropic.Anthropic()
        self.modelo = modelo
        self.esfuerzo = esfuerzo

    def _json(self, esquema: dict, sistema: str, contenido: str) -> dict:
        resp = self.cliente.beta.messages.create(
            model=self.modelo,
            max_tokens=16000,
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            output_config={
                "effort": self.esfuerzo,
                "format": {"type": "json_schema", "schema": esquema},
            },
            system=sistema,
            messages=[{"role": "user", "content": contenido}],
        )
        if resp.stop_reason == "refusal":
            raise RuntimeError("Claude rechazó la petición")
        if resp.stop_reason == "max_tokens":
            raise RuntimeError("La respuesta de Claude se cortó (max_tokens)")
        texto = "".join(b.text for b in resp.content if b.type == "text")
        return json.loads(texto)

    def extraer_anuncios(self, url: str, texto_pagina: str) -> list[dict]:
        if len(texto_pagina) > MAX_CARACTERES:
            log.warning("La página %s es muy larga (%d caracteres)", url, len(texto_pagina))
        datos = self._json(
            ESQUEMA_ANUNCIOS,
            SISTEMA_EXTRACCION,
            f"URL de la página: {url}\n\nContenido de la página:\n{texto_pagina}",
        )
        return datos["anuncios"]

    def buscar_energia(self, url: str, texto_ficha: str) -> str | None:
        datos = self._json(
            ESQUEMA_ENERGIA,
            "Lee la ficha de un piso en venta y devuelve la letra (A-G) de su calificación "
            "energética de consumo, 'en trámite', 'exento', o null si la ficha no la indica. "
            "No la deduzcas: solo si aparece escrita.",
            f"URL: {url}\n\n{texto_ficha}",
        )
        return datos["calificacion_energetica"]

    def valorar(self, pisos: list, contexto: str) -> dict[str, str]:
        """Devuelve {id: valoración breve} para cada piso."""
        if not pisos:
            return {}
        fichas = [
            {
                "id": p.id, "precio": p.precio, "metros": p.metros, "precio_m2": p.precio_m2,
                "habitaciones": p.habitaciones, "planta": p.planta, "ascensor": p.ascensor,
                "barrio": p.barrio or p.direccion, "minutos_al_centro": p.minutos_centro,
                "energia": p.energia, "garaje": p.garaje, "trastero": p.trastero,
                "descripcion": p.descripcion[:1500],
            }
            for p in pisos
        ]
        datos = self._json(
            ESQUEMA_ANALISIS,
            "Eres un agente inmobiliario honesto en A Coruña que asesora a un comprador. Para "
            "cada piso escribe una valoración de máximo 2 frases en español: lo mejor y la "
            "principal pega o riesgo (p. ej. sin ascensor en planta alta, bajo, a reformar, "
            "precio/m² alto o bajo respecto al resto, certificado energético malo o ausente). "
            "Basa la valoración solo en los datos dados.",
            f"{contexto}\n\nPisos:\n{json.dumps(fichas, ensure_ascii=False)}",
        )
        return {v["id"]: v["valoracion"] for v in datos["valoraciones"]}
