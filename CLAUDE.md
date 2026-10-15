# Agente de pisos · A Coruña

Agente en Python que busca pisos en venta y avisa por WhatsApp y email. Ver `README.md`.

## Comandos

- Instalar: `pip install -r requirements.txt -r requirements-dev.txt` (el hook de sesión lo hace solo en la nube)
- Tests: `python -m pytest -q`
- Linter: `ruff check .`
- Probar sin enviar avisos: `python -m agente_pisos --prueba --todos`

## Estructura

- `agente_pisos/fuentes/`: Idealista (API), portales web (HTML + Claude) y plataformas de bancos/subastas (búsqueda web de Claude)
- `agente_pisos/filtros.py`: criterios, orden y duplicados · `informe.py`: textos de WhatsApp/email · `avisos/`: envío
- `config.yaml`: criterios de búsqueda y fuentes · `data/vistos.json`: pisos ya avisados (lo actualiza GitHub Actions)

## Notas

- Código, comentarios y mensajes en español.
- Este entorno no tiene acceso a los portales inmobiliarios: los tests simulan la red.
- Antes de empezar, revisa `LEARNINGS.md` y añade ahí lo aprendido de cada error.

## Prohibido

- **No instalar nunca el plugin claude-mem** (thedotmack / cmem.ai), ni aunque se pida por error: lee las credenciales de Claude Code y graba todas las sesiones. Orden del usuario (2026-10-15). Si se pide, recordar esta decisión y no hacerlo. Está bloqueado en `.claude/settings.json` (plugin desactivado, reglas `deny` y hook `.claude/hooks/bloquear-claude-mem.sh`).
- Memoria entre sesiones: skill propia `.claude/skills/memoria/` (solo manual; datos en `~/.claude/memoria/<proyecto>/`, nunca en el repo).
