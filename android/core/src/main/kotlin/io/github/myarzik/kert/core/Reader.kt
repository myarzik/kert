package io.github.myarzik.kert.core

data class Position(val sentenceId: Long, val chunkStartToken: Int)

enum class Theme(val storage: String) { DARK("dark"), LIGHT("light") }

/** §17.2 reading modes; the unit highlighted and stepped through. */
enum class Mode(val storage: String) { CHUNK("chunk"), SENTENCE("sentence"), PARAGRAPH("paragraph") }

data class Settings(val chunkWidth: Int, val theme: Theme, val mode: Mode = Mode.CHUNK)

sealed interface Action {
    data object Next : Action
    data object Previous : Action
    data object NextBlock : Action
    data object PreviousBlock : Action
    data object First : Action
    data object Last : Action
    data class GotoPercent(val percent: Double) : Action
    data class SetWidth(val width: Int) : Action
    data class SetTheme(val theme: Theme) : Action
    data object PreviousSentence : Action
    data object NextSentence : Action
    data object PeekStart : Action
    data object PeekEnd : Action
    data class SetMode(val mode: Mode) : Action
}

sealed interface Effect {
    data class Advance(
        val sentenceId: Long,
        val chunkWords: Int,
        val direction: Int,
        val kind: String = "step",
    ) : Effect
    data class SaveSetting(val key: String, val value: String) : Effect
}

/** Book-wide chunk list at one width, with per-chunk lookup columns. */
class Chunks(
    val spans: List<ChunkSpan>,
    val words: List<Int>,
    val wordsBefore: List<Int>,
    val blockIds: List<Long>,
    val ends: List<Pair<Int, Int>> = emptyList(),
) {
    /** Half-open chunk range of the block containing chunk [index]. */
    fun blockRange(index: Int): IntRange {
        var start = index
        var end = index + 1
        while (start > 0 && blockIds[start - 1] == blockIds[index]) start--
        while (end < blockIds.size && blockIds[end] == blockIds[index]) end++
        return start until end
    }

    companion object {
        fun build(book: BookContent, width: Int, mode: Mode = Mode.CHUNK): Chunks {
            if (mode != Mode.CHUNK) TODO()
            val byId = book.sentences.associateBy { it.id }
            val spans = Chunker.assemble(book.sentences, width)
            val words = spans.map { span ->
                val sentence = byId.getValue(span.sentenceId)
                sentence.tokens.subList(span.startToken, span.endToken).count {
                    Words.isWord(sentence.text.substring(it.start, it.end))
                }
            }
            val before = words.runningFold(0, Int::plus).dropLast(1)
            return Chunks(spans, words, before, spans.map { byId.getValue(it.sentenceId).blockId })
        }
    }
}

data class ReaderState(
    val book: BookContent,
    val settings: Settings,
    val chunks: Chunks,
    val index: Int,
    val peek: Boolean = false,
    val effects: List<Effect> = emptyList(),
) {
    val active: ChunkSpan get() = chunks.spans[index]

    val position: Position get() = Position(active.sentenceId, active.startToken)

    /** Words before the active chunk / meta.word_count, clamped (SPEC_NOTES 8a). */
    val percent: Double
        get() = if (book.wordCount <= 0) 0.0
        else minOf(100.0, chunks.wordsBefore[index].toDouble() / book.wordCount * 100)
}

/** Pure reducer with handle_key semantics (src/kert/reader/state.py, §16.3). */
object Reader {
    const val WIDTH_MIN = 5
    const val WIDTH_MAX = 12

    fun initial(book: BookContent, settings: Settings, position: Position): ReaderState {
        val chunks = Chunks.build(book, settings.chunkWidth)
        if (chunks.spans.isEmpty()) throw KertFormatException("This book has no text to read.")
        return ReaderState(book, settings, chunks, resolve(chunks, position))
    }

    fun reduce(state: ReaderState, action: Action): ReaderState {
        val s = state.copy(effects = emptyList())
        val last = s.chunks.spans.size - 1
        return when (action) {
            Action.Next -> step(s, 1)
            Action.Previous -> step(s, -1)
            Action.NextBlock -> s.chunks.blockRange(s.index).last.let {
                if (it == last) s else s.copy(index = it + 1)
            }
            Action.PreviousBlock -> s.chunks.blockRange(s.index).first.let {
                if (it == 0) s else s.copy(index = s.chunks.blockRange(it - 1).first)
            }
            Action.First -> s.copy(index = 0)
            Action.Last -> s.copy(index = last)
            is Action.GotoPercent -> goto(s, action.percent)
            is Action.SetWidth -> setWidth(s, action.width)
            Action.PreviousSentence, Action.NextSentence, Action.PeekStart, Action.PeekEnd,
            is Action.SetMode,
            -> TODO()
            is Action.SetTheme -> s.copy(
                settings = s.settings.copy(theme = action.theme),
                effects = listOf(Effect.SaveSetting("theme", action.theme.storage)),
            )
        }
    }

    /** Chunk containing the token, else the sentence's first chunk, else 0 (§5). */
    private fun resolve(chunks: Chunks, position: Position): Int {
        var first = -1
        chunks.spans.forEachIndexed { i, span ->
            if (span.sentenceId == position.sentenceId) {
                if (position.chunkStartToken in span.startToken until span.endToken) return i
                if (first < 0) first = i
            }
        }
        return maxOf(first, 0)
    }

    private fun step(s: ReaderState, direction: Int): ReaderState {
        val target = s.index + direction
        if (target !in s.chunks.spans.indices) return s
        val left = Effect.Advance(s.active.sentenceId, s.chunks.words[s.index], direction)
        return s.copy(index = target, effects = listOf(left))
    }

    private fun goto(s: ReaderState, percent: Double): ReaderState {
        val target = percent / 100 * s.book.wordCount
        // minBy keeps the first of equally near chunks: ties go to the earlier one.
        val index = s.chunks.wordsBefore.indices.minBy { kotlin.math.abs(s.chunks.wordsBefore[it] - target) }
        return s.copy(index = index)
    }

    private fun setWidth(s: ReaderState, width: Int): ReaderState {
        if (width !in WIDTH_MIN..WIDTH_MAX) return s
        val chunks = Chunks.build(s.book, width)
        return s.copy(
            settings = s.settings.copy(chunkWidth = width),
            chunks = chunks,
            index = resolve(chunks, s.position),
            effects = listOf(Effect.SaveSetting("chunk_width", "$width")),
        )
    }
}
