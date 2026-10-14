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
            "tipo_venta": {"type": "string", "enum": ["venta", "subasta"]},
            "fin_subasta": {"type": "string"},
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
    "y anuncios de alquiler. tipo_venta: 'subasta' si es una subasta (precio = precio de "
    "salida o puja actual) y fin_subasta con la fecha en que termina, si aparece."
)

SISTEMA_INVESTIGACION = (
    "Eres un agente inmobiliario que busca viviendas en venta para un comprador. Busca SOLO en "
    "el sitio web indicado (bancos, servicers y plataformas de subastas). Usa la búsqueda web "
    "y abre las páginas de resultados y las fichas de los inmuebles para comprobar los datos. "
    "Ignora locales, garajes sueltos, terrenos, naves, vehículos y alquileres. Al terminar, "
    "escribe una lista con CADA vivienda encontrada que pueda cumplir los criterios: URL de la "
    "ficha, título, precio (o precio de salida si es subasta y la fecha de fin), habitaciones, "
    "metros, dirección o barrio, certificado energético, garaje, trastero, ascensor y planta. "
    "No inventes datos ni URLs: pon solo lo que hayas visto. Si no encuentras ninguna, dilo."
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

    def investigar_plataforma(self, nombre: str, dominio: str, criterios: str, max_busquedas: int) -> str:
        """Busca viviendas en un dominio con las herramientas web de Claude; devuelve sus notas."""
        herramientas = [
            {"type": "web_search_20260209", "name": "web_search", "max_uses": max_busquedas,
             "allowed_domains": [dominio], "user_location": {"type": "approximate", "country": "ES",
                                                             "region": "Galicia", "city": "A Coruña"}},
            {"type": "web_fetch_20260209", "name": "web_fetch", "max_uses": max_busquedas * 3,
             "allowed_domains": [dominio]},
        ]
        mensajes = [{"role": "user", "content": f"Sitio: {nombre} ({dominio})\n\nCriterios: {criterios}"}]
        notas = []
        for _ in range(5):  # reanuda si la búsqueda se pausa (pause_turn)
            resp = self.cliente.beta.messages.create(
                model=self.modelo,
                max_tokens=16000,
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
                output_config={"effort": self.esfuerzo},
                system=SISTEMA_INVESTIGACION,
                tools=herramientas,
                messages=mensajes,
            )
            notas += [b.text for b in resp.content if b.type == "text"]
            if resp.stop_reason == "refusal":
                raise RuntimeError("Claude rechazó la petición")
            if resp.stop_reason != "pause_turn":
                break
            if len(mensajes) == 1:
                mensajes.append({"role": "assistant", "content": resp.content})
            else:
                mensajes[-1] = {"role": "assistant", "content": list(mensajes[-1]["content"]) + list(resp.content)}
        return "\n".join(notas)

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
