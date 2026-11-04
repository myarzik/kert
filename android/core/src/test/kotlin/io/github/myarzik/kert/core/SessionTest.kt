package io.github.myarzik.kert.core

import java.nio.file.Files
import java.nio.file.Path
import java.security.MessageDigest
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertFalse
import org.junit.jupiter.api.BeforeEach
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.io.TempDir

/** Port of the session parts of tests/test_roundtrip.py and test_config.py (§16.4–16.5). */
class SessionTest {
    @TempDir
    lateinit var tmp: Path
    private lateinit var book: Path

    /** App-level defaults (SharedPreferences in the app). */
    private class FakeDefaults(
        override val chunkWidth: Int? = null,
        override val theme: Theme? = null,
    ) : SettingsDefaults {
        val saved = mutableListOf<Pair<String, String>>()

        override fun save(key: String, value: String) {
            saved += key to value
        }
    }

    private val fallback = Settings(chunkWidth = 8, theme = Theme.LIGHT)
    private var now = 1000.0

    @BeforeEach
    fun copyBook() {
        book = Reference.copy("book_ru.kert", tmp)
    }

    private fun open(defaults: SettingsDefaults = FakeDefaults()) =
        ReadingSession.open(JdbcConnection(book), defaults, fallback) { now++ }

    private fun sql(query: String, vararg args: Any?) = JdbcConnection(book).use { it.query(query, *args) }

    private fun state(key: String) =
        sql("SELECT value FROM reader_state WHERE key = ?", key).singleOrNull()?.single()

    private fun setState(key: String, value: String) = JdbcConnection(book).use {
        it.execute("INSERT INTO reader_state (key, value) VALUES (?, ?)", key, value)
    }

    private fun contentDigest(): String {
        val digest = MessageDigest.getInstance("SHA-256")
        for (table in listOf("meta", "blocks", "sentences")) {
            for (row in sql("SELECT * FROM $table ORDER BY 1")) {
                digest.update(row.joinToString("|") { if (it is ByteArray) it.contentToString() else "$it" }.toByteArray())
            }
        }
        return digest.digest().joinToString("") { "%02x".format(it) }
    }

    // --- Opening (§5 step 3, §16.5 precedence) ---------------------------------------

    @Test
    fun `fresh book uses the fallback settings and starts at the first chunk`() {
        val session = open()
        assertEquals(fallback, session.state.settings)
        assertEquals(Position(1, 0), session.state.position)
        session.close()
    }

    @Test
    fun `app defaults override the fallback`() {
        val session = open(FakeDefaults(chunkWidth = 6, theme = Theme.DARK))
        assertEquals(Settings(6, Theme.DARK), session.state.settings)
        session.close()
    }

    @Test
    fun `book state overrides app defaults per key`() {
        setState("chunk_width", "10")
        val session = open(FakeDefaults(chunkWidth = 6, theme = Theme.DARK))
        assertEquals(Settings(10, Theme.DARK), session.state.settings)
        session.close()
    }

    @Test
    fun `invalid book values fall through`() {
        setState("chunk_width", "99")
        setState("theme", "blue")
        val session = open(FakeDefaults(chunkWidth = 6))
        assertEquals(Settings(6, Theme.LIGHT), session.state.settings)
        session.close()
    }

    @Test
    fun `reads a position written by the Python reader`() {
        setState("position", """{"sentence_id": 4, "chunk_start_token": 0}""")
        val session = open()
        assertEquals(Position(4, 0), session.state.position)
        session.close()
    }

    // --- Effects (D5, §8.4) -------------------------------------------------------------

    @Test
    fun `steps write advance_log rows with the clock`() {
        val session = open()
        session.dispatch(Action.Next) // leaves S1 "Глава 1": 2 words
        session.dispatch(Action.Previous) // leaves S2: 7 words at W=8
        session.close()

        assertEquals(
            listOf(listOf(1000.0, 1L, 2L, 1L), listOf(1001.0, 2L, 7L, -1L)),
            sql("SELECT ts, sentence_id, chunk_words, direction FROM advance_log ORDER BY id")
                .map { r -> r.map { (it as Number).let { n -> if (it is Double) n.toDouble() else n.toLong() } } },
        )
    }

