# Grabadora YA · app Android

App que escucha el micrófono y **empieza a grabar cuando dices «YA»**.

- Reconoce la palabra sin internet (Vosk, modelo pequeño en español incluido en el APK).
- Sigue escuchando con la pantalla apagada (servicio con notificación fija).
- Para la grabación con el botón «Parar grabación» de la notificación o de la app (o sola a los 30 min).
- Guarda cada grabación en `Música/GrabadoraYA/YA_fecha_hora.wav`.
- Suena un pitido al empezar y otro al terminar.

## Instalar en el móvil

1. En el móvil abre <https://github.com/taisom27/lsta/releases/download/grabadora-apk/GrabadoraYA.apk>
   (también está en la pestaña *Actions* → «App Android» → artefacto *GrabadoraYA*).
2. Android avisará de «origen desconocido»: permite instalar apps desde el navegador.
3. Abre **Grabadora YA**, pulsa «Activar escucha» y acepta los permisos de micrófono y notificaciones.
4. Di «YA».

Requiere Android 10 o superior. Si el móvil corta la escucha al rato, quita la app de la
optimización de batería (Ajustes → Apps → Grabadora YA → Batería → Sin restricciones).

Cada compilación se firma con una clave de depuración distinta: para actualizar,
desinstala antes la versión anterior (las grabaciones guardadas no se borran).

## Compilar

GitHub Actions (`.github/workflows/android.yml`) descarga el modelo de voz y compila el APK en
cada cambio de esta carpeta. En local hace falta el SDK de Android: descarga el modelo
`vosk-model-small-es-0.42` en `app/src/main/assets/modelo/` y ejecuta `gradle assembleDebug`.
