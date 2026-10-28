package io.github.myarzik.kert.core

import java.nio.file.Files
import java.nio.file.Path
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.assertThrows
import org.junit.jupiter.api.io.TempDir

class KertReaderTest {
    @TempDir
    lateinit var tmp: Path

    private fun read(file: String): BookContent =
        JdbcConnection(Reference.copy(file, tmp)).use { KertReader.read(it) }

    private fun tokenTexts(sentence: Sentence) =
        sentence.tokens.map { sentence.text.substring(it.start, it.end) }

    // --- Full scan (§5 steps 1-2), goldens from tests/test_store.py ------------------

    @Test
    fun `reads meta blocks and sentences of the RU fixture`() {
        val book = read("book_ru.kert")

        assertEquals("1", book.meta["schema_version"])
        assertEquals(31, book.wordCount)
        assertEquals(
            listOf("paragraph", "paragraph", "dialogue", "paragraph"),
            book.blocks.map { it.type },
        )
        assertEquals(
            listOf(
                "Глава 1",
                "Он вышел из дома, хотя шёл дождь.",
                "На улице было пусто.",
                "— Привет, — сказал он и улыбнулся.",
                "Мы долго гуляли по парку и разговаривали о книгах.",
                "Вечером мы вернулись домой.",
            ),
            book.sentences.map { it.text },
        )
        assertEquals(listOf(1L, 2L, 2L, 3L, 4L, 4L), book.sentences.map { it.blockId })
    }

    @Test
    fun `decodes token and candidate blobs`() {
        val dialogue = read("book_ru.kert").sentences[3]

        assertEquals(
            listOf("—", "Привет", ",", "—", "сказал", "он", "и", "улыбнулся", "."),
            tokenTexts(dialogue),
        )
        assertEquals(
            listOf(SplitCandidate(4, 1.0), SplitCandidate(6, 0.8)),
            dialogue.candidates,
        )
    }

    @Test
    fun `reads typed blocks and chapters from Markdown`() {
        val book = read("book_en.kert")

        assertEquals("heading", book.blocks.first().type)
        assertEquals(1L, book.blocks.first().chapter)
        assertTrue(book.blocks.any { it.type == "code" })
        assertTrue(book.blocks.any { it.type == "list_item" })
    }

    // --- Code point offsets → UTF-16 (§16.3) ---------------------------------------

    @Test
    fun `token offsets survive characters outside the BMP`() {
        val book = read("non_bmp.kert")
        val all = book.sentences.flatMap(::tokenTexts)

        assertTrue("🙂" in all, "emoji token missing: $all")
        assertTrue("𝔸" in all, "math letter token missing: $all")
        assertTrue(all.none { it.isBlank() || it != it.trim() }, "misaligned tokens: $all")
    }

    @Test
    fun `code point spans convert to UTF-16 indices`() {
        val text = "a🙂b 𝔸c"
        // code points: a 🙂 b ␠ 𝔸 c  -> spans [0,3) and [4,6)
        val spans = Offsets.toUtf16(text, listOf(0 to 3, 4 to 6))

        assertEquals(listOf("a🙂b", "𝔸c"), spans.map { text.substring(it.start, it.end) })
    }

    @Test
    fun `BMP-only text keeps its offsets`() {
        assertEquals(
            listOf(TokenSpan(0, 5), TokenSpan(6, 9)),
            Offsets.toUtf16("Глава 1.Х", listOf(0 to 5, 6 to 9)),
        )
    }

    // --- Words: the shared predicate and the Python reference (§14.3, §16.3) ---------

    @Test
    fun `total words match the Python reference for every fixture`() {
        for (reference in Reference.books) {
            val book = read(reference.file)
            val words = book.sentences.sumOf { s -> tokenTexts(s).count(Words::isWord) }
            val pythonWords = reference.widths.getValue("8").sumOf { it[3] }

            assertEquals(pythonWords, words, reference.file)
        }
    }

    // --- Rejection (§5 step 1) --------------------------------------------------------

    @Test
    fun `rejects an unsupported schema version`() {
        val path = Reference.copy("book_ru.kert", tmp)
        JdbcConnection(path).use {
            it.execute("UPDATE meta SET value = '2' WHERE key = 'schema_version'")
        }

        val error = assertThrows<KertFormatException> {
            JdbcConnection(path).use { KertReader.read(it) }
        }
        assertTrue("schema version 2" in error.message.orEmpty(), error.message)
    }

    @Test
    fun `rejects a file that is not a kert book`() {
        val path = tmp.resolve("bad.kert")
        Files.writeString(path, "this is not a database at all".repeat(100))

        assertThrows<KertFormatException> { JdbcConnection(path).use { KertReader.read(it) } }
    }

    @Test
    fun `rejects undecodable blobs`() {
        val path = Reference.copy("book_ru.kert", tmp)
        JdbcConnection(path).use {
            it.execute("UPDATE sentences SET tokens = ? WHERE id = 2", byteArrayOf(0xc1.toByte()))
        }

        assertThrows<KertFormatException> { JdbcConnection(path).use { KertReader.read(it) } }
    }

    @Test
    fun `rejects a missing or non-numeric word count`() {
        val path = Reference.copy("book_ru.kert", tmp)
        JdbcConnection(path).use {
            it.execute("UPDATE meta SET value = 'many' WHERE key = 'word_count'")
        }

        assertThrows<KertFormatException> { JdbcConnection(path).use { KertReader.read(it) } }
    }
}
