package io.github.myarzik.kert.core

/** One block's display text (its sentences joined by a space, like the terminal). */
data class BlockView(val id: Long, val type: String, val text: String)

class BookLayout(book: BookContent) {
    val blocks: List<BlockView> = TODO("task 23")

    /** Index into [blocks] of chunk [chunk]. */
    fun blockIndex(state: ReaderState, chunk: Int): Int = TODO("task 23")

    /** The active chunk: its block index and inclusive UTF-16 range in that block's text. */
    fun active(state: ReaderState): Pair<Int, IntRange> = TODO("task 23")
}

object Centering {
    /** Scroll by this many pixels to center the chunk's lines in the viewport. */
    fun scrollDelta(itemTop: Int, chunkTop: Float, chunkBottom: Float, viewport: Int): Float = TODO("task 23")
}
