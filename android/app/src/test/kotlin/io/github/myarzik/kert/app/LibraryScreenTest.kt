package io.github.myarzik.kert.app

import android.content.Intent
import android.net.Uri
import androidx.compose.ui.test.hasText
import androidx.compose.ui.test.junit4.v2.createEmptyComposeRule
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.test.core.app.ActivityScenario
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import java.io.File
import java.nio.file.Files
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

/** Import by opening a file from another app, the library list, duplicates (§16.4). */
@RunWith(AndroidJUnit4::class)
class LibraryScreenTest {
    @get:Rule
    val compose = createEmptyComposeRule()

    private val outside: File = Files.createTempDirectory("downloads").toFile()

    private fun viewIntent(file: File) =
        Intent(ApplicationProvider.getApplicationContext(), MainActivity::class.java)
            .setAction(Intent.ACTION_VIEW)
            .setData(Uri.fromFile(file))

    private fun waitForText(text: String) =
        compose.waitUntil(timeoutMillis = 10_000) { compose.onAllNodes(hasText(text, substring = true)).fetchSemanticsNodes().isNotEmpty() }

    @Test
    fun emptyLibraryInvitesToImport() {
        ActivityScenario.launch(MainActivity::class.java).use {
            waitForText("No books yet")
        }
    }

    @Test
    fun openingAKertFileImportsItIntoTheLibrary() {
        ActivityScenario.launch<MainActivity>(viewIntent(Fixtures.copy("book_ru.kert", outside))).use {
            waitForText("book_ru")
            compose.onNodeWithText("Not started", substring = true).assertExists()
        }
    }

    @Test
    fun anInvalidFileShowsWhatIsWrong() {
        val junk = File(outside, "junk.kert").apply { writeText("not a book ".repeat(100)) }
        ActivityScenario.launch<MainActivity>(viewIntent(junk)).use {
            waitForText("Not a valid .kert file")
        }
    }

    @Test
    fun importingTheSameBookAgainAsksBeforeReplacing() {
        val book = Fixtures.copy("book_ru.kert", outside)
        ActivityScenario.launch<MainActivity>(viewIntent(book)).use { waitForText("book_ru") }
        ActivityScenario.launch<MainActivity>(viewIntent(book)).use {
            waitForText("already in your library")
            compose.onNodeWithText("Keep").performClick()
            waitForText("book_ru")
        }
    }
}
