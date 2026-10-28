package io.github.myarzik.kert.core

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

class ReadingSession private constructor() {
    val state: ReaderState get() = TODO("task 22")

    fun dispatch(action: Action): ReaderState = TODO("task 22")

    fun close(): Unit = TODO("task 22")

    companion object {
        const val ADVANCE_LOG_CAP = 10_000

        fun open(
            db: SqlConnection,
            defaults: SettingsDefaults,
            fallback: Settings,
            clock: () -> Double,
        ): ReadingSession = TODO("task 22")
    }
}
