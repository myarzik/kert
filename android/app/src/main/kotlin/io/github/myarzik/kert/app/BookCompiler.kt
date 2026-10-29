package io.github.myarzik.kert.app

import android.content.Context
import com.chaquo.python.PyException
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform
import java.io.File

/** Turns a book (EPUB, FB2, Markdown, text) into a `.kert` file. */
fun interface BookCompiler {
    /** Compile [source] into [output]; throws [CompileException] with a readable message. */
    fun compile(source: File, output: File, lang: String): String
}

class CompileException(message: String) : Exception(message)

/** Suffixes the on-device compiler accepts (§14.1). */
val compilableSuffixes = listOf(".epub", ".fb2", ".fb2.zip", ".md", ".markdown", ".txt")

fun isCompilable(name: String) = compilableSuffixes.any { name.lowercase().endsWith(it) }

/** The Python compiler from src/kert running in-process via Chaquopy (spike). */
class ChaquopyCompiler(private val context: Context) : BookCompiler {
    override fun compile(source: File, output: File, lang: String): String {
        if (!Python.isStarted()) Python.start(AndroidPlatform(context.applicationContext))
        val version = context.packageManager.getPackageInfo(context.packageName, 0).versionName ?: "android"
        return try {
            Python.getInstance().getModule("kert_android")
                .callAttr("compile_book", source.path, output.path, lang, "$version-android")
                .toString()
        } catch (e: PyException) {
            // KertError messages are written for people; keep only the message line.
            throw CompileException(e.message?.substringAfter(": ")?.trim().orEmpty().ifEmpty { "Compilation failed." })
        }
    }
}
