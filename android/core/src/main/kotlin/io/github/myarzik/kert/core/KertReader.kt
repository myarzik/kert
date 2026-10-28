package io.github.myarzik.kert.core

import org.msgpack.core.MessagePack

/** Full scan of a `.kert` file into memory (spec §5 steps 1–2, §16.3). */
object KertReader {
    fun read(db: SqlConnection): BookContent =
        try {
            scan(db)
        } catch (e: KertFormatException) {
            throw e
        } catch (e: Exception) {
            // Not SQLite, foreign tables, or undecodable msgpack blobs.
            throw KertFormatException("Not a valid .kert file (${e.message}).", e)
        }

    private fun scan(db: SqlConnection): BookContent {
        val meta = db.query("SELECT key, value FROM meta").associate { (k, v) ->
            k as String to v as String
        }
        val version = meta["schema_version"]
        if (version != KertFormat.SCHEMA_VERSION) {
            throw KertFormatException(
                "This book has schema version $version; this kert reads version " +
                    "${KertFormat.SCHEMA_VERSION}. Recompile the book.",
            )
        }
        val wordCount = meta["word_count"]?.toIntOrNull()
            ?: throw KertFormatException("Not a valid .kert file (bad meta word_count).")
        val blocks = db.query("SELECT id, type, chapter FROM blocks ORDER BY id").map { row ->
            Block(id = row[0].long(), type = row[1] as String, chapter = row[2]?.long())
        }
        val sentences = db.query(
            "SELECT id, block_id, seq, text, tokens, candidates FROM sentences ORDER BY id",
        ).map { row ->
            val text = row[3] as String
            Sentence(
                id = row[0].long(),
                blockId = row[1].long(),
                seq = row[2].long().toInt(),
                text = text,
                tokens = Offsets.toUtf16(text, decodePairs(row[4] as ByteArray)),
                candidates = decodeCandidates(row[5] as ByteArray),
            )
        }
        return BookContent(meta, blocks, sentences, wordCount)
    }

    private fun Any?.long(): Long = (this as Number).toLong()

    /** msgpack `[[start, end], ...]` (code point offsets). */
    private fun decodePairs(blob: ByteArray): List<Pair<Int, Int>> =
        MessagePack.newDefaultUnpacker(blob).use { unpacker ->
            List(unpacker.unpackArrayHeader()) {
                check(unpacker.unpackArrayHeader() == 2) { "token span is not a pair" }
                unpacker.unpackInt() to unpacker.unpackInt()
            }
        }

    /** msgpack `[[token_index, weight], ...]`. */
    private fun decodeCandidates(blob: ByteArray): List<SplitCandidate> =
        MessagePack.newDefaultUnpacker(blob).use { unpacker ->
            List(unpacker.unpackArrayHeader()) {
                check(unpacker.unpackArrayHeader() == 2) { "candidate is not a pair" }
                SplitCandidate(unpacker.unpackInt(), unpacker.unpackDouble())
            }
        }
}

/** `.kert` offsets count Unicode code points; Kotlin strings index UTF-16 units. */
object Offsets {
    fun toUtf16(text: String, codePointSpans: List<Pair<Int, Int>>): List<TokenSpan> {
        if (text.codePointCount(0, text.length) == text.length) {
            return codePointSpans.map { (start, end) -> TokenSpan(start, end) }
        }
        return codePointSpans.map { (start, end) ->
            val from = text.offsetByCodePoints(0, start)
            TokenSpan(from, text.offsetByCodePoints(from, end - start))
        }
    }
}

/** The spaCy-free word predicate shared with Python's common/text.py (§14.3). */
object Words {
    // \p{Nd}: any Unicode decimal digit, like Python's \d on str.
    private val number = Regex("""\p{Nd}+(?:[.,]\p{Nd}+)*""")

    fun isWord(text: String): Boolean =
        text.isNotEmpty() && (text.codePoints().allMatch(Character::isLetter) || number.matches(text))
}
