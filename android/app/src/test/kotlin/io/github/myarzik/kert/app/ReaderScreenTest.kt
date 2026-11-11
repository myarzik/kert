package io.github.myarzik.kert.app

import android.content.Intent
import android.database.sqlite.SQLiteDatabase
import android.net.Uri
import android.view.KeyEvent
import androidx.compose.ui.semantics.SemanticsProperties
import androidx.compose.ui.test.SemanticsMatcher
import androidx.compose.ui.test.assertIsOff
import androidx.compose.ui.test.assertIsOn
import androidx.compose.ui.test.assertIsSelected
import androidx.compose.ui.test.assertTextEquals
import androidx.compose.ui.test.click
import androidx.compose.ui.test.hasStateDescription
import androidx.compose.ui.test.hasTestTag
import androidx.compose.ui.test.hasText
import androidx.compose.ui.test.junit4.v2.createEmptyComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performTouchInput
import androidx.compose.ui.test.swipeLeft
import androidx.compose.ui.test.swipeRight
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

    private fun openBook(
        first: String = "Глава 1",
        prepare: (File) -> Unit = {},
        block: (ActivityScenario<MainActivity>) -> Unit,
    ) {
        val file = Fixtures.copy("book_ru.kert", outside).also(prepare)
        val intent = Intent(ApplicationProvider.getApplicationContext(), MainActivity::class.java)
            .setAction(Intent.ACTION_VIEW)
            .setData(Uri.fromFile(file))
        ActivityScenario.launch<MainActivity>(intent).use { scenario ->
            waitFor(hasText("book_ru"))
            compose.onNodeWithText("book_ru").performClick()
            waitForActive(first)
            block(scenario)
        }
    }

    private fun openPanel() {
        reader().performTouchInput { click(percentOffset(0.5f, 0.02f)) }
        waitFor(hasText("Width 8"))
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
        waitFor(hasText("29.0%", substring = true)) // 9 of 31 words before (2 + 7)
        waitFor(hasText("book_ru")) // the row being clicked, after the list settles

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
    fun horizontalSwipesMoveBySentence() = openBook {
        reader().performTouchInput { swipeLeft() }
        waitForActive("Он вышел из дома, хотя шёл дождь.")
        reader().performTouchInput { swipeRight() } // finger moves right = back (§17.12)
        waitForActive("Глава 1")
    }

    @Test
    fun holdingPeeksAtThePreviousUnitUntilRelease() = openBook { scenario ->
        scenario.key(KeyEvent.KEYCODE_VOLUME_DOWN)
        waitForActive("Он вышел из дома, хотя шёл дождь.")
        reader().performTouchInput { down(center) }
        compose.mainClock.advanceTimeBy(1_000)
        waitForActive("Глава 1")
        reader().performTouchInput { up() }
        waitForActive("Он вышел из дома, хотя шёл дождь.")
    }

    @Test
    fun reopeningMidBookShowsTheRecapCard() = openBook { scenario ->
        scenario.key(KeyEvent.KEYCODE_VOLUME_DOWN)
        scenario.key(KeyEvent.KEYCODE_VOLUME_DOWN)
        waitForActive("На улице было пусто.")
        scenario.onActivity { it.onBackPressedDispatcher.onBackPressed() }
        waitFor(hasText("29.0%", substring = true))
        waitFor(hasText("book_ru"))

        compose.onNodeWithText("book_ru").performClick()
        waitFor(hasText("Он вышел из дома, хотя шёл дождь.", substring = true))
        compose.onNodeWithText("Tap to continue").performClick()
        waitForGone(hasText("Tap to continue"))
        waitForActive("На улице было пусто.")
    }

    @Test
    fun aLongGapStartsWithTheRecallCardThenRatingThenRecap() =
        openBook(first = "— Привет, — сказал он и улыбнулся.", prepare = ::lastReadLongAgo) {
            waitFor(hasText("What was happening?"))
            compose.onNodeWithText("Tap to continue").performClick()
            waitFor(hasText("Partial"))
            compose.onNodeWithText("Partial").performClick()
            waitFor(hasText("На улице было пусто.", substring = true)) // the recap
            compose.onNodeWithText("Tap to continue").performClick()
            waitForGone(hasText("Tap to continue"))
        }

    /** Position on S4 and one advance_log row from 1970 (§17.7 gap). */
    private fun lastReadLongAgo(file: File) =
        SQLiteDatabase.openDatabase(file.path, null, SQLiteDatabase.OPEN_READWRITE).use { db ->
            db.execSQL(
                "INSERT INTO reader_state (key, value) VALUES ('position', ?)",
                arrayOf("""{"sentence_id": 4, "chunk_start_token": 0}"""),
            )
            db.execSQL("INSERT INTO advance_log (ts, sentence_id, chunk_words, direction) VALUES (1.0, 3, 4, 1)")
        }

    @Test
    fun panelSetsModeGoalAndSwitches() = openBook { scenario ->
        openPanel()
        compose.onNodeWithText("Paragraph").performClick()
        compose.onNodeWithText("Paragraph").assertIsSelected()
        scenario.key(KeyEvent.KEYCODE_VOLUME_DOWN)
        waitForActive("Он вышел из дома, хотя шёл дождь. На улице было пусто.") // block 2 whole (§17.2)

        compose.onNodeWithText("15m").performClick()
        waitFor(hasText("goal 15m"))
        compose.onNodeWithTag("goal").assertTextEquals("▸ 15 min")
        compose.onNodeWithText("off").performClick()
        waitForGone(hasTestTag("goal"))

        compose.onNodeWithText("Recap").assertIsOn()
        compose.onNodeWithText("Recap").performClick()
        compose.onNodeWithText("Recap").assertIsOff()
        compose.onNodeWithText("Recall").performClick()
        compose.onNodeWithText("Recall").assertIsOff()
    }

    private fun waitForGone(matcher: SemanticsMatcher) =
        compose.waitUntil(timeoutMillis = 10_000) { compose.onAllNodes(matcher).fetchSemanticsNodes().isEmpty() }

    @Test
    fun theScreenStaysOnWhileReading() = openBook { scenario ->
        scenario.onActivity { assertTrue(it.window.decorView.keepScreenOn || it.findViewById<android.view.View>(android.R.id.content).keepScreenOn) }
    }

    @Suppress("unused")
    private val stateDescription = SemanticsProperties.StateDescription
}
