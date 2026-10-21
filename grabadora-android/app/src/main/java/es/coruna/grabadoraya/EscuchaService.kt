package es.coruna.grabadoraya

import android.annotation.SuppressLint
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.ContentValues
import android.content.Intent
import android.content.pm.ServiceInfo
import android.media.AudioFormat
import android.media.AudioManager
import android.media.AudioRecord
import android.media.MediaRecorder
import android.media.ToneGenerator
import android.os.Environment
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import android.os.PowerManager
import android.provider.MediaStore
import org.json.JSONObject
import org.vosk.LibVosk
import org.vosk.LogLevel
import org.vosk.Model
import org.vosk.Recognizer
import java.io.File
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import kotlin.concurrent.thread

/**
 * Servicio en primer plano que escucha el micrófono sin conexión.
 * Al oír «ya» empieza a grabar; se para desde la notificación, la app o al llegar al máximo.
 */
class EscuchaService : Service() {

    companion object {
        const val ACCION_PARAR_GRABACION = "es.coruna.grabadoraya.PARAR_GRABACION"
        const val ACCION_APAGAR = "es.coruna.grabadoraya.APAGAR"

        const val PALABRA = "ya"
        private const val TASA = 16000
        private const val MAX_SEGUNDOS = 30 * 60
        private const val CANAL = "escucha"
        private const val ID_NOTIFICACION = 1

        @Volatile var activo = false
            private set
        @Volatile var grabando = false
            private set
        @Volatile var estado = "Apagado"
            private set

        /** Lo usa la pantalla para mostrar el estado (se llama en el hilo principal). */
        var oyente: (() -> Unit)? = null
    }

