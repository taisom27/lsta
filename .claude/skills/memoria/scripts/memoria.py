#!/usr/bin/env python3
"""Memoria persistente y manual para Claude Code.

Guarda decisiones, preferencias y pendientes en archivos Markdown locales,
uno por categoría y proyecto, en ~/.claude/memoria/<proyecto>/.
Sin red, sin telemetría y sin leer credenciales.

Uso:
  memoria.py guardar <decision|preferencia|pendiente> "texto"
  memoria.py buscar "consulta"
  memoria.py listar [decision|preferencia|pendiente]
  memoria.py completar <id>      # marca un pendiente como hecho
  memoria.py olvidar <id>        # borra una entrada
  memoria.py resumen             # resumen corto para el inicio de sesión
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

TIPOS = {"decision": "decisiones", "preferencia": "preferencias", "pendiente": "pendientes"}
LETRA = {"decision": "d", "preferencia": "f", "pendiente": "p"}
ENTRADA = re.compile(r"^- \[(?P<id>[a-z]\d+)\] (?P<fecha>\d{4}-\d{2}-\d{2})(?P<hecho> ✅)? · (?P<texto>.*)$")

# Nunca se guardan secretos: claves, tokens ni contraseñas.
SECRETOS = re.compile(
    r"sk-ant-[\w-]{10,}|sk-[A-Za-z0-9]{20,}|ghp_\w{20,}|github_pat_\w{20,}|AKIA[0-9A-Z]{16}"
    r"|xox[bpas]-[\w-]{10,}|-----BEGIN [A-Z ]*PRIVATE KEY-----|eyJ[\w-]{10,}\.[\w-]{10,}\.[\w-]{10,}"
    r"|(?i:(password|contraseña|passwd|secret|token|api[_-]?key)\s*[:=]\s*\S{6,})"
)


def proyecto() -> str:
    raiz = os.environ.get("CLAUDE_PROJECT_DIR")
    if not raiz:
        try:
            raiz = subprocess.run(
                ["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=True
            ).stdout.strip()
        except (OSError, subprocess.CalledProcessError):
            raiz = os.getcwd()
    return re.sub(r"[^\w.-]", "_", Path(raiz).name) or "general"


def carpeta() -> Path:
    base = Path(os.environ.get("MEMORIA_DIR", Path.home() / ".claude" / "memoria"))
    d = base / proyecto()
    d.mkdir(parents=True, exist_ok=True, mode=0o700)
    return d


def archivo(tipo: str) -> Path:
    return carpeta() / f"{TIPOS[tipo]}.md"


def leer(tipo: str) -> list[dict]:
    f = archivo(tipo)
    if not f.exists():
        return []
    return [m.groupdict() | {"tipo": tipo} for linea in f.read_text(encoding="utf-8").splitlines() if (m := ENTRADA.match(linea))]


def escribir(tipo: str, entradas: list[dict]) -> None:
    lineas = [f"# {TIPOS[tipo].capitalize()} · {proyecto()}", ""]
    for e in entradas:
        lineas.append(f"- [{e['id']}] {e['fecha']}{' ✅' if e['hecho'] else ''} · {e['texto']}")
    f = archivo(tipo)
    f.write_text("\n".join(lineas) + "\n", encoding="utf-8")
    f.chmod(0o600)


def todas() -> list[dict]:
    return [e for t in TIPOS for e in leer(t)]


def buscar_id(id_: str) -> dict | None:
    return next((e for e in todas() if e["id"] == id_), None)


def guardar(tipo: str, texto: str) -> str:
    texto = " ".join(texto.split())
    if not texto:
        raise SystemExit("Texto vacío: no se guarda nada.")
    if SECRETOS.search(texto):
        raise SystemExit("Parece contener un secreto (clave, token o contraseña): no se guarda.")
    entradas = leer(tipo)
    if any(e["texto"].lower() == texto.lower() and not e["hecho"] for e in entradas):
        return "Ya estaba guardado."
    n = max((int(e["id"][1:]) for e in entradas), default=0) + 1
    nuevo = {"id": f"{LETRA[tipo]}{n}", "fecha": date.today().isoformat(), "hecho": None, "texto": texto}
    escribir(tipo, entradas + [nuevo])
    return f"Guardado [{nuevo['id']}] en {TIPOS[tipo]}."


def cambiar(id_: str, accion: str) -> str:
    e = buscar_id(id_)
    if not e:
        raise SystemExit(f"No existe la entrada {id_}.")
    entradas = leer(e["tipo"])
    if accion == "olvidar":
        entradas = [x for x in entradas if x["id"] != id_]
        msg = f"Borrada [{id_}]."
    else:
        if e["tipo"] != "pendiente":
            raise SystemExit("Solo se pueden completar pendientes.")
        for x in entradas:
            if x["id"] == id_:
                x["hecho"] = " ✅"
        msg = f"Pendiente [{id_}] marcado como hecho."
    escribir(e["tipo"], entradas)
    return msg


def formato(e: dict) -> str:
    return f"[{e['id']}] {e['fecha']}{' ✅' if e['hecho'] else ''} · {e['texto']}"


def buscar(consulta: str) -> str:
    palabras = [p for p in consulta.lower().split() if len(p) > 2] or [consulta.lower()]
    hallados = [e for e in todas() if all(p in e["texto"].lower() for p in palabras)]
    if not hallados:
        hallados = [e for e in todas() if any(p in e["texto"].lower() for p in palabras)]
    return "\n".join(f"{TIPOS[e['tipo']]}: {formato(e)}" for e in hallados) or "Nada encontrado."


def listar(tipo: str | None) -> str:
    tipos = [tipo] if tipo else list(TIPOS)
    bloques = []
    for t in tipos:
        es = leer(t)
        bloques.append(f"## {TIPOS[t].capitalize()} ({len(es)})\n" + ("\n".join(formato(e) for e in es) or "(vacío)"))
    return "\n\n".join(bloques)


def resumen(max_chars: int = 2500) -> str:
    pend = [e for e in leer("pendiente") if not e["hecho"]]
    pref = leer("preferencia")[-10:]
    dec = leer("decision")[-5:]
    if not (pend or pref or dec):
        return ""
    partes = [f"Memoria del proyecto «{proyecto()}» (guardada a mano por el usuario; úsala como contexto)."]
    if pend:
        partes.append("Pendientes:\n" + "\n".join(f"- {formato(e)}" for e in pend))
    if pref:
        partes.append("Preferencias:\n" + "\n".join(f"- {formato(e)}" for e in pref))
    if dec:
        partes.append("Últimas decisiones:\n" + "\n".join(f"- {formato(e)}" for e in dec))
    texto = "\n\n".join(partes)
    if len(texto) > max_chars:
        texto = texto[:max_chars] + "\n… (más en «memoria.py listar»)"
    return texto


def main(argv: list[str]) -> None:
    if not argv:
        raise SystemExit(__doc__)
    cmd, args = argv[0], argv[1:]
    if cmd == "guardar" and len(args) >= 2 and args[0] in TIPOS:
        print(guardar(args[0], " ".join(args[1:])))
    elif cmd == "buscar" and args:
        print(buscar(" ".join(args)))
    elif cmd == "listar" and (not args or args[0] in TIPOS):
        print(listar(args[0] if args else None))
    elif cmd in ("completar", "olvidar") and len(args) == 1:
        print(cambiar(args[0], cmd))
    elif cmd == "resumen":
        print(resumen())
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
