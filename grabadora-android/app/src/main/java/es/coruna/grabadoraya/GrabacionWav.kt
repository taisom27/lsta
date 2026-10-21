package es.coruna.grabadoraya

import java.io.File
import java.io.RandomAccessFile
import java.nio.ByteBuffer
import java.nio.ByteOrder

/** Escribe audio PCM de 16 bits mono en un archivo WAV. */
class GrabacionWav(val archivo: File, private val tasa: Int) {
    private val salida = RandomAccessFile(archivo, "rw")
    private var bytesDatos = 0L

    init {
        salida.setLength(0)
        salida.write(cabecera(0))
    }

    fun escribir(datos: ByteArray, n: Int) {
        salida.write(datos, 0, n)
        bytesDatos += n
    }

    fun segundos(): Long = bytesDatos / (tasa * 2L)

    fun cerrar() {
        salida.seek(0)
        salida.write(cabecera(bytesDatos))
        salida.close()
    }

    private fun cabecera(datos: Long): ByteArray =
        ByteBuffer.allocate(44).order(ByteOrder.LITTLE_ENDIAN).apply {
            put("RIFF".toByteArray()); putInt((36 + datos).toInt())
            put("WAVE".toByteArray())
            put("fmt ".toByteArray()); putInt(16)
            putShort(1) // PCM
            putShort(1) // mono
            putInt(tasa)
            putInt(tasa * 2) // bytes por segundo
            putShort(2) // bytes por muestra
            putShort(16) // bits por muestra
            put("data".toByteArray()); putInt(datos.toInt())
        }.array()
}
