"""Formato de los avisos (WhatsApp en texto, email en HTML)."""
from __future__ import annotations

from html import escape

from .modelos import Piso


def euros(n: int | float) -> str:
    return f"{n:,.0f} €".replace(",", ".")


def _energia(p: Piso) -> str:
    return p.energia or "sin indicar"


def _extras(p: Piso) -> str:
    e = [x for x, si in (("garaje", p.garaje), ("trastero", p.trastero)) if si]
    return " + ".join(e)


def _subasta(p: Piso) -> str:
    if p.tipo_venta != "subasta":
        return ""
    return "🔨 subasta" + (f" hasta {p.fin_subasta}" if p.fin_subasta else "")


def _minutos(p: Piso, modo: str) -> str:
    return f"{p.minutos_centro:.0f} min {modo}" if p.minutos_centro is not None else "distancia ?"


def linea_whatsapp(i: int, p: Piso, modo: str, precio_antes: int | None = None) -> str:
    estrella = "⭐ " if p.tiene_extras else ""
    precio = euros(p.precio)
    if precio_antes:
        precio += f" (antes {euros(precio_antes)})"
    datos = [f"{p.habitaciones} hab"]
    if p.metros:
        datos.append(f"{p.metros:.0f} m²")
    datos += [f"⚡{_energia(p)}", _minutos(p, modo)]
    if _extras(p):
        datos.append(_extras(p))
    if _subasta(p):
        datos.append(_subasta(p))
    lineas = [f"{i}. {estrella}*{precio}* · {' · '.join(datos)}", f"   📍 {p.barrio or p.direccion or '-'} ({p.fuente})"]
    if p.analisis:
        lineas.append(f"   💬 {p.analisis}")
    lineas.append(f"   {p.url}")
    return "\n".join(lineas)


def whatsapp(nuevos: list[Piso], bajadas: list[tuple[Piso, int]], cfg: dict) -> str:
    modo = cfg["busqueda"]["modo"]
    maximo = cfg["avisos"].get("max_whatsapp", 10)
    partes = ["🏠 *Agente de pisos · A Coruña*"]
    if nuevos:
        partes.append(f"\n*{len(nuevos)} piso(s) nuevo(s)*, del más barato al más caro:")
        partes += [linea_whatsapp(i, p, modo) for i, p in enumerate(nuevos[:maximo], 1)]
        if len(nuevos) > maximo:
            partes.append(f"…y {len(nuevos) - maximo} más en el email.")
    if bajadas:
        partes.append(f"\n📉 *{len(bajadas)} bajada(s) de precio:*")
        partes += [linea_whatsapp(i, p, modo, antes) for i, (p, antes) in enumerate(bajadas[:maximo], 1)]
    return "\n".join(partes)


def _fila(p: Piso, modo: str, precio_antes: int | None = None) -> str:
    precio = euros(p.precio)
    if precio_antes:
        precio += f"<br><small><s>{euros(precio_antes)}</s></small>"
    if _subasta(p):
        precio += f"<br><small>{escape(_subasta(p))}</small>"
    m2 = f"{p.metros:.0f} m²<br><small>{euros(p.precio_m2)}/m²</small>" if p.metros else "?"
    extras = "⭐ " + _extras(p) if p.tiene_extras else "—"
    analisis = f"<br><small>💬 {escape(p.analisis)}</small>" if p.analisis else ""
    return (
        "<tr>"
        f"<td><b>{precio}</b></td>"
        f"<td>{p.habitaciones}</td><td>{m2}</td>"
        f"<td>{escape(_energia(p))}</td>"
        f"<td>{escape(_minutos(p, modo))}</td>"
        f"<td>{extras}</td>"
        f"<td><a href=\"{escape(p.url)}\">{escape(p.titulo or p.direccion or 'Ver anuncio')}</a>"
        f"<br><small>{escape(p.barrio or p.direccion)} · {escape(p.fuente)}</small>{analisis}</td>"
        "</tr>"
    )


def _tabla(titulo: str, filas: list[str]) -> str:
    cab = "".join(f"<th>{c}</th>" for c in ("Precio", "Hab.", "Tamaño", "Energía", "Al centro", "Extras", "Anuncio"))
    return (
        f"<h2>{titulo}</h2>"
        "<table border=\"1\" cellpadding=\"6\" cellspacing=\"0\" style=\"border-collapse:collapse;font-family:sans-serif;font-size:14px\">"
        f"<tr style=\"background:#eee\">{cab}</tr>{''.join(filas)}</table>"
    )


def email_html(
    nuevos: list[Piso], bajadas: list[tuple[Piso, int]], todos: list[Piso], cfg: dict, errores: list[str]
) -> str:
    b = cfg["busqueda"]
    modo = b["modo"]
    resumen = (
        f"Pisos en venta en {escape(b['ciudad'])} a ≤{b['minutos_max']} min {modo} de "
        f"{escape(b['centro']['nombre'])}, {b['habitaciones_min']}+ habitaciones, hasta {euros(b['precio_max'])}. "
        "Ordenados del más barato al más caro; ⭐ = con garaje o trastero; "
        "🔨 = subasta (el precio es el de salida, el final suele ser mayor)."
    )
    html = [f"<p style=\"font-family:sans-serif\">{resumen}</p>"]
    if nuevos:
        html.append(_tabla(f"Nuevos ({len(nuevos)})", [_fila(p, modo) for p in nuevos]))
    if bajadas:
        html.append(_tabla(f"Bajadas de precio ({len(bajadas)})", [_fila(p, modo, a) for p, a in bajadas]))
    con_extras = [p for p in todos if p.tiene_extras]
    if con_extras:
        html.append(_tabla(f"⭐ Con garaje o trastero ({len(con_extras)})", [_fila(p, modo) for p in con_extras[:15]]))
    html.append(_tabla(f"Todos los que cumplen ahora mismo ({len(todos)})", [_fila(p, modo) for p in todos[:50]]))
    if errores:
        html.append("<p style=\"font-family:sans-serif;color:#a00\"><b>Avisos:</b><br>" + "<br>".join(escape(e) for e in errores) + "</p>")
    return "\n".join(html)
