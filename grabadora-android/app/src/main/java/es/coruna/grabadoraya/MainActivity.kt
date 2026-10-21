package es.coruna.grabadoraya

import android.Manifest
import android.app.Activity
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import android.view.Gravity
import android.widget.Button
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.Toast

class MainActivity : Activity() {

    private lateinit var textoEstado: TextView
    private lateinit var botonEscucha: Button
    private lateinit var botonParar: Button

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val margen = (24 * resources.displayMetrics.density).toInt()

        textoEstado = TextView(this).apply { textSize = 22f; gravity = Gravity.CENTER }
        botonEscucha = Button(this).apply { setOnClickListener { alternarEscucha() } }
        botonParar = Button(this).apply {
            text = "Parar grabación"
            setOnClickListener { enviar(EscuchaService.ACCION_PARAR_GRABACION) }
        }
        val ayuda = TextView(this).apply {
            textSize = 15f
            text = "Activa la escucha y di «YA» para empezar a grabar. " +
                "Para parar, pulsa «Parar grabación» aquí o en la notificación.\n\n" +
                "Las grabaciones se guardan en Música/GrabadoraYA. " +
                "Funciona sin internet y con la pantalla apagada."
        }

        setContentView(LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(margen, margen, margen, margen)
            addView(textoEstado)
            addView(botonEscucha)
            addView(botonParar)
            addView(ayuda)
        })
    }

    override fun onResume() {
        super.onResume()
        EscuchaService.oyente = { refrescar() }
        refrescar()
    }

    override fun onPause() {
        EscuchaService.oyente = null
        super.onPause()
    }

    private fun refrescar() {
        textoEstado.text = EscuchaService.estado
        botonEscucha.text = if (EscuchaService.activo) "Apagar escucha" else "Activar escucha"
        botonParar.isEnabled = EscuchaService.grabando
    }

    private fun alternarEscucha() {
        if (EscuchaService.activo) {
            enviar(EscuchaService.ACCION_APAGAR)
            return
        }
        val faltan = permisos().filter { checkSelfPermission(it) != PackageManager.PERMISSION_GRANTED }
        if (faltan.isEmpty()) {
            startForegroundService(Intent(this, EscuchaService::class.java))
        } else {
            requestPermissions(faltan.toTypedArray(), 1)
        }
    }

    override fun onRequestPermissionsResult(codigo: Int, permisos: Array<String>, resultados: IntArray) {
        super.onRequestPermissionsResult(codigo, permisos, resultados)
        if (checkSelfPermission(Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED) {
            startForegroundService(Intent(this, EscuchaService::class.java))
        } else {
            Toast.makeText(this, "Sin permiso de micrófono no puedo escuchar", Toast.LENGTH_LONG).show()
        }
    }

    private fun permisos(): List<String> =
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            listOf(Manifest.permission.RECORD_AUDIO, Manifest.permission.POST_NOTIFICATIONS)
        } else {
            listOf(Manifest.permission.RECORD_AUDIO)
        }

    private fun enviar(accion: String) {
        startService(Intent(this, EscuchaService::class.java).setAction(accion))
    }
}
