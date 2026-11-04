package io.github.myarzik.kert.core

/** An advance_log row as tempo sees it (§17.6). */
data class LogRow(val ts: Double, val chunkWords: Int, val direction: Int, val kind: String, val mode: String)

/** Reading tempo and active time from advance_log rows: src/kert/reader/tempo.py (§17.6). */
object Tempo {
    private const val MIN_DWELL = 0.15 // skip-through, seconds
    private const val MAX_DWELL = 60.0 // idle
    private const val WINDOW = 200
    private const val MIN_SAMPLES = 30

    private fun forwardSteps(rows: List<LogRow>, mode: String) =
        rows.filter { it.kind == "step" && it.direction == 1 && it.mode == mode }.sortedBy { it.ts }

    /** Each row with the time spent on the unit it left, idle and skips dropped. */
    private fun keptDwells(rows: List<LogRow>): List<Pair<LogRow, Double>> =
        rows.zipWithNext { previous, row -> row to row.ts - previous.ts }
            .filter { (_, dwell) -> dwell in MIN_DWELL..MAX_DWELL }

    /** Median words per second over the last 200 forward steps in [mode]. */
    fun wps(rows: List<LogRow>, mode: String): Double? {
        val samples = keptDwells(forwardSteps(rows, mode).takeLast(WINDOW))
            .map { (row, dwell) -> row.chunkWords / dwell }
            .sorted()
        if (samples.size < MIN_SAMPLES) return null
        val mid = samples.size / 2
        return if (samples.size % 2 == 1) samples[mid] else (samples[mid - 1] + samples[mid]) / 2
    }

    /** Reading time in [mode] after [since]: the kept dwells only. */
    fun activeSeconds(rows: List<LogRow>, mode: String, since: Double): Double =
        keptDwells(forwardSteps(rows, mode)).filter { (row, _) -> row.ts > since }.sumOf { it.second }
}
