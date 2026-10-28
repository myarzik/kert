package io.github.myarzik.kert.app

import android.content.Intent
import android.net.Uri
import android.os.Build
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.runtime.mutableStateOf
import io.github.myarzik.kert.core.Library
import java.io.File

class MainActivity : ComponentActivity() {
    /** A `.kert` handed to us by another app (open / share), imported once. */
    private val incoming = mutableStateOf<Uri?>(null)

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        if (savedInstanceState == null) incoming.value = intent.bookUri()
        val books = File(filesDir, "books").apply { mkdirs() }
        val library = Library(books.toPath()) { AndroidSqlConnection.open(it.toFile()) }
        setContent { KertApp(library, contentResolver, incoming) }
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
