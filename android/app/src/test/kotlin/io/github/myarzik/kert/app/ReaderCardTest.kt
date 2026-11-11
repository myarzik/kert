package io.github.myarzik.kert.app

import androidx.compose.ui.test.hasText
import androidx.compose.ui.test.junit4.v2.createComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performTextInput
import androidx.test.ext.junit.runners.AndroidJUnit4
import io.github.myarzik.kert.core.Action
import io.github.myarzik.kert.core.KertReader
import io.github.myarzik.kert.core.Overlay
import io.github.myarzik.kert.core.Position
import io.github.myarzik.kert.core.Reader
import io.github.myarzik.kert.core.ReaderState
import io.github.myarzik.kert.core.Settings
import io.github.myarzik.kert.core.Theme
import java.nio.file.Files
import org.junit.Assert.assertEquals
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

/** The re-entry and checkpoint cards and the actions they send (§17.7, §17.8, §17.12). */
@RunWith(AndroidJUnit4::class)
class ReaderCardTest {
    @get:Rule
    val compose = createComposeRule()

    private val sent = mutableListOf<Action>()

    private fun show(overlay: Overlay, recap: String? = null, message: String? = null) {
        val file = Fixtures.copy("book_ru.kert", Files.createTempDirectory("cards").toFile())
        val book = AndroidSqlConnection.open(file).use { KertReader.read(it) }
        val state: ReaderState = Reader.initial(book, Settings(8, Theme.DARK), Position(4, 0))
            .copy(overlay = overlay, message = message)
        compose.setContent { ReaderCard(state, recap) { sent += it } }
    }

    @Test
    fun recallCardContinuesOnTap() {
        show(Overlay.RECALL)
        compose.onNodeWithText("What was happening?").assertExists()
        compose.onNodeWithText("Tap to continue").performClick()
        assertEquals(listOf<Action>(Action.Continue), sent)
    }

    @Test
    fun ratingButtons() {
        show(Overlay.RATING)
        for (label in listOf("Recalled", "Partial", "Blank", "Skip")) compose.onNodeWithText(label).performClick()
        assertEquals(listOf(Action.Rate(2), Action.Rate(1), Action.Rate(0), Action.Rate(null)), sent)
    }

    @Test
    fun lineCardSubmitsTheTypedText() {
        show(Overlay.LINE, message = Reader.GOAL_REACHED)
        compose.onNodeWithText(Reader.GOAL_REACHED).assertExists() // above the line (§17.6)
        compose.onNodeWithTag("recall-line").performTextInput("дождь и зонт")
        compose.onNodeWithText("Submit").performClick()
        assertEquals(listOf<Action>(Action.SubmitRecall("дождь и зонт")), sent)
    }

    @Test
    fun lineCardSkips() {
        show(Overlay.LINE)
        compose.onNodeWithText("Skip").performClick()
        assertEquals(listOf<Action>(Action.SkipRecall), sent)
    }

    @Test
    fun recapCardShowsTheTextAndContinues() {
        show(Overlay.RECAP, recap = "Глава 1\n\nОн вышел из дома, хотя шёл дождь.")
        compose.onNode(hasText("Он вышел из дома", substring = true)).assertExists()
        compose.onNodeWithText("Tap to continue").performClick()
        assertEquals(listOf<Action>(Action.Continue), sent)
    }
}
