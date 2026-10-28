package io.github.myarzik.kert.core

import java.nio.file.Files
import java.nio.file.Path
import kotlin.io.path.listDirectoryEntries
import kotlin.io.path.name
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertNotNull
import org.junit.jupiter.api.Assertions.assertNull
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.BeforeEach
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.assertThrows
import org.junit.jupiter.api.io.TempDir

/** Book import, listing and deletion (§16.4). */
class LibraryTest {
    @TempDir
    lateinit var tmp: Path
    private lateinit var library: Library

    @BeforeEach
    fun setUp() {
        library = Library(Files.createDirectories(tmp.resolve("books"))) { JdbcConnection(it) }
    }

    private fun stream(file: String) = Files.newInputStream(Reference.dir.resolve(file))

    private fun import(file: String) =
        checkNotNull(library.commit(library.stage(stream(file)), replace = true))

    private fun files() = library.dir.listDirectoryEntries().map { it.name }.sorted()

    @Test
    fun `import copies a valid book under its content-derived name`() {
        val entry = import("book_ru.kert")

        assertEquals("book_ru", entry.title)
        assertTrue(entry.file.name.matches(Regex("[0-9a-f]{16}\\.kert")), entry.file.name)
        assertEquals(listOf(entry.file.name), files())
        assertNull(entry.percent)
        assertNull(entry.lastRead)
    }

    @Test
    fun `invalid input is rejected and leaves nothing behind`() {
        assertThrows<KertFormatException> {
            library.stage("not a kert file at all".repeat(50).byteInputStream())
        }
        assertEquals(emptyList<String>(), files())
    }

    @Test
    fun `a book without text is rejected`() {
        val path = Reference.copy("book_ru.kert", tmp)
        JdbcConnection(path).use { it.execute("DELETE FROM sentences") }

        assertThrows<KertFormatException> { library.stage(Files.newInputStream(path)) }
        assertEquals(emptyList<String>(), files())
    }

    @Test
    fun `importing the same book again is reported as a duplicate`() {
        val first = import("book_ru.kert")
        val staged = library.stage(stream("book_ru.kert"))

        assertEquals(first.file, staged.duplicateOf?.file)
    }

    @Test
    fun `keeping the existing copy preserves its reading state`() {
        val first = import("book_ru.kert")
        ReadingSession.open(JdbcConnection(first.file), NoDefaults, Settings(8, Theme.DARK)) { 1.0 }
            .apply { dispatch(Action.Next); close() }

        assertNull(library.commit(library.stage(stream("book_ru.kert")), replace = false))

        assertEquals(listOf(first.file.name), files())
        assertNotNull(library.list().single().percent)
    }

    @Test
    fun `replacing resets the copy`() {
        val first = import("book_ru.kert")
        ReadingSession.open(JdbcConnection(first.file), NoDefaults, Settings(8, Theme.DARK)) { 1.0 }
            .apply { dispatch(Action.Next); close() }

        library.commit(library.stage(stream("book_ru.kert")), replace = true)

        assertNull(library.list().single().percent)
        assertEquals(listOf(first.file.name), files())
    }

    @Test
    fun `list shows titles, percent and last read, most recent first`() {
        val ru = import("book_ru.kert")
        val en = import("book_en.kert")
        ReadingSession.open(JdbcConnection(en.file), NoDefaults, Settings(8, Theme.DARK)) { 100.0 }
            .apply { dispatch(Action.Last); close() }
        ReadingSession.open(JdbcConnection(ru.file), NoDefaults, Settings(8, Theme.DARK)) { 200.0 }
            .close()

        val entries = library.list()
        assertEquals(listOf("book_ru", "book_en"), entries.map { it.title })
        assertEquals(listOf(200L, 100L), entries.map { it.lastRead })
        assertEquals(0.0, entries[0].percent)
    }

    @Test
    fun `unread books follow read ones, by title`() {
        import("non_bmp.kert")
        import("book_ru.kert")

        assertEquals(listOf("Non-BMP", "book_ru"), library.list().map { it.title })
    }

    @Test
    fun `delete removes the book and its sidecars`() {
        val entry = import("book_ru.kert")
        Files.writeString(library.dir.resolve(entry.file.name + "-wal"), "x")

        library.delete(entry)

        assertEquals(emptyList<String>(), files())
    }
}
