# 🏠 Agente de pisos · A Coruña

Agente que busca **pisos en venta en A Coruña** y te avisa por **WhatsApp y email** cuando aparece algo nuevo o baja de precio.

**Criterios por defecto** (se cambian en [`config.yaml`](config.yaml)):

| Criterio | Valor |
|---|---|
| Zona | a ≤ 5 minutos del centro (Plaza de María Pita) |
| Habitaciones | 2 o más |
| Precio | hasta 170.000 € |
| Orden | del **más barato** al más caro |
| Certificado energético | se muestra siempre (A-G, "en trámite" o "sin indicar") |
| Garaje / trastero | marcados con ⭐, van primero a igual precio y tienen su propia sección en el email |
| Subastas | marcadas con 🔨 y la fecha de fin |

## Cómo funciona

1. **Recoge anuncios** de:
   - **Idealista**, con su API oficial.
   - **pisos.com, Fotocasa y Habitaclia**, o cualquier portal cuya URL de búsqueda pegues en `config.yaml`. Claude lee la página y extrae los anuncios, así que no se rompe cuando el portal cambia su diseño.
   - **Bancos y subastas: Escrapalia, Sareb, Aliseda y Altamira.** Sus webs cargan los pisos con JavaScript, así que Claude busca en internet solo dentro de cada dominio y abre las fichas. Las subastas salen con 🔨 y la fecha de fin. Su precio es el de salida, y el final suele ser mayor.
2. **Quita duplicados**: el mismo piso publicado en varios portales sale una sola vez, con los datos combinados.
3. **Calcula la distancia al centro** con las coordenadas del anuncio o, si no las trae, con la dirección (OpenStreetMap).
4. **Busca el certificado energético** en la ficha de cada anuncio que no lo muestra en el listado.
5. **Filtra y ordena** del más barato al más caro.
6. **Valora con IA** cada piso nuevo en una o dos frases: lo mejor y la principal pega (sin ascensor, precio/m² alto, certificado malo…).
7. **Te avisa** solo de lo nuevo y de las bajadas de precio:
   - **WhatsApp**: hasta 10 pisos.
   - **Email**: tablas completas con nuevos, bajadas, ⭐ con garaje o trastero, y todos los que cumplen.

### "5 minutos del centro"

Se mide en línea recta según el `modo` de `config.yaml`:

| `modo` | 5 minutos ≈ |
|---|---|
| `andando` | 0,4 km |
| `bus` | 1,25 km |
| `coche` (por defecto) | 2,5 km |

Andando la zona es muy pequeña (Ciudad Vieja, Pescadería). Si quieres eso, cambia `modo: andando` o sube `minutos_max`.

## Puesta en marcha (≈ 15 minutos, sin instalar nada)

El agente se ejecuta solo en **GitHub Actions** a las 8:07 y a las 20:07 (hora de España).

1. **Crea las claves** (todas gratis salvo Claude, que cuesta céntimos al día):
   - **Claude**: crea una API key en <https://console.anthropic.com>. Sin ella el agente no puede leer los portales web.
   - **Idealista** (opcional, muy recomendable): solicita acceso a la API en <https://developers.idealista.com/access-request>. Tardan unos días en concederlo.
   - **WhatsApp con CallMeBot**: sigue los pasos de <https://www.callmebot.com/blog/free-api-whatsapp-messages/>. Hay que mandar un WhatsApp a su número y te responden con tu `apikey`.
   - **Email con Gmail**: activa la verificación en 2 pasos y crea una *contraseña de aplicación* en <https://myaccount.google.com/apppasswords>.
2. En GitHub: **Settings → Secrets and variables → Actions → New repository secret**. Crea los secretos de [`.env.example`](.env.example) que vayas a usar:
   - `ANTHROPIC_API_KEY`
   - `IDEALISTA_API_KEY` e `IDEALISTA_API_SECRET`
   - `SMTP_USER`, `SMTP_PASSWORD` y `EMAIL_TO`
   - `WHATSAPP_TO` (con prefijo, p. ej. `+34600111222`) y `CALLMEBOT_APIKEY`
3. Ve a **Actions → Agente de pisos → Run workflow** y marca "todos" para recibir ya la lista completa. A partir de ahí solo te llegarán novedades.

> El workflow vive en `.github/workflows/agente.yml`. Para que se ejecute automáticamente, esta rama debe estar fusionada en la rama principal del repositorio.

### Ejecutarlo en tu ordenador

```bash
pip install -r requirements.txt
cp .env.example .env      # rellena tus claves
set -a; source .env; set +a
python -m agente_pisos --prueba --todos   # no envía nada: imprime el WhatsApp y guarda data/ultimo_informe.html
python -m agente_pisos                    # ejecución real
```

