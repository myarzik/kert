package io.github.myarzik.kert.app

import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test
import org.junit.runner.RunWith

/** SharedPreferences as the app-defaults layer (§16.5), recap and recall included (§17.12). */
@RunWith(AndroidJUnit4::class)
class PrefsDefaultsTest {
    private val defaults = PrefsDefaults(ApplicationProvider.getApplicationContext())

    @Test
    fun recapAndRecallAreReadBackAsSwitches() {
        assertNull(defaults.recap)
        assertNull(defaults.recall)
        defaults.save("recap", "off")
        defaults.save("recall", "on")
        assertEquals(false, defaults.recap)
        assertEquals(true, defaults.recall)
    }
}
