package io.github.myarzik.kert.core

import java.nio.file.Path
import kotlin.random.Random
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.io.TempDir
import org.junit.jupiter.params.ParameterizedTest
import org.junit.jupiter.params.provider.CsvSource

/**
 * Port of tests/test_chunker.py (spec §6). Goldens are the hand-computed values
 * from the Python suite; the reference test checks every fixture and width
 * against the Python implementation (§16.6).
 */
class ChunkerTest {
    private fun cands(vararg pairs: Pair<Int, Double>) =
        pairs.map { (i, w) -> SplitCandidate(i, w) }

    private fun chunk(n: Int, candidates: List<SplitCandidate>, width: Int) =
        Chunker.chunkSentence(n, candidates, width)

    // --- Cost terms -------------------------------------------------------------------

    @ParameterizedTest
    @CsvSource(
        "8, 8, 0.0",
        "6, 8, 0.0625", // (2/8)^2
        "2, 8, 1.5625", // (6/8)^2 + 1 crumb
        "16, 8, 1.0", // (8/8)^2, not > 2W
        "17, 8, 5.265625", // (9/8)^2 + 4
        "3, 5, 0.16", // (2/5)^2, not a crumb
    )
    fun `length penalty`(length: Int, width: Int, expected: Double) =
        assertEquals(expected, Chunker.lengthPenalty(length, width), 1e-12)

    @ParameterizedTest
    @CsvSource("1.0, 0.0", "0.8, 0.15", "0.4, 0.45", "0.2, 0.6")
    fun `cut penalty`(weight: Double, expected: Double) =
        assertEquals(expected, Chunker.cutPenalty(weight), 1e-12)

    // --- Golden fixture sentences at W = 6, 8, 12 ---------------------------------------

    // EN "She gave the old man a book in the morning." / RU "Мы долго гуляли по парку…"
    private val en = cands(2 to 0.4, 5 to 0.4, 7 to 0.4)
    private val ru = cands(3 to 0.4, 5 to 0.8, 7 to 0.4)

    @Test
    fun `golden fixture sentences`() {
        assertEquals(listOf(0 to 5, 5 to 11), chunk(11, en, 6)) // {5} 0.478 is cheapest
        assertEquals(listOf(0 to 11), chunk(11, en, 8)) // {} 0.141
        assertEquals(listOf(0 to 11), chunk(11, en, 12)) // n <= W+2
        assertEquals(listOf(0 to 5, 5 to 10), chunk(10, ru, 6)) // {5} 0.206
        assertEquals(listOf(0 to 10), chunk(10, ru, 8))
        assertEquals(listOf(0 to 10), chunk(10, ru, 12))
    }

    @Test
    fun `short sentence is one chunk without DP`() =
        assertEquals(listOf(0 to 10), chunk(10, cands(5 to 1.0), 8))

    @Test
    fun `no candidates is one chunk`() = assertEquals(listOf(0 to 20), chunk(20, emptyList(), 6))

    @Test
    fun `strong boundary preferred`() =
        assertEquals(listOf(0 to 7, 7 to 12), chunk(12, cands(5 to 0.4, 7 to 1.0), 6))

    @Test
    fun `crumbs avoided even at strong boundaries`() =
        assertEquals(listOf(0 to 12), chunk(12, cands(2 to 1.0, 10 to 1.0), 8))

    @Test
    fun `long sentence split at fallback candidates`() =
        assertEquals(
            listOf(0 to 10, 10 to 20, 20 to 30),
            chunk(30, cands(10 to 0.2, 20 to 0.2), 5),
        )

    @Test
    fun `tie prefers earlier cut`() =
        assertEquals(listOf(0 to 4, 4 to 12), chunk(12, cands(4 to 1.0, 8 to 1.0), 6))

    @Test
    fun `overlong chunk avoided when a bounded partition exists`() =
        assertEquals(listOf(0 to 2, 2 to 13), chunk(13, cands(2 to 0.4), 5))

    @Test
    fun `assemble flattens sentences in reading order`() {
        fun sentence(id: Long, n: Int, candidates: List<SplitCandidate>) =
            Sentence(id, 1, 0, "", List(n) { TokenSpan(it, it + 1) }, candidates)

        val spans = Chunker.assemble(listOf(sentence(1, 10, ru), sentence(2, 3, emptyList())), 6)

        assertEquals(
            listOf(ChunkSpan(1, 0, 5), ChunkSpan(1, 5, 10), ChunkSpan(2, 0, 3)),
            spans,
        )
    }

    // --- Properties (seeded random cases) -------------------------------------------------

    private data class Case(val n: Int, val candidates: List<SplitCandidate>, val width: Int)

    private fun randomCases(count: Int = 2000): List<Case> {
        val rnd = Random(20261028)
        val weights = listOf(1.0, 0.8, 0.6, 0.4, 0.2)
        return List(count) {
            val n = rnd.nextInt(1, 81)
            val width = rnd.nextInt(5, 13)
            val k = rnd.nextInt(0, minOf(n - 1, 12) + 1)
            val indices = (1 until n).shuffled(rnd).take(k).sorted()
            Case(n, indices.map { SplitCandidate(it, weights.random(rnd)) }, width)
        }
    }

    private fun boundedPartitionExists(case: Case): Boolean {
        val points = listOf(0) + case.candidates.map { it.tokenIndex } + case.n
        val reachable = mutableListOf(0)
        for (p in points.drop(1)) {
            if (reachable.any { p - it <= 2 * case.width + 2 }) reachable += p
        }
        return case.n in reachable
    }

    @Test
    fun `properties hold on random cases`() {
        for (case in randomCases()) {
            val spans = chunk(case.n, case.candidates, case.width)
            val allowed = case.candidates.map { it.tokenIndex }.toSet()

            assertEquals(0, spans.first().first)
            assertEquals(case.n, spans.last().second)
            assertTrue(spans.all { (a, b) -> a < b })
            assertTrue(spans.zipWithNext().all { (p, q) -> p.second == q.first })
            assertTrue(spans.drop(1).all { it.first in allowed }, "cut outside candidates")
            if (case.n <= case.width + 2) assertEquals(listOf(0 to case.n), spans)
            if (boundedPartitionExists(case)) {
                assertTrue(spans.all { (a, b) -> b - a <= 2 * case.width + 2 }, "$case $spans")
            }
        }
    }

    // --- Python reference cross-check (§16.6) ------------------------------------------------

    @TempDir
    lateinit var tmp: Path

    @Test
    fun `chunks match the Python implementation for every fixture and width`() {
        for (reference in Reference.books) {
            val book = JdbcConnection(Reference.copy(reference.file, tmp)).use {
                KertReader.read(it)
            }
            for ((width, expected) in reference.widths) {
                val actual = Chunker.assemble(book.sentences, width.toInt()).map {
                    listOf(it.sentenceId.toInt(), it.startToken, it.endToken)
                }
                assertEquals(expected.map { it.take(3) }, actual, "${reference.file} W=$width")
            }
        }
    }
}
