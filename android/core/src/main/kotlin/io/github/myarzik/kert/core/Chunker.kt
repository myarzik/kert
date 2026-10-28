package io.github.myarzik.kert.core

/** Half-open token range [startToken, endToken) of one sentence. */
data class ChunkSpan(val sentenceId: Long, val startToken: Int, val endToken: Int)

object Chunker {
    fun lengthPenalty(length: Int, width: Int): Double = TODO("task 20")

    fun cutPenalty(weight: Double): Double = TODO("task 20")

    fun chunkSentence(n: Int, candidates: List<SplitCandidate>, width: Int): List<Pair<Int, Int>> =
        TODO("task 20")

    fun assemble(sentences: List<Sentence>, width: Int): List<ChunkSpan> = TODO("task 20")
}
