package io.github.myarzik.kert.core

/** An advance_log row as tempo sees it (§17.6). */
data class LogRow(val ts: Double, val chunkWords: Int, val direction: Int, val kind: String, val mode: String)

object Tempo {
    fun wps(rows: List<LogRow>, mode: String): Double? = TODO()

    fun activeSeconds(rows: List<LogRow>, mode: String, since: Double): Double = TODO()
}