    @Test
    fun `advance_log rows carry the kind and the mode`() {
        val session = open()
        session.dispatch(Action.NextBlock) // leaves S1 (block 1)
        session.dispatch(Action.SetMode(Mode.PARAGRAPH))
        session.dispatch(Action.Next) // leaves block 2 = S2 + S3: 11 words
        session.close()

        assertEquals(
            listOf(listOf("block", "chunk", 2L), listOf("step", "paragraph", 11L)),
            sql("SELECT kind, mode, chunk_words FROM advance_log ORDER BY id")
                .map { r -> listOf(r[0], r[1], (r[2] as Number).toLong()) },
        )
    }

    @Test
    fun `mode is saved in the book only and restored`() {
        val defaults = FakeDefaults()
        val session = open(defaults)
        session.dispatch(Action.SetMode(Mode.SENTENCE))
        session.close()

        assertEquals("sentence", state("mode"))
        assertEquals(emptyList<Pair<String, String>>(), defaults.saved)
        val reopened = open()
        assertEquals(Mode.SENTENCE, reopened.state.settings.mode)
        reopened.close()
    }

    @Test
    fun `settings write both the book and the app defaults`() {
        val defaults = FakeDefaults()
        val session = open(defaults)
        session.dispatch(Action.SetWidth(6))
        session.dispatch(Action.SetTheme(Theme.DARK))
        session.close()

        assertEquals("6", state("chunk_width"))
        assertEquals("dark", state("theme"))
        assertEquals(listOf("chunk_width" to "6", "theme" to "dark"), defaults.saved)
    }

    // --- Closing (§5 on exit, §16.4) ------------------------------------------------------

    @Test
    fun `close saves the position in the Python JSON format`() {
        val session = open()
        repeat(3) { session.dispatch(Action.Next) }
        session.close()

        assertEquals("""{"sentence_id": 4, "chunk_start_token": 0}""", state("position"))
    }

    @Test
    fun `close writes library percent and last read`() {
        now = 5000.0
        val session = open()
        repeat(3) { session.dispatch(Action.Next) } // 13 of 31 words before S4; ts 5000-5002
        session.close() // the clock's next tick is the close time

        assertEquals("41.9", state("percent"))
        assertEquals("5003", state("last_read"))
    }

    @Test
    fun `reopening restores position and width`() {
        open().apply { dispatch(Action.SetWidth(6)); repeat(4) { dispatch(Action.Next) }; close() }

        val session = open()
        assertEquals(6, session.state.settings.chunkWidth)
        assertEquals(Position(4, 0), session.state.position)
        session.close()
    }

    @Test
    fun `close caps advance_log at 10 000 rows`() {
        JdbcConnection(book).use { db ->
            db.execute("BEGIN")
            repeat(ReadingSession.ADVANCE_LOG_CAP) {
                db.execute("INSERT INTO advance_log (ts, sentence_id, chunk_words, direction) VALUES (?, 1, 0, 1)", it.toDouble())
            }
            db.execute("COMMIT")
        }
        val session = open()
        session.dispatch(Action.Next)
        session.dispatch(Action.Next)
        session.close()

        val rows = sql("SELECT ts FROM advance_log ORDER BY id").map { (it[0] as Number).toDouble() }
        assertEquals(10_000, rows.size)
        assertEquals(2.0, rows.first()) // the two oldest rows were dropped
    }

    @Test
    fun `content tables are never written and no WAL sidecar remains`() {
        val before = contentDigest()
        open().apply { dispatch(Action.Next); dispatch(Action.SetWidth(5)); close() }

        assertEquals(before, contentDigest())
        assertFalse(Files.exists(tmp.resolve("book_ru.kert-wal")))
    }
}
