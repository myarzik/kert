package io.github.myarzik.kert.core

data class Position(val sentenceId: Long, val chunkStartToken: Int)

enum class Theme(val storage: String) { DARK("dark"), LIGHT("light") }

/** §17.2 reading modes; the unit highlighted and stepped through. */
enum class Mode(val storage: String) { CHUNK("chunk"), SENTENCE("sentence"), PARAGRAPH("paragraph") }

enum class GoalUnit(val storage: String, val max: Int) { MINUTES("m", 600), WORDS("w", 100_000) }

/** A session goal (§17.6): [amount] minutes or words, counted from when it was armed. */
data class Goal(val amount: Int, val unit: GoalUnit, val armedAt: Double, val startWords: Int)

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
    data class SetGoal(val amount: Int, val unit: GoalUnit) : Action
    data object GoalOff : Action
    data object GoalAgain : Action
}

sealed interface Effect {
    /** An advance_log row (§17.4); the session adds the clock and the mode. */
    data class Advance(
        val sentenceId: Long,
        val chunkWords: Int,
        val direction: Int,
        val kind: String = "step",
    ) : Effect
    data class SaveSetting(val key: String, val value: String) : Effect
}

/**
 * Book-wide list of reading units at one width and mode (§6, §17.2). A unit is
 * a chunk, a sentence or a whole block: [spans] anchors unit i at its first
 * sentence and token, [ends] holds the (sentence index, end token) where it stops.
 */
class Chunks(
    val spans: List<ChunkSpan>,
    val words: List<Int>,
    val wordsBefore: List<Int>,
    val blockIds: List<Long>,
    val ends: List<Pair<Int, Int>>,
    /** Index into [BookContent.sentences] of each unit's first sentence. */
    val sentencePos: List<Int>,
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
            val pos = book.sentences.withIndex().associate { (i, s) -> s.id to i }
            val units = units(book, width, mode, pos)
            val words = units.map { (span, last, end) ->
                countWords(book, pos.getValue(span.sentenceId), span.startToken, last, end)
            }
            return Chunks(
                spans = units.map { it.first },
                words = words,
                wordsBefore = words.runningFold(0, Int::plus).dropLast(1),
                blockIds = units.map { book.sentences[pos.getValue(it.first.sentenceId)].blockId },
                ends = units.map { it.second to it.third },
                sentencePos = units.map { pos.getValue(it.first.sentenceId) },
            )
        }

        private fun units(
            book: BookContent,
            width: Int,
            mode: Mode,
            pos: Map<Long, Int>,
        ): List<Triple<ChunkSpan, Int, Int>> {
            if (mode == Mode.CHUNK) {
                return Chunker.assemble(book.sentences, width).map { Triple(it, pos.getValue(it.sentenceId), it.endToken) }
            }
            val units = mutableListOf<Triple<ChunkSpan, Int, Int>>()
            book.sentences.forEachIndexed { i, sentence ->
                val end = sentence.tokens.size
                val sameBlock = units.isNotEmpty() && book.sentences[units.last().second].blockId == sentence.blockId
                if (mode == Mode.PARAGRAPH && sameBlock) {
                    units[units.size - 1] = Triple(units.last().first, i, end)
                } else {
                    units += Triple(ChunkSpan(sentence.id, 0, end), i, end)
                }
            }
            return units
        }

        private fun countWords(book: BookContent, first: Int, start: Int, last: Int, end: Int): Int =
            (first..last).sumOf { i ->
                val sentence = book.sentences[i]
                val from = if (i == first) start else 0
                val to = if (i == last) end else sentence.tokens.size
                sentence.tokens.subList(from, to).count { Words.isWord(sentence.text.substring(it.start, it.end)) }
            }
    }
}