    private val principal = Handler(Looper.getMainLooper())
    private var hilo: Thread? = null
    private var bloqueo: PowerManager.WakeLock? = null
    @Volatile private var seguir = false
    @Volatile private var pararGrabacion = false

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACCION_PARAR_GRABACION -> pararGrabacion = true
            ACCION_APAGAR -> stopSelf()
            else -> if (!seguir) arrancar()
        }
        return START_NOT_STICKY
    }

    private fun arrancar() {
        getSystemService(NotificationManager::class.java).createNotificationChannel(
            NotificationChannel(CANAL, "Escucha", NotificationManager.IMPORTANCE_LOW)
        )
        startForeground(
            ID_NOTIFICACION,
            notificacion("Preparando…"),
            ServiceInfo.FOREGROUND_SERVICE_TYPE_MICROPHONE,
        )
        bloqueo = getSystemService(PowerManager::class.java)
            .newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "GrabadoraYA:escucha")
            .apply { acquire() }
        activo = true
        seguir = true
        hilo = thread(name = "escucha") { bucle() }
    }

    @SuppressLint("MissingPermission") // la pantalla pide el permiso antes de arrancar
    private fun bucle() {
        var modelo: Model? = null
        var reconocedor: Recognizer? = null
        var audio: AudioRecord? = null
        var grabacion: GrabacionWav? = null
        val tono = runCatching { ToneGenerator(AudioManager.STREAM_NOTIFICATION, 80) }.getOrNull()
        try {
            publicar("Preparando el reconocimiento de voz…")
            LibVosk.setLogLevel(LogLevel.WARNINGS)
            modelo = Model(ModeloVoz.preparar(this).absolutePath)
            reconocedor = Recognizer(modelo, TASA.toFloat(), "[\"$PALABRA\", \"[unk]\"]")

            val bufferMinimo = AudioRecord.getMinBufferSize(
                TASA, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT
            )
            val trozo = ByteArray(TASA / 10 * 2) // 100 ms
            audio = AudioRecord(
                MediaRecorder.AudioSource.VOICE_RECOGNITION, TASA,
                AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT,
                maxOf(bufferMinimo, trozo.size * 4),
            )
            audio.startRecording()
            publicar("Escuchando… di «YA» para grabar")

            while (seguir) {
                val n = audio.read(trozo, 0, trozo.size)
                if (n <= 0) continue

                if (grabacion != null) {
                    grabacion.escribir(trozo, n)
                    if (pararGrabacion || grabacion.segundos() >= MAX_SEGUNDOS) {
                        guardar(grabacion)
                        grabacion = null
                        tono?.startTone(ToneGenerator.TONE_PROP_ACK, 150)
                        reconocedor.reset()
                        publicar("Escuchando… di «YA» para grabar")
                    }
                    continue
                }

                val texto = if (reconocedor.acceptWaveForm(trozo, n)) {
                    JSONObject(reconocedor.result).optString("text")
                } else {
                    JSONObject(reconocedor.partialResult).optString("partial")
                }
                if (PALABRA in texto.split(" ")) {
                    reconocedor.reset()
                    pararGrabacion = false
                    grabacion = GrabacionWav(File(cacheDir, "grabacion.wav"), TASA)
                    tono?.startTone(ToneGenerator.TONE_PROP_BEEP, 150)
                    publicar("● Grabando…", grabandoAhora = true)
                }
            }
        } catch (e: Throwable) {
            publicar("Error: ${e.message ?: e.javaClass.simpleName}")
            principal.post { stopSelf() }
        } finally {
            grabacion?.let { runCatching { guardar(it) } }
            audio?.run { runCatching { stop() }; release() }
            reconocedor?.close()
            modelo?.close()
            tono?.release()
        }
    }

    /** Cierra el WAV y lo copia a Música/GrabadoraYA, donde lo ve cualquier reproductor. */
    private fun guardar(grabacion: GrabacionWav) {
        grabacion.cerrar()
        val nombre = "YA_" + SimpleDateFormat("yyyy-MM-dd_HH-mm-ss", Locale.ROOT).format(Date()) + ".wav"
        val valores = ContentValues().apply {
            put(MediaStore.Audio.Media.DISPLAY_NAME, nombre)
            put(MediaStore.Audio.Media.MIME_TYPE, "audio/wav")
            put(MediaStore.Audio.Media.RELATIVE_PATH, Environment.DIRECTORY_MUSIC + "/GrabadoraYA")
            put(MediaStore.Audio.Media.IS_PENDING, 1)
        }
        val coleccion = MediaStore.Audio.Media.getContentUri(MediaStore.VOLUME_EXTERNAL_PRIMARY)
        val uri = contentResolver.insert(coleccion, valores)
            ?: error("No se pudo crear el archivo de audio")
        contentResolver.openOutputStream(uri)!!.use { salida ->
            grabacion.archivo.inputStream().use { it.copyTo(salida) }
        }
        valores.clear()
        valores.put(MediaStore.Audio.Media.IS_PENDING, 0)
        contentResolver.update(uri, valores, null, null)
        grabacion.archivo.delete()
        publicar("Guardado en Música/GrabadoraYA/$nombre")
    }

    private fun publicar(texto: String, grabandoAhora: Boolean = false) {
        estado = texto
        grabando = grabandoAhora
        principal.post {
            if (activo) {
                getSystemService(NotificationManager::class.java)
                    .notify(ID_NOTIFICACION, notificacion(texto))
            }
            oyente?.invoke()
        }
    }

    private fun notificacion(texto: String): Notification {
        val abrir = PendingIntent.getActivity(
            this, 0, Intent(this, MainActivity::class.java), PendingIntent.FLAG_IMMUTABLE
        )
        val constructor = Notification.Builder(this, CANAL)
            .setSmallIcon(android.R.drawable.ic_btn_speak_now)
            .setContentTitle("Grabadora YA")
            .setContentText(texto)
            .setContentIntent(abrir)
            .setOngoing(true)
        if (grabando) {
            constructor.addAction(accion("Parar grabación", ACCION_PARAR_GRABACION, 1))
        }
        constructor.addAction(accion("Apagar", ACCION_APAGAR, 2))
        return constructor.build()
    }

    private fun accion(titulo: String, accion: String, codigo: Int): Notification.Action {
        val intent = PendingIntent.getService(
            this, codigo, Intent(this, EscuchaService::class.java).setAction(accion),
            PendingIntent.FLAG_IMMUTABLE,
        )
        return Notification.Action.Builder(null, titulo, intent).build()
    }

    override fun onDestroy() {
        seguir = false
        hilo?.join(3000)
        bloqueo?.release()
        activo = false
        if (!estado.startsWith("Error")) publicar("Apagado")
        super.onDestroy()
    }
}
