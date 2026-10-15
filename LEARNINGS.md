# Aprendizajes

- **El SDK `anthropic` 1.x usa `httpx2`, no `httpx`.** Un test con `httpx.MockTransport` falló por `ModuleNotFoundError`. Para simular la API en tests: `import httpx2 as httpx` y pasar `http_client=httpx.Client(transport=httpx.MockTransport(...))`.
- **El entorno de desarrollo en la nube no tiene acceso a los portales inmobiliarios** (idealista, fotocasa, pisos.com...). No se puede comprobar su HTML en vivo, así que la lectura de portales usa Claude sobre el texto de la página en lugar de selectores CSS frágiles. La primera ejecución real (`--prueba --todos`) es la verificación de verdad.
- **Los secretos de GitHub vacíos llegan como cadena vacía**, no como variable ausente. Usar `os.environ.get(X) or valor_por_defecto`, no `os.environ.get(X, valor_por_defecto)`.
- **`pkill -f patrón` / `pgrep -f patrón` dentro de un comando que contiene ese mismo patrón mata la propia shell** (salió con código 144). Para buscar procesos usa `ps -eo pid,args | grep "[w]orker"` (el corchete evita coincidir consigo mismo) y mata por PID.
- **`/plugin` no existe en las sesiones en la nube.** Para instalar o quitar plugins aquí: `claude plugin install|uninstall <nombre>@<marketplace>` y `claude plugin marketplace add|remove`.
