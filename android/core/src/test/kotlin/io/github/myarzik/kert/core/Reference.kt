package io.github.myarzik.kert.core

import java.nio.file.Files
import java.nio.file.Path
import java.nio.file.Paths
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json

/** The Python reference exported by scripts/export_android_reference.py (§16.6). */
object Reference {
    val dir: Path by lazy {
        val path = Paths.get(System.getProperty("kert.reference") ?: "")
        check(Files.isRegularFile(path.resolve("reference.json"))) {
            "Python reference missing at $path; run: " +
                "uv run python scripts/export_android_reference.py build/android-reference"
        }
        path
    }

    val books: List<ReferenceBook> by lazy {
        Json.decodeFromString<ReferenceFile>(Files.readString(dir.resolve("reference.json"))).books
    }

    fun book(file: String): ReferenceBook = books.single { it.file == file }

    /** A private copy of a reference .kert, safe to open read-write. */
    fun copy(file: String, into: Path): Path =
        Files.copy(dir.resolve(file), into.resolve(file))
}

@Serializable
data class ReferenceFile(val books: List<ReferenceBook>)

/** Chunks per width as [sentenceId, startToken, endToken, words, wordsBefore]. */
@Serializable
data class ReferenceBook(
    val file: String,
    val word_count: Int,
    val widths: Map<String, List<List<Int>>>,
    /** §17.12: units per mode as [first sid, start token, last sid, end token, words, before]. */
    val modes: Map<String, List<List<Int>>>,
)
