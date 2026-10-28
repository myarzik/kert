package io.github.myarzik.kert.core

/** One block's display text (its sentences joined by a space, like the terminal). */
data class BlockView(val id: Long, val type: String, val text: String)

/** Book text arranged for the Android tape (§16.5): computed once per book. */
class BookLayout(book: BookContent) {
    val blocks: List<BlockView>

    /** Per sentence id: its block index and its UTF-16 offset in that block's text. */
    private val placement = HashMap<Long, Pair<Int, Int>>()

    init {
        val types = book.blocks.associate { it.id to it.type }
        val built = mutableListOf<BlockView>()
        for ((blockId, sentences) in book.sentences.groupBy { it.blockId }) {
            var offset = 0
            for (sentence in sentences) {
                placement[sentence.id] = built.size to offset
                offset += sentence.text.length + 1
            }
            built += BlockView(blockId, types[blockId] ?: "paragraph", sentences.joinToString(" ") { it.text })
        }
        blocks = built
    }

    private val sentences = book.sentences.associateBy { it.id }

    /** Index into [blocks] of chunk [chunk]. */
    fun blockIndex(state: ReaderState, chunk: Int): Int =
        placement.getValue(state.chunks.spans[chunk].sentenceId).first

    /** The active chunk: its block index and inclusive UTF-16 range in that block's text. */
    fun active(state: ReaderState): Pair<Int, IntRange> {
        val span = state.active
        val (block, offset) = placement.getValue(span.sentenceId)
        val tokens = sentences.getValue(span.sentenceId).tokens
        val start = offset + tokens[span.startToken].start
        val end = offset + tokens[span.endToken - 1].end
        return block to (start until end)
    }
}

object Centering {
    /** Scroll by this many pixels to center the chunk's lines in the viewport. */
    fun scrollDelta(itemTop: Int, chunkTop: Float, chunkBottom: Float, viewport: Int): Float =
        itemTop + (chunkTop + chunkBottom) / 2 - viewport / 2f
}
