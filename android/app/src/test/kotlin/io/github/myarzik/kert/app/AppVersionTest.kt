package io.github.myarzik.kert.app

import android.content.Context
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import java.io.File
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Test
import org.junit.runner.RunWith

/** The app's version follows the Python package version (§16.7). */
@RunWith(AndroidJUnit4::class)
class AppVersionTest {
    @Test
    fun versionNameAndCodeFollowPyproject() {
        val path = System.getProperty("kert.pyproject")
        assertNotNull("the build must pass kert.pyproject to the tests", path)
        val match = Regex("""(?m)^version\s*=\s*"(\d+)\.(\d+)\.(\d+)"""").find(File(path!!).readText())
        val (major, minor, patch) = match!!.destructured

        val context = ApplicationProvider.getApplicationContext<Context>()
        val info = context.packageManager.getPackageInfo(context.packageName, 0)

        assertEquals("$major.$minor.$patch", info.versionName)
        assertEquals(major.toLong() * 10000 + minor.toLong() * 100 + patch.toLong(), info.longVersionCode)
    }
}
