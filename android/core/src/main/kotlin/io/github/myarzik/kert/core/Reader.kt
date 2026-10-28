package io.github.myarzik.kert.core

data class Position(val sentenceId: Long, val chunkStartToken: Int)

enum class Theme(val storage: String) { DARK("dark"), LIGHT("light") }

data class Settings(val chunkWidth: Int, val theme: Theme)

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
}

sealed interface Effect {
    data class Advance(val sentenceId: Long, val chunkWords: Int, val direction: Int) : Effect
    data class SaveSetting(val key: String, val value: String) : Effect
}

class Chunks(
    val spans: List<ChunkSpan>,
    val words: List<Int>,
    val wordsBefore: List<Int>,
    val blockIds: List<Long>,
) {
    companion object {
        fun build(book: BookContent, width: Int): Chunks = TODO("task 21")
    }
}

data class ReaderState(
    val book: BookContent,
    val settings: Settings,
    val chunks: Chunks,
    val index: Int,
    val effects: List<Effect> = emptyList(),
) {
    val position: Position get() = TODO("task 21")
    val percent: Double get() = TODO("task 21")
}

object Reader {
    fun initial(book: BookContent, settings: Settings, position: Position): ReaderState = TODO("task 21")

    fun reduce(state: ReaderState, action: Action): ReaderState = TODO("task 21")
}
