package io.github.myarzik.kert.core

/** Half-open token range [startToken, endToken) of one sentence. */
data class ChunkSpan(val sentenceId: Long, val startToken: Int, val endToken: Int)

/**
 * Chunk assembly from split-point candidates (spec §6), a port of
 * src/kert/reader/chunker.py.
 *
 * Cuts are {0, n} plus a subset of candidate indices. A suffix DP picks the
 * subset minimizing (chunks longer than 2W+2, §6 cost) lexicographically; on
 * equal cost the forward walk takes the earliest next cut (SPEC_NOTES, Task 7).
 */
object Chunker {
    private const val TIE_EPSILON = 1e-9

    fun lengthPenalty(length: Int, width: Int): Double {
        val ratio = (length - width).toDouble() / width
        var penalty = ratio * ratio
        if (length > 2 * width) penalty += 4.0
        if (length < 3) penalty += 1.0
        return penalty
    }

    fun cutPenalty(weight: Double): Double = (1.0 - weight) * 0.75

    fun chunkSentence(n: Int, candidates: List<SplitCandidate>, width: Int): List<Pair<Int, Int>> {
        if (n <= width + 2) return listOf(0 to n)

        val cuts = listOf(0) + candidates.map { it.tokenIndex } + n
        // Penalty for a chunk entered at cuts[i]; the sentence start is free.
        val entry = listOf(0.0) + candidates.map { cutPenalty(it.weight) }
        val limit = 2 * width + 2
        val last = cuts.size - 1

        // best[i]: (overlong chunks, cost) of the optimal cover of [cuts[i], n].
        val overlong = IntArray(cuts.size)
        val cost = DoubleArray(cuts.size)
        val next = IntArray(cuts.size) { last }

        fun option(i: Int, j: Int): Pair<Int, Double> {
            val length = cuts[j] - cuts[i]
            return (overlong[j] + if (length > limit) 1 else 0) to
                (cost[j] + lengthPenalty(length, width) + entry[i])
        }

        for (i in last - 1 downTo 0) {
            var best = option(i, i + 1)
            next[i] = i + 1
            for (j in i + 2..last) {
                val candidate = option(i, j)
                if (better(candidate, best)) {
                    best = candidate
                    next[i] = j
                }
            }
            overlong[i] = best.first
            cost[i] = best.second
        }

        val spans = mutableListOf<Pair<Int, Int>>()
        var i = 0
        while (i < last) {
            spans += cuts[i] to cuts[next[i]]
            i = next[i]
        }
        return spans
    }

    private fun better(a: Pair<Int, Double>, b: Pair<Int, Double>): Boolean =
        a.first < b.first || (a.first == b.first && a.second < b.second - TIE_EPSILON)

    /** Chunk every sentence at [width] into one flat, reading-ordered list. */
    fun assemble(sentences: List<Sentence>, width: Int): List<ChunkSpan> =
        sentences.flatMap { s ->
            chunkSentence(s.tokens.size, s.candidates, width).map { (start, end) ->
                ChunkSpan(s.id, start, end)
            }
        }
}