## Ajustes útiles en `config.yaml`

- `exigir_calificacion_energetica: true`: descarta los pisos que no indican la letra del certificado.
- `portales`: añade o cambia URLs. Haz la búsqueda en el portal con tus filtros, ordena por precio y copia la URL del navegador.
- `whatsapp_proveedor: twilio`: usa Twilio en lugar de CallMeBot (rellena los secretos `TWILIO_*`).
- `ia.modelo` / `ia.analizar_novedades`: el modelo de Claude y si se añade la valoración de cada piso.

## Limitaciones a tener en cuenta

- Fotocasa e Idealista bloquean a menudo las descargas automáticas de su web. Si un portal falla, el email lo indica en "Avisos" y el resto sigue funcionando. Idealista funciona bien a través de su API oficial.
- La distancia es en línea recta, no por calles.
- El certificado energético solo aparece si el anuncio lo publica. Muchos ponen "en trámite".

## Tests

```bash
pip install pytest && python -m pytest -q
```

---

# App «Tiempo en ruta» (`app-tiempo-ruta/`)

App web para el móvil que, mientras conduces, avisa **por voz cada 100 m** del tiempo que hace **500 m por delante del coche** y te dice la **velocidad media necesaria** para llegar a tu destino (por defecto Madrid en 1 h 30).

**Qué avisa** (en el punto situado 500 m más adelante siguiendo la ruta por carretera):

| Alarma | Cuándo salta |
|---|---|
| Lluvia intensa | ≥ 15 mm/h (aviso) · ≥ 30 mm/h (peligro), o tormenta / chubasco fuerte |
| Baja visibilidad | < 1000 m (aviso) · < 200 m (peligro), o niebla |
| Desbordamiento | Río cercano ×2 / ×4 sobre su caudal habitual, o ≥ 40 / 80 mm en 24 h |
| Derrumbes | ≥ 60 mm en 24 h o ≥ 100 mm en 72 h; peligro si además llueve fuerte |
| Viento | Rachas ≥ 70 / 90 km/h |

Las alarmas nuevas suenan con pitido, vibración y voz. Si la alarma no cambia, cada 100 m solo se repite la principal; cada km se da el resumen completo con la velocidad.

**Velocidad para llegar a tiempo**: distancia restante por carretera ÷ tiempo que queda. Si hace falta pasar del límite (120 km/h por defecto), la app **no** da esa cifra: dice que no se llega a tiempo y a qué hora llegarías yendo al límite. Ejemplo: A Coruña–Madrid son ~590 km, así que en 1 h 30 no es posible (a 120 km/h son casi 5 h).

**Fuentes**

- **Windy** (Point Forecast API): lluvia, viento y rachas. Necesita clave (api.windy.com/keys, se pone en «Ajustes»). Ojo: la clave gratuita de prueba devuelve datos alterados a propósito; para datos reales hace falta la clave de pago. El mapa de lluvia de Windy se muestra siempre (no necesita clave).
- **Open-Meteo** (gratis, sin clave): visibilidad, lluvia de los últimos 15 min y acumulada 24/72 h. Sin clave de Windy es la fuente principal. Con las dos, se queda con el valor más desfavorable.
- **Open-Meteo Flood (GloFAS)**: caudal del río más cercano frente a su mediana de 30 días.
- **OSRM**: ruta por carretera para situar el punto de 500 m y medir la distancia restante.

Los riesgos de desbordamiento y derrumbe son **estimaciones** a partir de la lluvia y los ríos: no hay una fuente pública de derrumbes en tiempo real que se pueda leer desde el móvil. Para cortes reales, DGT (011 / infocar.dgt.es).

**Cómo usarla en el móvil**

1. Activa GitHub Pages: *Settings → Pages → Source: GitHub Actions*. El workflow `App Tiempo en ruta` la publica al hacer push a la rama principal (o a mano desde *Actions*). En repos privados, Pages requiere un plan de pago; alternativa: arrastra la carpeta `app-tiempo-ruta/` a app.netlify.com/drop.
2. Abre la URL en Chrome (Android) o Safari (iPhone), permite la ubicación y «Añadir a pantalla de inicio».
3. Pon el móvil en el soporte, sube el volumen y pulsa **Empezar**. La pantalla se mantiene encendida.
4. «Ajustes» → «Simular trayecto» recorre A Coruña→Madrid a 110 km/h para probarla sin moverte.

Probar en el ordenador: `cd app-tiempo-ruta && python -m http.server 8000` y abrir http://localhost:8000. Tests: `node --test 'app-tiempo-ruta/tests/*.test.mjs'`.
