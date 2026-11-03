package io.github.myarzik.kert.app

import android.content.Context
import androidx.compose.ui.test.hasText
import androidx.compose.ui.test.junit4.v2.createEmptyComposeRule
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.test.core.app.ActivityScenario
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

/** The APK carries the notices of the libraries it bundles and shows them (§16.7). */
@RunWith(AndroidJUnit4::class)
class ThirdPartyNoticesTest {
    @get:Rule
    val compose = createEmptyComposeRule()

    private fun notices(): String =
        ApplicationProvider.getApplicationContext<Context>().assets
            .open(NOTICES_ASSET).bufferedReader().use { it.readText() }

    @Test
    fun noticesListTheBundledLibrariesWithTheirLicenseTexts() {
        val text = notices()
        for (module in listOf("androidx.compose.ui:ui:", "org.msgpack:msgpack-core:", "org.jetbrains.kotlin:kotlin-stdlib:")) {
            assertTrue("missing $module", text.lines().any { it.startsWith(module) && it.contains("Apache-2.0") })
        }
        assertTrue(text.contains("TERMS AND CONDITIONS FOR USE, REPRODUCTION, AND DISTRIBUTION"))
        assertTrue("kert itself is MIT", text.contains("MIT License"))
    }

    @Test
    fun libraryOpensTheLicenses() {
        ActivityScenario.launch(MainActivity::class.java).use {
            compose.onNodeWithText("Licenses").performClick()
            compose.waitUntil(10_000) {
                compose.onAllNodes(hasText("org.msgpack:msgpack-core", substring = true)).fetchSemanticsNodes().isNotEmpty()
            }
        }
    }
}
