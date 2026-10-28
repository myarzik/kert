package io.github.myarzik.kert.app

import java.io.File

/** The Python reference books (scripts/export_android_reference.py, §16.6). */
object Fixtures {
    private val dir: File by lazy {
        val path = File(System.getProperty("kert.reference") ?: "")
        check(File(path, "reference.json").isFile) {
            "Python reference missing at $path; run: " +
                "uv run python scripts/export_android_reference.py build/android-reference"
        }
        path
    }

    fun copy(name: String, into: File): File = File(dir, name).copyTo(File(into, name), overwrite = true)
}
