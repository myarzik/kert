package io.github.myarzik.kert.core

import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertNull
import org.junit.jupiter.api.Test

/** Port of tests/test_tempo.py (§17.6). */
class TempoTest {
    /** Forward chunk steps: one row at [start], then one after each dwell. */
    private fun steps(dwells: List<Double>, words: Int = 4, start: Double = 1000.0, mode: String = "chunk"): List<LogRow> {
        var ts = start
        return listOf(LogRow(start, words, 1, "step", mode)) + dwells.map { ts += it; LogRow(ts, words, 1, "step", mode) }
    }

    private fun repeat(value: Double, n: Int) = List(n) { value }

    @Test
    fun `median words per second`() = assertEquals(2.0, Tempo.wps(steps(repeat(2.0, 30)), "chunk")!!, 1e-9)

    @Test
    fun `median resists outliers`() =
        assertEquals(2.0, Tempo.wps(steps(repeat(2.0, 20) + repeat(0.5, 5) + repeat(40.0, 6)), "chunk")!!, 1e-9)

    @Test
    fun `fewer than 30 samples is null`() {
        assertNull(Tempo.wps(steps(repeat(2.0, 29)), "chunk"))
        assertNull(Tempo.wps(emptyList(), "chunk"))
    }

    @Test
    fun `idle and skip-through dwells are discarded`() {
        assertEquals(2.0, Tempo.wps(steps(repeat(2.0, 15) + listOf(61.0, 0.1) + repeat(2.0, 15)), "chunk")!!, 1e-9)
        assertNull(Tempo.wps(steps(repeat(2.0, 28) + listOf(61.0, 0.1)), "chunk"))
    }

    @Test
    fun `only forward steps in the current mode count`() {
        val noise = listOf(
            LogRow(1001.0, 50, -1, "step", "chunk"),
            LogRow(1003.0, 50, 1, "block", "chunk"),
            LogRow(1005.0, 50, 0, "peek", "chunk"),
            LogRow(1007.0, 50, 1, "step", "paragraph"),
        )
        val mixed = (steps(repeat(2.0, 30)) + noise).sortedBy { it.ts }
        assertEquals(2.0, Tempo.wps(mixed, "chunk")!!, 1e-9)
        assertNull(Tempo.wps(mixed, "paragraph"))
    }

    @Test
    fun `only the last 200 qualifying rows count`() =
        assertEquals(4.0, Tempo.wps(steps(repeat(4.0, 100) + repeat(1.0, 199)), "chunk")!!, 1e-9)

    @Test
    fun `active seconds sum kept dwells after arming`() {
        val rows = steps(listOf(2.0, 2.0, 61.0, 2.0, 0.1, 3.0))
        assertEquals(7.0, Tempo.activeSeconds(rows, "chunk", since = 1003.0), 1e-9)
        assertEquals(9.0, Tempo.activeSeconds(rows, "chunk", since = 0.0), 1e-9)
        assertEquals(0.0, Tempo.activeSeconds(rows, "paragraph", since = 0.0), 1e-9)
    }
}
