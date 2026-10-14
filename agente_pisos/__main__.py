"""Ejecuta una ronda de búsqueda:  python -m agente_pisos [--prueba] [--todos]"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from typing import Callable

from . import informe, texto
from .almacen import Almacen
from .avisos import email, whatsapp
from .config import cargar, radio_km
from .filtros import calcular_distancia, motivo_descarte, ordenar, quitar_duplicados
from .fuentes import idealista, plataformas, portales
from .geo import Geocodificador
from .modelos import Piso

log = logging.getLogger("agente_pisos")


def _en_paralelo(tareas: list, hilos: int) -> list:
    """Ejecuta las funciones a la vez (casi todo es esperar a la red) y devuelve sus
    resultados en el mismo orden; si una falla, su resultado es la excepción."""
    def ejecutar_una(f):
        try:
            return f()
        except Exception as e:
            return e
    if not tareas:
        return []
    with ThreadPoolExecutor(max_workers=max(1, min(hilos, len(tareas)))) as pool:
        return list(pool.map(ejecutar_una, tareas))


def recoger(cfg: dict, ia, errores: list[str]) -> list[Piso]:
    tareas: list[tuple[str, Callable[[], list[Piso]]]] = []
    if cfg["fuentes"]["idealista"].get("activo"):
        tareas.append(("Idealista", lambda: idealista.buscar(cfg, radio_km(cfg))))
    for portal in cfg["fuentes"].get("portales") or []:
        if ia is None:
            errores.append(f"{portal['nombre']}: falta ANTHROPIC_API_KEY para leer portales web")
            continue
        tareas.append((portal["nombre"], lambda portal=portal: portales.buscar(portal, ia)))
    for plataforma in cfg["fuentes"].get("plataformas") or []:
        if ia is None:
            errores.append(f"{plataforma['nombre']}: falta ANTHROPIC_API_KEY para buscar en la plataforma")
            continue
        tareas.append((plataforma["nombre"], lambda plataforma=plataforma: plataformas.buscar(plataforma, ia, cfg)))

    pisos: list[Piso] = []
    resultados = _en_paralelo([f for _, f in tareas], cfg["fuentes"].get("hilos", 8))
    for (nombre, _), r in zip(tareas, resultados):
        if isinstance(r, Exception):  # una fuente caída no debe parar el resto
            errores.append(f"{nombre}: {r}")
        else:
            pisos += r
    return pisos


def _leer_ficha(p: Piso, ia) -> None:
    pagina = portales.descargar_texto(p.url)
    p.energia = texto.energia(pagina) or (ia.buscar_energia(p.url, pagina) if ia else None) or p.energia
    p.garaje = p.garaje or texto.menciona_garaje(pagina)
    p.trastero = p.trastero or texto.menciona_trastero(pagina)


def completar_energia(pisos: list[Piso], ia, maximo: int, errores: list[str], hilos: int = 8) -> None:
    """Abre la ficha de los pisos sin certificado energético para buscarlo."""
    a_revisar = [p for p in pisos if not p.energia_letra][:maximo]
    resultados = _en_paralelo([lambda p=p: _leer_ficha(p, ia) for p in a_revisar], hilos)
    for p, r in zip(a_revisar, resultados):
        if isinstance(r, Exception):
            log.warning("No se pudo leer la ficha %s: %s", p.url, r)
    sin = sum(1 for p in pisos if not p.energia_letra)
    if sin > maximo:
        errores.append(f"{sin - maximo} pisos se quedaron sin revisar su ficha (límite max_fichas_por_ejecucion)")


def ejecutar(cfg: dict, prueba: bool, todos: bool) -> int:
    errores: list[str] = []
    ia = None
    if os.environ.get("ANTHROPIC_API_KEY"):
        from .ia import ClaudeInmobiliario
        ia = ClaudeInmobiliario(cfg["ia"]["modelo"], cfg["ia"].get("esfuerzo", "low"))

    pisos = quitar_duplicados(recoger(cfg, ia, errores))
    for p in pisos:
        texto.enriquecer(p)
    pisos = [p for p in pisos if motivo_descarte(p, cfg, comprobar_energia=False) not in ("precio", "habitaciones")]

    geo = Geocodificador(cfg["busqueda"]["ciudad"])
    for p in pisos:
        if p.lat is None and (p.direccion or p.barrio):
            coords = geo.buscar(p.direccion or p.barrio) or (geo.buscar(p.barrio) if p.barrio and p.direccion else None)
            if coords:
                p.lat, p.lon = coords
        calcular_distancia(p, cfg)
    geo.guardar()

    candidatos = [p for p in pisos if motivo_descarte(p, cfg, comprobar_energia=False) is None]
    almacen = Almacen()
    if cfg["fuentes"].get("consultar_ficha_si_falta_energia"):
        sin_avisar = [p for p in candidatos if p.id not in almacen.datos]
        completar_energia(
            sin_avisar, ia, cfg["fuentes"].get("max_fichas_por_ejecucion", 25), errores, cfg["fuentes"].get("hilos", 8)
        )
    validos = ordenar([p for p in candidatos if motivo_descarte(p, cfg) is None])
    log.info("%d anuncios recogidos, %d cumplen los criterios", len(pisos), len(validos))

    nuevos, bajadas = almacen.clasificar(validos)
    if todos:
        nuevos = validos

    if ia and cfg["ia"].get("analizar_novedades") and (nuevos or bajadas):
        a_valorar = nuevos + [p for p, _ in bajadas]
        precios_m2 = [p.precio_m2 for p in validos if p.precio_m2]
        contexto = (
            f"Hay {len(validos)} pisos que cumplen los criterios del comprador."
            + (f" Precio/m² medio entre ellos: {sum(precios_m2) / len(precios_m2):.0f} €." if precios_m2 else "")
        )
        try:
            valoraciones = ia.valorar(a_valorar[:40], contexto)
            for p in a_valorar:
                p.analisis = valoraciones.get(p.id, "")
        except Exception as e:
            errores.append(f"Valoración IA: {e}")

    for e in errores:
        log.warning(e)

    if not (nuevos or bajadas):
        log.info("Sin novedades")
        if not prueba:
            almacen.guardar()
        return 0

    msg_wa = informe.whatsapp(nuevos, bajadas, cfg)
    html = informe.email_html(nuevos, bajadas, validos, cfg, errores)
    asunto = f"🏠 {len(nuevos)} piso(s) nuevo(s) en A Coruña" + (f", {len(bajadas)} bajada(s)" if bajadas else "")
    if nuevos:
        asunto += f" · desde {informe.euros(nuevos[0].precio)}"

    if prueba:
        print(msg_wa)
        with open("data/ultimo_informe.html", "w", encoding="utf-8") as f:
            f.write(html)
        log.info("Modo prueba: no se envía nada ni se guarda el estado (informe en data/ultimo_informe.html)")
        return 0

    fallos = 0
    if cfg["avisos"].get("whatsapp"):
        try:
            whatsapp.enviar(msg_wa, cfg["avisos"].get("whatsapp_proveedor", "callmebot"))
        except Exception as e:
            fallos += 1
            log.error("WhatsApp: %s", e)
    if cfg["avisos"].get("email"):
        try:
            email.enviar(asunto, html, msg_wa)
        except Exception as e:
            fallos += 1
            log.error("Email: %s", e)
    canales = sum(bool(cfg["avisos"].get(c)) for c in ("whatsapp", "email"))
    if canales and fallos == canales:
        log.error("No se pudo avisar por ningún canal; no se marcan los pisos como vistos")
        return 1
    almacen.guardar()
    return 0


def main() -> None:
    ap = argparse.ArgumentParser(description="Agente que busca pisos en A Coruña")
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--prueba", action="store_true", help="no envía avisos, imprime el resultado")
    ap.add_argument("--todos", action="store_true", help="incluye todos los pisos válidos, no solo los nuevos")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    sys.exit(ejecutar(cargar(args.config), args.prueba, args.todos))


if __name__ == "__main__":
    main()
