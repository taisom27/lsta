# Instrucciones para Claude

Antes de empezar cualquier tarea, lee `LEARNINGS.md` y apunta ahí lo que aprendas de cada error.

## Palabra clave «piso»: ejecutar el agente

El usuario ha llamado **piso** al agente. Cuando su mensaje sea la orden «piso»
(solo esa palabra, o «piso» seguido de una opción), prepara la ejecución del agente y
**pide confirmación antes de lanzarlo** cada vez: di en una línea qué vas a lanzar (rama y
si es `todos`) y espera a que el usuario diga que sí. Avisa de que una ejecución real
envía WhatsApp y email.

| Mensaje | Qué hacer |
|---|---|
| `piso` | Lanzar el workflow con `todos: false` (solo novedades y bajadas de precio) |
| `piso todos` | Lanzar el workflow con `todos: true` (lista completa) |

Cómo se lanza, una vez confirmado:

1. Llama a `mcp__github__actions_run_trigger` con `method: run_workflow`,
   `owner: taisom27`, `repo: lsta`, `workflow_id: agente.yml`,
   `ref`: la rama actual (`git branch --show-current`) e `inputs: {"todos": "true"|"false"}`.
   Se ejecuta en GitHub Actions, que tiene los secretos (Claude, Idealista, WhatsApp, email)
   y acceso a los portales. El contenedor de la nube no tiene ninguna de las dos cosas.
2. Comprueba con `mcp__github__actions_list` (`list_workflow_runs`) que la ejecución arrancó
   y dile al usuario en una línea que el agente está buscando, con el enlace a la ejecución.
   Los resultados llegan por WhatsApp y email.
3. Si no hay acceso a GitHub, ejecuta en local `python -m agente_pisos --prueba`
   (`--todos` si se pidió) y explica que en ese modo no se envía nada.

No lo actives cuando «piso» aparezca dentro de una frase normal sobre el código o los
anuncios (p. ej. «cambia el precio máximo del piso»). Ahí es una palabra más, no la orden.