data class ReaderState(
    val book: BookContent,
    val settings: Settings,
    val chunks: Chunks,
    val index: Int,
    val peek: Boolean = false,
    val now: Double = 0.0,
    val log: List<LogRow> = emptyList(),
    val goal: Goal? = null,
    val lastGoal: Pair<Int, GoalUnit>? = null,
    val message: String? = null,
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
    const val GOAL_REACHED = "goal reached"

    fun goalSegment(state: ReaderState): String? = TODO()

    fun initial(book: BookContent, settings: Settings, position: Position): ReaderState {
        val chunks = Chunks.build(book, settings.chunkWidth, settings.mode)
        if (chunks.spans.isEmpty()) throw KertFormatException("This book has no text to read.")
        return ReaderState(book, settings, chunks, resolve(book, chunks, position))
    }

    fun reduce(state: ReaderState, action: Action): ReaderState {
        val s = state.copy(effects = emptyList())
        // §17.3: the action that ends peek is consumed.
        if (s.peek) return s.copy(peek = false)
        val last = s.chunks.spans.size - 1
        return when (action) {
            Action.Next -> if (s.index < last) move(s, s.index + 1, "step") else s
            Action.Previous -> if (s.index > 0) move(s, s.index - 1, "step") else s
            Action.NextBlock -> s.chunks.blockRange(s.index).last.let {
                if (it == last) s else move(s, it + 1, "block")
            }
            Action.PreviousBlock -> s.chunks.blockRange(s.index).first.let {
                if (it == 0) s else move(s, s.chunks.blockRange(it - 1).first, "block")
            }
            Action.First -> move(s, 0, "jump")
            Action.Last -> move(s, last, "jump")
            is Action.GotoPercent -> goto(s, action.percent)
            is Action.SetWidth -> setWidth(s, action.width)
            is Action.SetTheme -> s.copy(
                settings = s.settings.copy(theme = action.theme),
                effects = listOf(Effect.SaveSetting("theme", action.theme.storage)),
            )
            Action.PreviousSentence -> previousSentence(s)
            Action.NextSentence -> nextSentence(s)
            Action.PeekStart -> peek(s)
            Action.PeekEnd -> s
            is Action.SetGoal, Action.GoalOff, Action.GoalAgain -> TODO()
            is Action.SetMode -> reassemble(
                s, s.settings.copy(mode = action.mode), Effect.SaveSetting("mode", action.mode.storage),
            )
        }
    }

    /** Unit containing the token, else the sentence's first unit, else 0 (§5). */
    private fun resolve(book: BookContent, chunks: Chunks, position: Position): Int {
        val target = book.sentences.indexOfFirst { it.id == position.sentenceId }
        if (target < 0) return 0
        var first = -1
        chunks.spans.forEachIndexed { i, span ->
            val (last, end) = chunks.ends[i]
            if (target !in chunks.sentencePos[i]..last) return@forEachIndexed
            val from = if (chunks.sentencePos[i] == target) span.startToken else 0
            if (position.chunkStartToken >= from && (last > target || position.chunkStartToken < end)) return i
            if (first < 0) first = i
        }
        return maxOf(first, 0)
    }

    /** Go to unit [target], logging the unit left (§17.4); the same unit is a no-op. */
    private fun move(s: ReaderState, target: Int, kind: String): ReaderState {
        if (target == s.index) return s
        val left = Effect.Advance(s.active.sentenceId, s.chunks.words[s.index], if (target > s.index) 1 else -1, kind)
        return s.copy(index = target, effects = listOf(left))
    }

    private fun sentenceStart(chunks: Chunks, index: Int): Int {
        var i = index
        while (i > 0 && chunks.sentencePos[i - 1] == chunks.sentencePos[i]) i--
        return i
    }

    private fun previousSentence(s: ReaderState): ReaderState {
        var start = sentenceStart(s.chunks, s.index)
        if (start == s.index && start > 0) start = sentenceStart(s.chunks, start - 1)
        return move(s, start, "sentence")
    }

    private fun nextSentence(s: ReaderState): ReaderState {
        val pos = s.chunks.sentencePos
        var target = s.index
        while (target < pos.size && pos[target] == pos[s.index]) target++
        return if (target == pos.size) s else move(s, target, "sentence")
    }

    private fun peek(s: ReaderState): ReaderState {
        if (s.index == 0) return s
        val shown = s.index - 1
        val row = Effect.Advance(s.chunks.spans[shown].sentenceId, s.chunks.words[shown], 0, "peek")
        return s.copy(peek = true, effects = listOf(row))
    }

    private fun goto(s: ReaderState, percent: Double): ReaderState {
        val target = percent / 100 * s.book.wordCount
        // minBy keeps the first of equally near chunks: ties go to the earlier one.
        val index = s.chunks.wordsBefore.indices.minBy { kotlin.math.abs(s.chunks.wordsBefore[it] - target) }
        return move(s, index, "jump")
    }

    private fun setWidth(s: ReaderState, width: Int): ReaderState {
        if (width !in WIDTH_MIN..WIDTH_MAX) return s
        return reassemble(s, s.settings.copy(chunkWidth = width), Effect.SaveSetting("chunk_width", "$width"))
    }

    /** New width or mode: rebuild the units and keep the place (§5, §17.2). */
    private fun reassemble(s: ReaderState, settings: Settings, saved: Effect): ReaderState {
        val chunks = Chunks.build(s.book, settings.chunkWidth, settings.mode)
        return s.copy(
            settings = settings,
            chunks = chunks,
            index = resolve(s.book, chunks, s.position),
            effects = listOf(saved),
        )
    }
}
