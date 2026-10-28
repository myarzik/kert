package io.github.myarzik.kert.core

import io.github.myarzik.kert.core.ReaderTest.Companion.W5
import io.github.myarzik.kert.core.ReaderTest.Companion.miniBook
import java.nio.file.Path
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.io.TempDir

/** Block texts and the active chunk's character range for the Android tape (§16.5). */
class BookLayoutTest {
    private val layout = BookLayout(miniBook())

    private fun at(position: Position) = Reader.initial(miniBook(), W5, position)

    private fun activeText(state: ReaderState): String {
        val (block, range) = layout.active(state)
        return layout.blocks[block].text.substring(range.first, range.last + 1)
    }

    @Test
    fun `blocks join their sentences with a space, like the terminal`() {
        assertEquals(
            listOf(
                "Глава один.",
                "alpha bravo charlie delta echo foxtrot golf hotel india. Short one.",
                "one two three four five six seven eight nine.",
            ),
            layout.blocks.map { it.text },
        )
        assertEquals(listOf(1L, 2L, 3L), layout.blocks.map { it.id })
    }

    @Test
    fun `active chunk range inside its block`() {
        assertEquals("alpha bravo charlie delta echo", activeText(at(Position(2, 0))))
        assertEquals("foxtrot golf hotel india.", activeText(at(Position(2, 5))))
        assertEquals("Short one.", activeText(at(Position(3, 0))))
        assertEquals(1, layout.active(at(Position(3, 0))).first)
    }

    @Test
    fun `block index of every chunk`() {
        val state = at(Position(1, 0))
        assertEquals(listOf(0, 1, 1, 1, 2, 2), state.chunks.spans.indices.map { layout.blockIndex(state, it) })
    }

    @TempDir
    lateinit var tmp: Path

    @Test
    fun `ranges stay aligned with characters outside the BMP`() {
        val book = JdbcConnection(Reference.copy("non_bmp.kert", tmp)).use { KertReader.read(it) }
        val layout = BookLayout(book)
        var state = Reader.initial(book, W5, Position(book.sentences.first().id, 0))
        val seen = mutableListOf<String>()
        while (true) {
            val (block, range) = layout.active(state)
            seen += layout.blocks[block].text.substring(range.first, range.last + 1)
            val next = Reader.reduce(state, Action.Next)
            if (next.index == state.index) break
            state = next
        }

        assertEquals(state.chunks.spans.size, seen.size)
        assertEquals(seen.map { it.trim() }, seen) // no chunk starts or ends mid-whitespace
        assertEquals(true, seen.any { "🙂" in it } && seen.any { "𝔸" in it })
    }

    // --- Centering (§7.1 applied to pixels) -----------------------------------------------

    @Test
    fun `scroll delta brings the chunk's lines to the viewport center`() {
        // Item top at 100 px; chunk lines span 40..100 inside it -> center at 170;
        // viewport 1000 px -> center 500 -> scroll by 170 - 500 = -330.
        assertEquals(-330f, Centering.scrollDelta(itemTop = 100, chunkTop = 40f, chunkBottom = 100f, viewport = 1000))
        assertEquals(0f, Centering.scrollDelta(itemTop = 470, chunkTop = 0f, chunkBottom = 60f, viewport = 1000))
    }
}
