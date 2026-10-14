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

## Cómo funciona

1. **Recoge anuncios** de:
   - **Idealista**, con su API oficial.
   - **pisos.com, Fotocasa y Habitaclia**, o cualquier portal cuya URL de búsqueda pegues en `config.yaml`. Claude lee la página y extrae los anuncios, así que no se rompe cuando el portal cambia su diseño.
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
