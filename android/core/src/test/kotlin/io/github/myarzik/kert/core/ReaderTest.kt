package io.github.myarzik.kert.core

import java.nio.file.Path
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.assertThrows
import org.junit.jupiter.api.io.TempDir
import org.junit.jupiter.params.ParameterizedTest
import org.junit.jupiter.params.provider.CsvSource

/** Port of tests/test_state.py (spec §5, §8, §16.3) on the same mini book. */
class ReaderTest {
    companion object {
        /** Whitespace-separated words plus the final period, like tests/helpers.py. */
        fun sentence(id: Long, blockId: Long, seq: Int, text: String, vararg cands: Pair<Int, Double>): Sentence {
            val tokens = mutableListOf<TokenSpan>()
            var pos = 0
            for (word in text.dropLast(1).split(" ")) {
                tokens += TokenSpan(pos, pos + word.length)
                pos += word.length + 1
            }
            tokens += TokenSpan(text.length - 1, text.length)
            return Sentence(id, blockId, seq, text, tokens, cands.map { SplitCandidate(it.first, it.second) })
        }

        /**
         * helpers.mini_book: 22 words. At W=5 the chunks are
         * 0 S1[0,3) 2w | 1 S2[0,5) 5w | 2 S2[5,10) 4w | 3 S3[0,3) 2w | 4 S4[0,5) 5w | 5 S4[5,10) 4w
         * and at W=8 one chunk per sentence.
         */
        fun miniBook(wordCount: Int = 22) = BookContent(
            meta = mapOf("schema_version" to "1", "word_count" to "$wordCount"),
            blocks = listOf(Block(1, "paragraph", null), Block(2, "paragraph", null), Block(3, "paragraph", null)),
            sentences = listOf(
                sentence(1, 1, 0, "Глава один."),
                sentence(2, 2, 0, "alpha bravo charlie delta echo foxtrot golf hotel india.", 5 to 1.0),
                sentence(3, 2, 1, "Short one."),
                sentence(4, 3, 0, "one two three four five six seven eight nine.", 5 to 1.0),
            ),
            wordCount = wordCount,
        )

        val W5 = Settings(chunkWidth = 5, theme = Theme.DARK)
        val W8 = Settings(chunkWidth = 8, theme = Theme.DARK)
    }

    private val startsW5 = listOf(1L to 0, 2L to 0, 2L to 5, 3L to 0, 4L to 0, 4L to 5)
    private val startsW8 = listOf(1L to 0, 2L to 0, 3L to 0, 4L to 0)

    private fun at(index: Int, settings: Settings = W5): ReaderState {
        val (sid, token) = (if (settings.chunkWidth == 8) startsW8 else startsW5)[index]
        val state = Reader.initial(miniBook(), settings, Position(sid, token))
        assertEquals(index, state.index)
        return state
    }

    private fun ReaderState.then(vararg actions: Action) =
        actions.fold(this) { state, action -> Reader.reduce(state, action) }

    // --- Position resolution (§5 step 4) -------------------------------------------------

    @ParameterizedTest
    @CsvSource("1,0,0", "2,5,2", "2,3,1", "2,7,2", "4,99,4", "99,0,0")
    fun `initial position resolves to the nearest chunk`(sid: Long, token: Int, index: Int) =
        assertEquals(index, Reader.initial(miniBook(), W5, Position(sid, token)).index)

    @Test
    fun `position reports the active chunk start`() = assertEquals(Position(2, 5), at(2).position)

    @Test
    fun `initial state has no effects`() = assertEquals(emptyList<Effect>(), at(0).effects)

    @Test
    fun `a book without text is rejected`() {
        val empty = miniBook().copy(sentences = emptyList(), blocks = emptyList())
        assertThrows<KertFormatException> { Reader.initial(empty, W5, Position(1, 0)) }
    }

    // --- Percent (§7.1, word-based) ---------------------------------------------------------

    @ParameterizedTest
    @CsvSource("0,0", "1,2", "2,7", "5,18")
    fun `percent is words before over word count`(index: Int, before: Int) =
        assertEquals(before / 22.0 * 100, at(index).percent, 1e-9)

    @Test
    fun `percent is stable across widths`() = assertEquals(at(1, W5).percent, at(1, W8).percent)

    @Test
    fun `percent counts only words`() {
        val book = BookContent(
            meta = mapOf(), blocks = listOf(Block(1, "dialogue", null)),
            sentences = listOf(sentence(1, 1, 0, "— Да , 10 раз."), sentence(2, 1, 1, "Ок.")),
            wordCount = 4,
        )
        assertEquals(75.0, Reader.initial(book, W8, Position(2, 0)).percent, 1e-9)
    }

