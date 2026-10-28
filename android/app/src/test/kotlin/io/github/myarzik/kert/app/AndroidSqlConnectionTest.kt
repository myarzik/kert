package io.github.myarzik.kert.app

import androidx.test.ext.junit.runners.AndroidJUnit4
import io.github.myarzik.kert.core.Action
import io.github.myarzik.kert.core.KertReader
import io.github.myarzik.kert.core.NoDefaults
import io.github.myarzik.kert.core.Position
import io.github.myarzik.kert.core.ReadingSession
import io.github.myarzik.kert.core.Settings
import io.github.myarzik.kert.core.Theme
import java.io.File
import java.nio.file.Files
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Test
import org.junit.runner.RunWith

/** Android's SQLite behind the core SqlConnection seam (§16.3–16.4). */
@RunWith(AndroidJUnit4::class)
class AndroidSqlConnectionTest {
    private val dir: File = Files.createTempDirectory("kert").toFile()

    @Test
    fun readsBlobsAndTextThroughAndroidSqlite() {
        val book = AndroidSqlConnection.open(Fixtures.copy("book_ru.kert", dir)).use { KertReader.read(it) }

        assertEquals(6, book.sentences.size)
        assertEquals("— Привет, — сказал он и улыбнулся.", book.sentences[3].text)
        assertEquals(9, book.sentences[3].tokens.size)
    }

    @Test
    fun sessionWritesStateAndLeavesASingleFile() {
        val file = Fixtures.copy("book_ru.kert", dir)
        ReadingSession.open(AndroidSqlConnection.open(file), NoDefaults, Settings(8, Theme.DARK)) { 1.0 }
            .apply { dispatch(Action.Next); dispatch(Action.Next); close() }

        val session = ReadingSession.open(AndroidSqlConnection.open(file), NoDefaults, Settings(8, Theme.DARK)) { 2.0 }
        assertEquals(Position(3, 0), session.state.position)
        session.close()
        assertFalse(File(dir, "book_ru.kert-wal").exists())
    }
}
