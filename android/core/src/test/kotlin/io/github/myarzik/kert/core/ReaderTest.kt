package io.github.myarzik.kert.core

import java.nio.file.Path
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertFalse
import org.junit.jupiter.api.Assertions.assertNull
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
    fun `effects are per action`() = assertEquals(emptyList<Effect>(), at(1).then(Action.Next, Action.PeekEnd).effects)

    // --- Block and book jumps (logged per §17.4) ---------------------------------------------

    /** (sentence id, words) of each W=5 chunk, see [miniBook]. */
    private val chunksW5 = listOf(1L to 2, 2L to 5, 2L to 4, 3L to 2, 4L to 5, 4L to 4)

    private fun left(index: Int, direction: Int, kind: String) =
        chunksW5[index].let { (sid, words) -> Effect.Advance(sid, words, direction, kind) }

    private fun effectsOf(start: Int, index: Int, direction: Int, kind: String) =
        if (start == index) emptyList() else listOf(left(start, direction, kind))

    @ParameterizedTest
    @CsvSource("1,4", "2,4", "3,4", "0,1", "4,4")
    fun `next block goes to its first chunk`(start: Int, index: Int) {
        val state = at(start).then(Action.NextBlock)
        assertEquals(index, state.index)
        assertEquals(effectsOf(start, index, 1, "block"), state.effects)
    }

    @ParameterizedTest
    @CsvSource("5,1", "4,1", "2,0", "3,0", "0,0")
    fun `previous block goes to its first chunk`(start: Int, index: Int) {
        val state = at(start).then(Action.PreviousBlock)
        assertEquals(index, state.index)
        assertEquals(effectsOf(start, index, -1, "block"), state.effects)
    }

    @Test
    fun `first and last`() {
        assertEquals(0, at(5).then(Action.First).index)
        assertEquals(listOf(left(5, -1, "jump")), at(5).then(Action.First).effects)
        assertEquals(5, at(0).then(Action.Last).index)
        assertEquals(listOf(left(0, 1, "jump")), at(0).then(Action.Last).effects)
        assertEquals(emptyList<Effect>(), at(0).then(Action.First).effects)
    }

    // --- Goto (§8.2) --------------------------------------------------------------------------

    @ParameterizedTest
    @CsvSource("0,0", "50,3", "60,4", "70,4", "100,5")
    fun `goto jumps to the chunk nearest in words`(percent: Double, index: Int) {
        val state = at(2).then(Action.GotoPercent(percent))
        assertEquals(index, state.index)
        assertEquals(listOf(left(2, if (index > 2) 1 else -1, "jump")), state.effects)
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

    // --- R1 cheap regressions (§17.3, §17.12) --------------------------------------------------

    @ParameterizedTest
    @CsvSource("2,1", "1,0", "3,1", "4,3", "0,0")
    fun `previous sentence`(start: Int, index: Int) {
        val state = at(start).then(Action.PreviousSentence)
        assertEquals(index, state.index)
        assertEquals(effectsOf(start, index, -1, "sentence"), state.effects)
    }

    @ParameterizedTest
    @CsvSource("0,1", "1,3", "2,3", "3,4", "4,4", "5,5")
    fun `next sentence`(start: Int, index: Int) {
        val state = at(start).then(Action.NextSentence)
        assertEquals(index, state.index)
        assertEquals(effectsOf(start, index, 1, "sentence"), state.effects)
    }

    @Test
    fun `peek shows the previous unit while held, without moving`() {
        val held = at(2).then(Action.PeekStart)
        assertTrue(held.peek)
        assertEquals(2, held.index)
        assertEquals(listOf(Effect.Advance(2, 5, 0, "peek")), held.effects)

        val released = held.then(Action.PeekEnd)
        assertEquals(false, released.peek)
        assertEquals(emptyList<Effect>(), released.effects)
    }

    @Test
    fun `any other action ends peek and is consumed`() {
        val state = at(2).then(Action.PeekStart, Action.Next)
        assertEquals(false, state.peek)
        assertEquals(2, state.index)
        assertEquals(emptyList<Effect>(), state.effects)
    }

    @Test
    fun `peek at the first unit is a no-op`() {
        val state = at(0).then(Action.PeekStart)
        assertEquals(false, state.peek)
        assertEquals(emptyList<Effect>(), state.effects)
    }

    // --- Reading modes (§17.2) ------------------------------------------------------------------

    private val sentenceMode = W5.copy(mode = Mode.SENTENCE)
    private val paragraphMode = W5.copy(mode = Mode.PARAGRAPH)

    private fun inMode(settings: Settings, sid: Long, token: Int = 0) =
        Reader.initial(miniBook(), settings, Position(sid, token))

    @Test
    fun `mode defaults to chunk`() = assertEquals(Mode.CHUNK, W5.mode)

    @Test
    fun `sentence mode units are whole sentences`() {
        val state = inMode(sentenceMode, 2).then(Action.Next)
        assertEquals(Position(3, 0), state.position)
        assertEquals(listOf(Effect.Advance(2, 9, 1, "step")), state.effects)
        assertEquals(11.0 / 22 * 100, state.percent, 1e-9)
    }

    @Test
    fun `paragraph mode units are whole blocks`() {
        val state = inMode(paragraphMode, 2).then(Action.Next)
        assertEquals(Position(4, 0), state.position)
        assertEquals(listOf(Effect.Advance(2, 11, 1, "step")), state.effects)
        assertEquals(13.0 / 22 * 100, state.percent, 1e-9)
        assertEquals(emptyList<Effect>(), state.then(Action.Next).effects)
    }

    @ParameterizedTest
    @CsvSource("3,0,2,0", "2,7,2,0")
    fun `paragraph mode resolves inside a block to its start`(sid: Long, token: Int, rsid: Long, rtoken: Int) =
        assertEquals(Position(rsid, rtoken), inMode(paragraphMode, sid, token).position)

    @Test
    fun `sentence mode resolves mid sentence to its start`() =
        assertEquals(Position(2, 0), inMode(sentenceMode, 2, 5).position)

    @Test
    fun `paragraph mode regressions and peek move by block`() {
        val last = inMode(paragraphMode, 4)
        assertEquals(Position(2, 0), last.then(Action.PreviousSentence).position)
        assertEquals(listOf(Effect.Advance(4, 9, -1, "sentence")), last.then(Action.PreviousSentence).effects)
        assertEquals(Position(2, 0), inMode(paragraphMode, 1).then(Action.NextSentence).position)
        assertEquals(listOf(Effect.Advance(2, 11, 0, "peek")), last.then(Action.PeekStart).effects)
    }

    @Test
    fun `paragraph mode goto is word based`() =
        assertEquals(Position(4, 0), inMode(paragraphMode, 1).then(Action.GotoPercent(50.0)).position)

    @ParameterizedTest
    @CsvSource("2,SENTENCE,2", "3,PARAGRAPH,2", "5,PARAGRAPH,4")
    fun `set mode reassembles and keeps the place`(start: Int, mode: Mode, sid: Long) {
        val state = at(start).then(Action.SetMode(mode))
        assertEquals(mode, state.settings.mode)
        assertEquals(Position(sid, 0), state.position)
        assertEquals(listOf(Effect.SaveSetting("mode", mode.storage)), state.effects)
    }

    @Test
    fun `set mode back to chunk returns to the chunk of the unit start`() =
        assertEquals(1, at(2).then(Action.SetMode(Mode.SENTENCE), Action.SetMode(Mode.CHUNK)).index)

    @Test
    fun `width is stored in other modes and used back in chunk mode`() {
        val state = inMode(sentenceMode, 2).then(Action.SetWidth(8))
        assertEquals(8, state.settings.chunkWidth)
        assertEquals(Position(2, 0), state.position)
        assertEquals(at(1, W8).chunks.spans, state.then(Action.SetMode(Mode.CHUNK)).chunks.spans)
    }

    @Test
    fun `mode units match Python for every fixture`() {
        for (reference in Reference.books) {
            val book = JdbcConnection(Reference.copy(reference.file, tmp)).use { KertReader.read(it) }
            for ((name, expected) in reference.modes) {
                val chunks = Chunks.build(book, 5, Mode.entries.single { it.storage == name })
                val actual = chunks.spans.indices.map { i ->
                    val (last, end) = chunks.ends[i]
                    listOf(
                        chunks.spans[i].sentenceId.toInt(), chunks.spans[i].startToken,
                        book.sentences[last].id.toInt(), end, chunks.words[i], chunks.wordsBefore[i],
                    )
                }
                assertEquals(expected, actual, "${reference.file} mode=$name")
            }
        }
    }

    // --- R5 session goal (§17.6, §17.12) -------------------------------------------------------
    // mini book at W=5: words before each chunk 0, 2, 7, 11, 13, 18.

    private fun ReaderState.at(now: Double) = copy(now = now)

    @Test
    fun `goal in words is reached by reading from the arming place`() {
        var state = at(0).then(Action.SetGoal(5, GoalUnit.WORDS))
        assertEquals("goal 5w", state.message)
        state = state.then(Action.Next)
        assertNull(state.message)
        state = state.then(Action.Next)
        assertEquals(Reader.GOAL_REACHED, state.message)
        assertNull(state.goal)
    }

    @Test
    fun `goal again rearms from the current place`() {
        // SkipRecall skips the goal checkpoint (§17.8) offered when the goal is reached.
        val state = at(0).then(
            Action.SetGoal(5, GoalUnit.WORDS), Action.Next, Action.Next, Action.SkipRecall, Action.GoalAgain,
        )
        assertEquals("goal 5w", state.message)
        assertNull(state.then(Action.Next).message)
        assertEquals(Reader.GOAL_REACHED, state.then(Action.Next, Action.Next).message)
    }

    @Test
    fun `goal again without a previous goal`() {
        val state = at(0).then(Action.GoalAgain)
        assertNull(state.goal)
        assertEquals("no goal to re-arm", state.message)
    }

    @Test
    fun `goal off clears the goal`() {
        val state = at(0).then(Action.SetGoal(5, GoalUnit.WORDS), Action.GoalOff)
        assertNull(state.goal)
        assertEquals("goal off", state.message)
        assertNull(state.then(Action.Next, Action.Next).message)
    }

    @ParameterizedTest
    @CsvSource("0,WORDS", "100001,WORDS", "0,MINUTES", "601,MINUTES")
    fun `out of range goals are ignored`(amount: Int, unit: GoalUnit) =
        assertNull(at(0).then(Action.SetGoal(amount, unit)).goal)

    @Test
    fun `moves are kept as log rows with the clock`() =
        assertEquals(LogRow(5.0, 2, 1, "step", "chunk"), Reader.reduce(at(0).at(5.0), Action.Next).log.last())

    @Test
    fun `goal in minutes counts active reading time`() {
        var state = Reader.reduce(at(0).at(100.0), Action.SetGoal(1, GoalUnit.MINUTES))
        state = Reader.reduce(state.at(100.0), Action.Next) // first row: no dwell yet
        state = Reader.reduce(state.at(130.0), Action.Next) // 30 s
        assertNull(state.message)
        state = Reader.reduce(state.at(161.0), Action.Next) // 61 s
        assertEquals(Reader.GOAL_REACHED, state.message)
    }

    @Test
    fun `idle time does not count toward a minutes goal`() {
        var state = Reader.reduce(at(0).at(100.0), Action.SetGoal(1, GoalUnit.MINUTES))
        state = Reader.reduce(state.at(100.0), Action.Next)
        state = Reader.reduce(state.at(200.0), Action.Next) // 100 s: idle, discarded
        assertNull(state.message)
    }

    // --- Goal status segment (tests/test_render.py §17.6) --------------------------------------

    private fun fastLog() = List(31) { LogRow(1000.0 + it * 2.0, 4, 1, "step", "chunk") }

    /** Clock past the log, so none of its dwells count after arming. */
    private fun goalAt(amount: Int, unit: GoalUnit, log: List<LogRow> = emptyList()) =
        Reader.reduce(at(0).copy(now = 2000.0, log = log), Action.SetGoal(amount, unit))

    @Test
    fun `goal segments`() {
        assertEquals("▸ 20 w", Reader.goalSegment(goalAt(20, GoalUnit.WORDS)))
        assertEquals("▸ 20 w · ~1 min", Reader.goalSegment(goalAt(20, GoalUnit.WORDS, fastLog())))
        assertEquals("▸ 6 min", Reader.goalSegment(goalAt(6, GoalUnit.MINUTES)))
        assertEquals("▸ 6 min · ~720 w", Reader.goalSegment(goalAt(6, GoalUnit.MINUTES, fastLog())))
        assertEquals("▸ 18 w", Reader.goalSegment(goalAt(20, GoalUnit.WORDS).then(Action.Next)))
        assertNull(Reader.goalSegment(at(0)))
    }

    // --- R3/R4 re-entry: recall card, rating, recap (§17.7, §17.12) ----------------------------

    private val hour = 3600.0

    /** State on chunk [index] opened [gap] seconds after the last logged move. */
    private fun reopened(index: Int, gap: Double, settings: Settings = W5, logRows: Int = 1): ReaderState {
        val (sid, token) = startsW5[index]
        val log = List(logRows) { LogRow(1000.0 - it, 2, 1, "step", "chunk") }
        return Reader.start(Reader.initial(miniBook(), settings, Position(sid, token), now = 1000.0 + gap, log = log))
    }

    private fun openCheckpoint(rating: Int?, sentenceId: Long = 4) =
        Effect.Checkpoint("open", "chunk", sentenceId, sentenceId, 0, null, rating)

    @Test
    fun `long gap starts with the recall card`() = assertEquals(Overlay.RECALL, reopened(4, hour).overlay)

    @Test
    fun `recall then rating then recap`() {
        var state = reopened(4, hour).then(Action.Continue)
        assertEquals(Overlay.RATING, state.overlay)

        state = state.then(Action.Rate(2))
        assertEquals(listOf(openCheckpoint(2)), state.effects)
        assertEquals(Overlay.RECAP, state.overlay)

        state = state.then(Action.Continue)
        assertNull(state.overlay)
        assertEquals(4, state.index)
        assertEquals(emptyList<Effect>(), state.effects)
    }

    @Test
    fun `rating buttons`() {
        for (rating in listOf(2, 1, 0, null)) {
            assertEquals(listOf(openCheckpoint(rating)), reopened(4, hour).then(Action.Continue, Action.Rate(rating)).effects)
        }
    }

    @Test
    fun `other actions keep the rating card`() {
        val state = reopened(4, hour).then(
            Action.Continue, Action.Next, Action.Continue, Action.NextBlock, Action.SubmitRecall("x"), Action.Rate(3),
        )
        assertEquals(Overlay.RATING, state.overlay)
        assertEquals(4, state.index)
        assertFalse(state.quit)
        assertEquals(emptyList<Effect>(), state.effects)
    }

    @Test
    fun `any action dismisses the recap and is consumed`() {
        val state = reopened(4, 0.0).then(Action.Next)
        assertNull(state.overlay)
        assertEquals(4, state.index)
        assertEquals(emptyList<Effect>(), state.effects)
    }

    @Test
    fun `short gap goes straight to the recap`() = assertEquals(Overlay.RECAP, reopened(4, hour - 1).overlay)

    @Test
    fun `empty log has no gap and no recall card`() =
        assertEquals(Overlay.RECAP, reopened(4, hour, logRows = 0).overlay)

    @Test
    fun `book start has no recall and no recap`() = assertNull(reopened(0, hour).overlay)

    @Test
    fun `recap off after a short gap reads directly`() = assertNull(reopened(4, 60.0, W5.copy(recap = false)).overlay)

    @Test
    fun `recall off skips the card`() = assertEquals(Overlay.RECAP, reopened(4, hour, W5.copy(recall = false)).overlay)

    @Test
    fun `recall without recap ends in reading`() =
        assertNull(reopened(4, hour, W5.copy(recap = false)).then(Action.Continue, Action.Rate(2)).overlay)

    @Test
    fun `recall gap is a setting`() {
        val settings = W5.copy(recallGapMinutes = 5)
        assertEquals(Overlay.RECALL, reopened(4, 301.0, settings).overlay)
        assertEquals(Overlay.RECAP, reopened(4, 299.0, settings).overlay)
    }

    @ParameterizedTest
    // back 2 + 4 + 5 = 11 >= 10 words, across the block boundary; at least one whole unit; the book start bounds it
    @CsvSource("4,10,1", "4,1,3", "2,40,0")
    fun `recap takes whole units back to the word budget`(index: Int, words: Int, start: Int) =
        assertEquals(start, Reader.recapStart(reopened(index, 0.0, W5.copy(recapWords = words))))

    @Test
    fun `no recap at the book start`() = assertNull(Reader.recapStart(reopened(0, 0.0)))

    @Test
    fun `recap and recall switches are saved`() {
        val off = at(0).then(Action.SetRecap(false))
        assertFalse(off.settings.recap)
        assertEquals(listOf(Effect.SaveSetting("recap", "off")), off.effects)
        val on = off.then(Action.SetRecall(false), Action.SetRecall(true))
        assertTrue(on.settings.recall)
        assertEquals(listOf(Effect.SaveSetting("recall", "on")), on.effects)
    }

    // --- R6 checkpoint recall: quit and goal triggers (§17.8, §17.12) --------------------------

    private val w12 = Settings(chunkWidth = 12, theme = Theme.DARK)

    /** One block per 5 sentences of 10 words each: 600 words, one chunk per sentence at W=12. */
    private fun longBook(sentences: Int = 60) = BookContent(
        meta = mapOf("schema_version" to "1", "word_count" to "${sentences * 10}"),
        blocks = (1..sentences / 5).map { Block(it.toLong(), "paragraph", null) },
        sentences = (1..sentences).map {
            sentence(it.toLong(), ((it - 1) / 5 + 1).toLong(), (it - 1) % 5, List(10) { "word" }.joinToString(" ") + ".")
        },
        wordCount = sentences * 10,
    )

    /** longBook state on sentence [sentenceId], reached by reading forward from [from]. */
    private fun longAt(sentenceId: Int, settings: Settings = w12, from: Int = 1) =
        Reader.initial(longBook(), settings, Position(from.toLong(), 0))
            .then(*Array(sentenceId - from) { Action.NextSentence })

    private fun quitCheckpoint(text: String?, rating: Int?, start: Long = 1, end: Long = 51, words: Int = 500) =
        Effect.Checkpoint("quit", "chunk", start, end, words, text, rating)

    @Test
    fun `quit before 500 words quits at once`() {
        val state = longAt(50).then(Action.Quit) // 490 words read
        assertTrue(state.quit)
        assertNull(state.overlay)
    }

    @Test
    fun `quit after 500 words offers the recall line`() {
        val state = longAt(51).then(Action.Quit) // 500 words read
        assertFalse(state.quit)
        assertEquals(Overlay.LINE, state.overlay)
    }

    @Test
    fun `quit checkpoint line then rating then exit`() {
        var state = longAt(51).then(Action.Quit, Action.SubmitRecall("он ушёл"))
        assertEquals(Overlay.RATING, state.overlay)
        assertEquals(emptyList<Effect>(), state.effects)

        state = state.then(Action.Rate(2))
        assertEquals(listOf(quitCheckpoint("он ушёл", 2)), state.effects)
        assertTrue(state.quit)
    }

    @Test
    fun `skip at the line skips the checkpoint and exits`() {
        val state = longAt(51).then(Action.Quit, Action.SkipRecall)
        assertTrue(state.quit)
        assertEquals(emptyList<Effect>(), state.effects)
    }

    @Test
    fun `skip at the rating writes the row without a rating`() {
        val state = longAt(51).then(Action.Quit, Action.SubmitRecall("a"), Action.Rate(null))
        assertEquals(listOf(quitCheckpoint("a", null)), state.effects)
        assertTrue(state.quit)
    }

    @Test
    fun `blank line is stored as no text`() =
        assertEquals(
            listOf(quitCheckpoint(null, 0)),
            longAt(51).then(Action.Quit, Action.SubmitRecall(" "), Action.Rate(0)).effects,
        )

    @Test
    fun `the line card ignores reading actions`() {
        val state = longAt(51).then(
            Action.Quit, Action.Next, Action.NextBlock, Action.Continue, Action.Rate(2),
            Action.SubmitRecall("a"), Action.Rate(2),
        )
        assertEquals(listOf(quitCheckpoint("a", 2)), state.effects)
        assertEquals(50, state.index)
    }

    @Test
    fun `back offers the quit checkpoint and a second back skips it`() {
        var state = longAt(51).then(Action.Quit)
        assertEquals(Overlay.LINE, state.overlay)
        state = state.then(Action.Quit)
        assertTrue(state.quit)
        assertEquals(emptyList<Effect>(), state.effects)
    }

    @Test
    fun `back at the rating skips too`() {
        val state = longAt(51).then(Action.Quit, Action.SubmitRecall("a"), Action.Quit)
        assertTrue(state.quit)
        assertEquals(emptyList<Effect>(), state.effects)
    }

    @Test
    fun `back while peeking quits`() = assertTrue(longAt(2).then(Action.PeekStart, Action.Quit).quit)

    @Test
    fun `recall off never offers a checkpoint`() =
        assertTrue(longAt(51, w12.copy(recall = false)).then(Action.Quit).quit)

    @Test
    fun `backward reading does not count toward the threshold`() =
        assertTrue(longAt(51).then(Action.First, Action.Quit).quit)

    @Test
    fun `the span starts where the session started`() {
        val state = longAt(56, from = 6).then(Action.Quit, Action.SubmitRecall("x"), Action.Rate(1))
        assertEquals(listOf(quitCheckpoint("x", 1, start = 6, end = 56)), state.effects)
    }

    @Test
    fun `goal reached offers a goal checkpoint and reading continues`() {
        // mini book: goal of 5 words reached on chunk 2 (S2 token 5), 7 words read.
        var state = at(0).then(Action.SetGoal(5, GoalUnit.WORDS), Action.Next, Action.Next)
        assertEquals(Reader.GOAL_REACHED, state.message)
        assertEquals(Overlay.LINE, state.overlay)

        state = state.then(Action.SubmitRecall("ok"), Action.Rate(1))
        assertEquals(listOf(Effect.Checkpoint("goal", "chunk", 1, 2, 7, "ok", 1)), state.effects)
        assertNull(state.overlay)
        assertFalse(state.quit)
    }

    @Test
    fun `after a goal checkpoint the next span starts there`() {
        val state = at(0).then(
            Action.SetGoal(5, GoalUnit.WORDS), Action.Next, Action.Next, Action.SubmitRecall(""), Action.Rate(2),
            Action.GoalAgain, Action.Next, Action.Next, // 13 - 7 = 6
            Action.SubmitRecall(""), Action.Rate(2),
        )
        assertEquals(listOf(Effect.Checkpoint("goal", "chunk", 2, 4, 6, null, 2)), state.effects)
    }

    @Test
    fun `goal reached without recall has no checkpoint`() {
        val state = Reader.initial(miniBook(), W5.copy(recall = false), Position(1, 0))
            .then(Action.SetGoal(5, GoalUnit.WORDS), Action.Next, Action.Next)
        assertEquals(Reader.GOAL_REACHED, state.message)
        assertNull(state.overlay)
    }
}
