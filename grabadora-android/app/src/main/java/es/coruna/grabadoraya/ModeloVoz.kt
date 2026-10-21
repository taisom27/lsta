package es.coruna.grabadoraya

import android.content.Context
import android.content.res.AssetManager
import java.io.File

/** Copia el modelo de Vosk de los assets a la memoria interna (solo la primera vez). */
object ModeloVoz {
    private const val CARPETA = "modelo"

    fun preparar(contexto: Context): File {
        val destino = File(contexto.filesDir, CARPETA)
        val marca = File(destino, ".listo")
        if (marca.exists()) return destino
        destino.deleteRecursively()
        copiar(contexto.assets, CARPETA, destino)
        marca.createNewFile()
        return destino
    }

    private fun copiar(assets: AssetManager, ruta: String, destino: File) {
        val hijos = assets.list(ruta).orEmpty()
        if (hijos.isEmpty()) {
            destino.parentFile?.mkdirs()
            assets.open(ruta).use { entrada -> destino.outputStream().use { entrada.copyTo(it) } }
        } else {
            destino.mkdirs()
            for (hijo in hijos) copiar(assets, "$ruta/$hijo", File(destino, hijo))
        }
    }
}
