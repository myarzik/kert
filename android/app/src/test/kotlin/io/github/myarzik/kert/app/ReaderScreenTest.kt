package io.github.myarzik.kert.app

import android.content.Intent
import android.net.Uri
import android.view.KeyEvent
import androidx.compose.ui.semantics.SemanticsProperties
import androidx.compose.ui.test.SemanticsMatcher
import androidx.compose.ui.test.assertIsSelected
import androidx.compose.ui.test.assertTextEquals
import androidx.compose.ui.test.click
import androidx.compose.ui.test.hasStateDescription
import androidx.compose.ui.test.hasText
import androidx.compose.ui.test.junit4.v2.createEmptyComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performTouchInput
import androidx.compose.ui.test.swipeUp
import androidx.test.core.app.ActivityScenario
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import java.io.File
import java.nio.file.Files
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

/** The reading screen: tape, input mapping, settings panel, lifecycle (§16.5). */
@RunWith(AndroidJUnit4::class)
class ReaderScreenTest {
    @get:Rule
    val compose = createEmptyComposeRule()

    private val outside: File = Files.createTempDirectory("downloads").toFile()

    private fun openBook(block: (ActivityScenario<MainActivity>) -> Unit) {
        val intent = Intent(ApplicationProvider.getApplicationContext(), MainActivity::class.java)
            .setAction(Intent.ACTION_VIEW)
            .setData(Uri.fromFile(Fixtures.copy("book_ru.kert", outside)))
        ActivityScenario.launch<MainActivity>(intent).use { scenario ->
            waitFor(hasText("book_ru"))
            compose.onNodeWithText("book_ru").performClick()
            waitForActive("Глава 1")
            block(scenario)
        }
    }

    private fun waitFor(matcher: SemanticsMatcher) =
        compose.waitUntil(timeoutMillis = 10_000) { compose.onAllNodes(matcher).fetchSemanticsNodes().isNotEmpty() }

    private fun waitForActive(text: String) = waitFor(hasStateDescription(text))

    private fun reader() = compose.onNodeWithTag("reader")

    private fun status() = compose.onNodeWithTag("status")

    private fun ActivityScenario<MainActivity>.key(code: Int) = onActivity {
        it.dispatchKeyEvent(KeyEvent(KeyEvent.ACTION_DOWN, code))
        it.dispatchKeyEvent(KeyEvent(KeyEvent.ACTION_UP, code))
    }

    @Test
    fun opensAtTheFirstChunkWithZeroPercent() = openBook {
        status().assertTextEquals("0.0%")
    }

    @Test
    fun tapOnTheRightAdvancesAndOnTheLeftGoesBack() = openBook {
        // Default width 8: every fixture sentence is one chunk (§6, n <= W+2).
        reader().performTouchInput { click(percentOffset(0.8f, 0.5f)) }
        waitForActive("Он вышел из дома, хотя шёл дождь.")
        status().assertTextEquals("6.5%") // 2 of 31 words before

        reader().performTouchInput { click(percentOffset(0.1f, 0.5f)) }
        waitForActive("Глава 1")
    }

    @Test
    fun volumeKeysStepChunks() = openBook { scenario ->
        scenario.key(KeyEvent.KEYCODE_VOLUME_DOWN)
        waitForActive("Он вышел из дома, хотя шёл дождь.")
        scenario.key(KeyEvent.KEYCODE_VOLUME_UP)
        waitForActive("Глава 1")
    }

    @Test
    fun swipeUpGoesToTheNextBlock() = openBook { scenario ->
        scenario.key(KeyEvent.KEYCODE_VOLUME_DOWN) // into block 2 ("Он вышел…")
        waitForActive("Он вышел из дома, хотя шёл дождь.")
        reader().performTouchInput { swipeUp() }
        waitForActive("— Привет, — сказал он и улыбнулся.") // block 3
    }

    @Test
    fun backSavesProgressAndReopeningResumes() = openBook { scenario ->
        scenario.key(KeyEvent.KEYCODE_VOLUME_DOWN)
        scenario.key(KeyEvent.KEYCODE_VOLUME_DOWN)
        waitForActive("На улице было пусто.")
        scenario.onActivity { it.onBackPressedDispatcher.onBackPressed() }
        waitFor(hasText("19.4%", substring = true)) // 6 of 31 words before

        compose.onNodeWithText("book_ru").performClick()
        waitForActive("На улице было пусто.")
    }

    @Test
    fun settingsPanelChangesWidthAndTheme() = openBook {
        reader().performTouchInput { click(percentOffset(0.5f, 0.02f)) }
        waitFor(hasText("Width 8"))
        compose.onNodeWithText("+").performClick()
        waitFor(hasText("Width 9"))
        compose.onNodeWithText("Light").performClick()
        compose.onNodeWithText("Light").assertIsSelected()
    }

    @Test
    fun theScreenStaysOnWhileReading() = openBook { scenario ->
        scenario.onActivity { assertTrue(it.window.decorView.keepScreenOn || it.findViewById<android.view.View>(android.R.id.content).keepScreenOn) }
    }

    @Suppress("unused")
    private val stateDescription = SemanticsProperties.StateDescription
}