    @Test
    fun `percent is clamped and safe for zero word count`() {
        assertEquals(100.0, Reader.initial(miniBook(10), W5, Position(4, 5)).percent)
        assertEquals(0.0, Reader.initial(miniBook(0), W5, Position(4, 5)).percent)
    }

    // --- Chunk steps and advance_log effects (§8.1, D5) --------------------------------------

    @Test
    fun `next logs the chunk left`() {
        val state = at(1).then(Action.Next)
        assertEquals(2, state.index)
        assertEquals(listOf(Effect.Advance(2, 5, 1)), state.effects)
    }

    @Test
    fun `previous logs the chunk left`() {
        val state = at(2).then(Action.Previous)
        assertEquals(1, state.index)
        assertEquals(listOf(Effect.Advance(2, 4, -1)), state.effects)
    }

    @Test
    fun `steps at the book edges are no-ops`() {
        assertEquals(5 to emptyList<Effect>(), at(5).then(Action.Next).let { it.index to it.effects })
        assertEquals(0 to emptyList<Effect>(), at(0).then(Action.Previous).let { it.index to it.effects })
    }

    @Test
    fun `effects are per action`() = assertEquals(emptyList<Effect>(), at(1).then(Action.Next, Action.First).effects)

    // --- Block and book jumps (not logged) ------------------------------------------------------

    @ParameterizedTest
    @CsvSource("1,4", "2,4", "3,4", "0,1", "4,4")
    fun `next block goes to its first chunk`(start: Int, index: Int) {
        val state = at(start).then(Action.NextBlock)
        assertEquals(index, state.index)
        assertEquals(emptyList<Effect>(), state.effects)
    }

    @ParameterizedTest
    @CsvSource("5,1", "4,1", "2,0", "3,0", "0,0")
    fun `previous block goes to its first chunk`(start: Int, index: Int) =
        assertEquals(index, at(start).then(Action.PreviousBlock).index)

    @Test
    fun `first and last`() {
        assertEquals(0, at(5).then(Action.First).index)
        assertEquals(5, at(0).then(Action.Last).index)
    }

    // --- Goto (§8.2) --------------------------------------------------------------------------

    @ParameterizedTest
    @CsvSource("0,0", "50,3", "60,4", "70,4", "100,5")
    fun `goto jumps to the chunk nearest in words`(percent: Double, index: Int) {
        val state = at(2).then(Action.GotoPercent(percent))
        assertEquals(index, state.index)
        assertEquals(emptyList<Effect>(), state.effects)
    }

    // --- Settings (§5 re-chunk, §8.4) -----------------------------------------------------------

    @Test
    fun `set width rechunks and keeps the active token`() {
        val state = at(2).then(Action.SetWidth(8))
        assertEquals(W8, state.settings)
        assertEquals(1, state.index)
        assertEquals(Position(2, 0), state.position)
        assertEquals(listOf(Effect.SaveSetting("chunk_width", "8")), state.effects)
    }

    @Test
    fun `set width back and forth`() {
        val state = at(5).then(Action.SetWidth(8), Action.SetWidth(5))
        assertEquals(4, state.index)
        assertEquals(13 / 22.0 * 100, state.percent, 1e-9)
    }

    @Test
    fun `navigation uses the new width`() {
        val state = at(1).then(Action.SetWidth(8), Action.Next)
        assertEquals(Position(3, 0), state.position)
        assertEquals(listOf(Effect.Advance(2, 9, 1)), state.effects)
    }

    @ParameterizedTest
    @CsvSource("4", "13", "0")
    fun `width outside 5 to 12 is ignored`(width: Int) {
        val state = at(2).then(Action.SetWidth(width))
        assertEquals(W5 to 2, state.settings to state.index)
        assertEquals(emptyList<Effect>(), state.effects)
    }

    @Test
    fun `set theme`() {
        val state = at(2).then(Action.SetTheme(Theme.LIGHT))
        assertEquals(Settings(5, Theme.LIGHT), state.settings)
        assertEquals(2, state.index)
        assertEquals(listOf(Effect.SaveSetting("theme", "light")), state.effects)
    }

    // --- Python reference cross-check (§16.6) ------------------------------------------------------

    @TempDir
    lateinit var tmp: Path

    @Test
    fun `chunk words and words before match Python for every fixture and width`() {
        for (reference in Reference.books) {
            val book = JdbcConnection(Reference.copy(reference.file, tmp)).use { KertReader.read(it) }
            for ((width, expected) in reference.widths) {
                val chunks = Chunks.build(book, width.toInt())
                assertEquals(expected.map { it[3] }, chunks.words, "${reference.file} W=$width words")
                assertEquals(expected.map { it[4] }, chunks.wordsBefore, "${reference.file} W=$width before")
            }
            assertTrue(reference.word_count == book.wordCount)
        }
    }
}
