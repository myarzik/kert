package io.github.myarzik.kert.core

import java.io.InputStream
import java.nio.file.Files
import java.nio.file.Path
import java.nio.file.StandardCopyOption
import java.security.MessageDigest
import kotlin.io.path.deleteIfExists
import kotlin.io.path.exists
import kotlin.io.path.listDirectoryEntries
import kotlin.io.path.name

data class LibraryEntry(
    val file: Path,
    val title: String,
    val compiledAt: String,
    val percent: Double?,
    val lastRead: Long?,
)

/** A validated import waiting to be committed into the library. */
class StagedBook(val temp: Path, val target: Path, val title: String, val duplicateOf: LibraryEntry?)

/**
 * Imported books, each a private copy of a `.kert` file (§16.4): SQLite needs
 * a real path, and the reading state lives in that copy (D8).
 */
class Library(val dir: Path, private val connect: (Path) -> SqlConnection) {
    /** Copy [input] next to the library and validate it with a full read. */
    fun stage(input: InputStream): StagedBook {
        val temp = Files.createTempFile(dir, INCOMING, ".kert")
        try {
            input.use { Files.copy(it, temp, StandardCopyOption.REPLACE_EXISTING) }
            val book = connect(temp).use { KertReader.read(it) }
            if (book.sentences.isEmpty()) throw KertFormatException("This book has no text to read.")
            val title = book.meta["title"].orEmpty()
            val target = dir.resolve(fileName(title, book.meta["compiled_at"].orEmpty()))
            return StagedBook(temp, target, title, if (target.exists()) entry(target) else null)
        } catch (e: Exception) {
            removeWithSidecars(temp)
            throw e
        }
    }

    /** Move the staged copy into place; null when a kept duplicate wins. */
    fun commit(staged: StagedBook, replace: Boolean): LibraryEntry? {
        if (staged.duplicateOf != null && !replace) {
            removeWithSidecars(staged.temp)
            return null
        }
        removeWithSidecars(staged.target)
        sidecars(staged.temp).forEach { it.deleteIfExists() }
        Files.move(staged.temp, staged.target, StandardCopyOption.REPLACE_EXISTING)
        return entry(staged.target)
    }

    /** Books read most recently first, then unread books by title. */
    fun list(): List<LibraryEntry> =
        dir.listDirectoryEntries("*.kert")
            .filterNot { it.name.startsWith(INCOMING) }
            .map(::entry)
            .sortedWith(compareByDescending<LibraryEntry> { it.lastRead ?: Long.MIN_VALUE }.thenBy { it.title })

    fun delete(entry: LibraryEntry) = removeWithSidecars(entry.file)

    private fun entry(file: Path): LibraryEntry = connect(file).use { db ->
        val meta = db.query("SELECT key, value FROM meta WHERE key IN ('title', 'compiled_at')")
            .associate { (k, v) -> k as String to v as String }
        LibraryEntry(
            file = file,
            title = meta["title"].orEmpty(),
            compiledAt = meta["compiled_at"].orEmpty(),
            percent = ReadingSession.loadState(db, "percent")?.toDoubleOrNull(),
            lastRead = ReadingSession.loadState(db, "last_read")?.toLongOrNull(),
        )
    }

    private fun sidecars(file: Path) =
        listOf("-wal", "-shm", "-journal").map { file.resolveSibling(file.name + it) }

    private fun removeWithSidecars(file: Path) {
        file.deleteIfExists()
        sidecars(file).forEach { it.deleteIfExists() }
    }

    companion object {
        private const val INCOMING = ".incoming-"

        /** First 16 hex digits of SHA-256(title + "\n" + compiled_at) + ".kert". */
        fun fileName(title: String, compiledAt: String): String {
            val digest = MessageDigest.getInstance("SHA-256").digest("$title\n$compiledAt".toByteArray())
            return digest.joinToString("") { "%02x".format(it) }.take(16) + ".kert"
        }
    }
}
