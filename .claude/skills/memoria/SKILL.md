---
name: memoria
description: Memoria persistente y manual entre sesiones (decisiones, preferencias y pendientes), guardada en archivos locales del ordenador. Úsala cuando el usuario diga "recuerda que…", "apunta / anota…", "guarda en memoria", "¿qué decidimos sobre…?", "¿qué tenía pendiente?", "ya hice…", "olvida…" o pregunte por algo de sesiones anteriores.
---

# Memoria

Memoria entre sesiones **solo manual**: nunca guardes nada que el usuario no haya pedido explícitamente.
Los datos viven en `~/.claude/memoria/<proyecto>/` (decisiones.md, preferencias.md, pendientes.md):
texto plano, sin red, sin telemetría, editable por el usuario.

Script: `python3 "$CLAUDE_PROJECT_DIR/.claude/skills/memoria/scripts/memoria.py" <comando>`

## Qué hacer según lo que pida el usuario

| El usuario dice | Comando |
|---|---|
| "Recuerda que decidimos X" / "apunta esta decisión" | `guardar decision "X (motivo)"` |
| "Recuerda que prefiero X" / "siempre quiero X" | `guardar preferencia "X"` |
| "Apunta pendiente X" / "queda por hacer X" | `guardar pendiente "X"` |
| "¿Qué decidimos sobre X?" / "¿recuerdas X?" | `buscar "X"` |
| "¿Qué tengo pendiente?" / "¿qué recuerdas?" | `listar pendiente` / `listar` |
| "Ya hice X" | `buscar "X"` y luego `completar <id>` |
| "Olvida X" / "eso ya no vale" | `buscar "X"` y luego `olvidar <id>` |

## Reglas

1. **Solo bajo petición.** Si algo parece valioso, puedes proponer "¿lo guardo en memoria?", pero no lo guardes sin un sí.
2. **Redacta entradas cortas y autosuficientes** (una frase; incluye el porqué de las decisiones). Usa el idioma del usuario.
3. **Nunca guardes secretos** (claves, tokens, contraseñas, datos bancarios). El script también los rechaza.
4. **Confirma** con una línea tras guardar, completar u olvidar, citando el id.
5. **Contexto de inicio:** al empezar cada sesión un hook inyecta `resumen` (pendientes abiertos, preferencias y últimas decisiones). Tenlo en cuenta, pero si contradice lo que el usuario dice ahora, manda el usuario y ofrece actualizar la memoria.
6. Para ver o editar a mano: los archivos `.md` de la carpeta del proyecto.
