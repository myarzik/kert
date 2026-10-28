package io.github.myarzik.kert.core

/** A thin SQL seam: JDBC in tests, Android's SQLite in the app (§16.3). */
interface SqlConnection : AutoCloseable {
    fun query(sql: String, vararg args: Any?): List<List<Any?>>

    fun execute(sql: String, vararg args: Any?)
}

class KertFormatException(message: String, cause: Throwable? = null) : Exception(message, cause)

data class Block(val id: Long, val type: String, val chapter: Long?)

data class SplitCandidate(val tokenIndex: Int, val weight: Double)

/** Half-open UTF-16 index range into [Sentence.text]. */
data class TokenSpan(val start: Int, val end: Int)

data class Sentence(
    val id: Long,
    val blockId: Long,
    val seq: Int,
    val text: String,
    val tokens: List<TokenSpan>,
    val candidates: List<SplitCandidate>,
)

data class BookContent(
    val meta: Map<String, String>,
    val blocks: List<Block>,
    val sentences: List<Sentence>,
    val wordCount: Int,
)
