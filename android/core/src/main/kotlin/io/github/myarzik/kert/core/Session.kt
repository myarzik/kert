package io.github.myarzik.kert.core

import java.util.Locale

/** App-level setting defaults (SharedPreferences in the app, §16.5). */
interface SettingsDefaults {
    val chunkWidth: Int?
    val theme: Theme?

    fun save(key: String, value: String)
}

object NoDefaults : SettingsDefaults {
    override val chunkWidth: Int? = null
    override val theme: Theme? = null

    override fun save(key: String, value: String) = Unit
}

/**
 * One open book: Python's open_session / feed / close_session (§5, §16.4).
 * Content tables are only read; reader_state and advance_log are written (D8).
 */
class ReadingSession private constructor(
    private val db: SqlConnection,
    private val defaults: SettingsDefaults,
    private val clock: () -> Double,
    initial: ReaderState,
) {
    var state: ReaderState = initial
        private set

    /** Apply one action and execute the effects it produced. */
    fun dispatch(action: Action): ReaderState {
        state = Reader.reduce(state, action)
        for (effect in state.effects) {
            when (effect) {
                is Effect.Advance -> db.execute(
                    "INSERT INTO advance_log (ts, sentence_id, chunk_words, direction, kind, mode) " +
                        "VALUES (?, ?, ?, ?, ?, ?)",
                    clock(), effect.sentenceId, effect.chunkWords, effect.direction,
                    effect.kind, state.settings.mode.storage,
                )
                is Effect.SaveSetting -> {
                    saveState(db, effect.key, effect.value)
                    // §17.2: the mode is an experimental condition, kept per book only.
                    if (effect.key != "mode") defaults.save(effect.key, effect.value)
                }
            }
        }
        return state
    }

    /** Save position and library keys, cap advance_log, checkpoint, close. */
    fun close() {
        try {
            val position = state.position
            saveState(
                db, "position",
                """{"sentence_id": ${position.sentenceId}, "chunk_start_token": ${position.chunkStartToken}}""",
            )
            saveState(db, "percent", String.format(Locale.ROOT, "%.1f", state.percent))
            saveState(db, "last_read", clock().toLong().toString())
            db.execute(
                "DELETE FROM advance_log WHERE id NOT IN " +
                    "(SELECT id FROM advance_log ORDER BY id DESC LIMIT ?)",
                ADVANCE_LOG_CAP,
            )
            // Fold the WAL back so the .kert stays a single portable file.
            db.query("PRAGMA wal_checkpoint(TRUNCATE)")
        } finally {
            db.close()
        }
    }

    companion object {
        const val ADVANCE_LOG_CAP = 10_000
        private val POSITION = Regex(
            """"sentence_id"\s*:\s*(\d+).*"chunk_start_token"\s*:\s*(\d+)""",
            RegexOption.DOT_MATCHES_ALL,
        )

        fun open(
            db: SqlConnection,
            defaults: SettingsDefaults,
            fallback: Settings,
            clock: () -> Double,
        ): ReadingSession =
            try {
                val book = KertReader.read(db)
                val settings = resolve(db, defaults, fallback)
                val position = loadState(db, "position")?.let { raw ->
                    POSITION.find(raw)?.destructured?.let { (sid, token) -> Position(sid.toLong(), token.toInt()) }
                } ?: Position(book.sentences.firstOrNull()?.id ?: 0, 0)
                ReadingSession(db, defaults, clock, Reader.initial(book, settings, position))
            } catch (e: Exception) {
                db.close()
                throw e
            }

        /** Per key: book reader_state > app defaults > fallback; invalid values fall through. */
        private fun resolve(db: SqlConnection, defaults: SettingsDefaults, fallback: Settings): Settings {
            val widths = Reader.WIDTH_MIN..Reader.WIDTH_MAX
            val width = loadState(db, "chunk_width")?.toIntOrNull()?.takeIf { it in widths }
                ?: defaults.chunkWidth?.takeIf { it in widths }
                ?: fallback.chunkWidth
            val theme = loadState(db, "theme")?.let { v -> Theme.entries.find { it.storage == v } }
                ?: defaults.theme
                ?: fallback.theme
            val mode = loadState(db, "mode")?.let { v -> Mode.entries.find { it.storage == v } } ?: Mode.CHUNK
            return Settings(width, theme, mode)
        }

        internal fun loadState(db: SqlConnection, key: String): String? =
            db.query("SELECT value FROM reader_state WHERE key = ?", key).firstOrNull()?.get(0) as String?

        // INSERT OR REPLACE, not UPSERT: Android 8's SQLite predates ON CONFLICT DO UPDATE.
        private fun saveState(db: SqlConnection, key: String, value: String) =
            db.execute("INSERT OR REPLACE INTO reader_state (key, value) VALUES (?, ?)", key, value)
    }
}
