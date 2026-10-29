package io.github.myarzik.kert.app

import android.content.Intent
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.view.KeyEvent
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.runtime.mutableStateOf
import io.github.myarzik.kert.core.Library
import java.io.File

class MainActivity : ComponentActivity() {
    /** A `.kert` handed to us by another app (open / share), imported once. */
    private val incoming = mutableStateOf<Uri?>(null)
    private val readerHost = ReaderHost()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        if (savedInstanceState == null) incoming.value = intent.bookUri()
        val books = File(filesDir, "books").apply { mkdirs() }
        val library = Library(books.toPath()) { AndroidSqlConnection.open(it.toFile()) }
        val defaults = PrefsDefaults(this)
        val compiler = ChaquopyCompiler(this)
        setContent { KertApp(library, contentResolver, incoming, defaults, readerHost, compiler, cacheDir) }
    }

    override fun onKeyDown(keyCode: Int, event: KeyEvent): Boolean =
        readerHost.onKey?.invoke(keyCode) == true || super.onKeyDown(keyCode, event)

    override fun onKeyUp(keyCode: Int, event: KeyEvent): Boolean {
        // While reading, volume keys page instead of changing the volume.
        val paging = readerHost.onKey != null &&
            (keyCode == KeyEvent.KEYCODE_VOLUME_DOWN || keyCode == KeyEvent.KEYCODE_VOLUME_UP)
        return paging || super.onKeyUp(keyCode, event)
    }

    override fun onStart() {
        super.onStart()
        readerHost.onStart?.invoke()
    }

    override fun onStop() {
        readerHost.onStop?.invoke()
        super.onStop()
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        incoming.value = intent.bookUri()
    }

    private fun Intent.bookUri(): Uri? = when (action) {
        Intent.ACTION_VIEW -> data
        Intent.ACTION_SEND ->
            if (Build.VERSION.SDK_INT >= 33) getParcelableExtra(Intent.EXTRA_STREAM, Uri::class.java)
            else @Suppress("DEPRECATION") getParcelableExtra(Intent.EXTRA_STREAM)
        else -> null
    }
}
