package io.github.myarzik.kert.core

import java.io.InputStream
import java.nio.file.Path

data class LibraryEntry(
    val file: Path,
    val title: String,
    val compiledAt: String,
    val percent: Double?,
    val lastRead: Long?,
)

/** A validated import waiting to be committed into the library. */
class StagedBook(val temp: Path, val target: Path, val title: String, val duplicateOf: LibraryEntry?)

class Library(val dir: Path, private val connect: (Path) -> SqlConnection) {
    fun stage(input: InputStream): StagedBook = TODO("task 22")

    fun commit(staged: StagedBook, replace: Boolean): LibraryEntry? = TODO("task 22")

    fun list(): List<LibraryEntry> = TODO("task 22")

    fun delete(entry: LibraryEntry): Unit = TODO("task 22")
}
