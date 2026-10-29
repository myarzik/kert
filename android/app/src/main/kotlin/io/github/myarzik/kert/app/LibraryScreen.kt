package io.github.myarzik.kert.app

import android.content.ContentResolver
import android.net.Uri
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.clickable
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FloatingActionButton
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.ListItem
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.MutableState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import io.github.myarzik.kert.core.KertFormatException
import io.github.myarzik.kert.core.Library
import io.github.myarzik.kert.core.LibraryEntry
import io.github.myarzik.kert.core.SettingsDefaults
import io.github.myarzik.kert.core.StagedBook
import java.io.File
import java.io.IOException
import java.text.DateFormat
import java.util.Date
import java.util.Locale
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/** Library ↔ reader navigation with book import (§16.4). */
@Composable
fun KertApp(
    library: Library,
    resolver: ContentResolver,
    incoming: MutableState<Uri?>,
    defaults: SettingsDefaults,
    host: ReaderHost,
    compiler: BookCompiler,
    cacheDir: File,
) {
    val dark = isSystemInDarkTheme()
    MaterialTheme(colorScheme = if (dark) darkColorScheme() else lightColorScheme()) {
        val scope = rememberCoroutineScope()
        val snackbar = remember { SnackbarHostState() }
        var books by remember { mutableStateOf<List<LibraryEntry>?>(null) }
        var duplicate by remember { mutableStateOf<StagedBook?>(null) }
        var deleting by remember { mutableStateOf<LibraryEntry?>(null) }
        var reading by remember { mutableStateOf<LibraryEntry?>(null) }
        var choosingLanguage by remember { mutableStateOf<Pair<Uri, String>?>(null) }
        var compiling by remember { mutableStateOf<String?>(null) }

        suspend fun refresh() {
            books = withContext(Dispatchers.IO) { library.list() }
        }

        suspend fun commit(staged: StagedBook, replace: Boolean) {
            withContext(Dispatchers.IO) { library.commit(staged, replace) }
            refresh()
        }

        suspend fun stageAndCommit(open: () -> java.io.InputStream) {
            val staged = withContext(Dispatchers.IO) { library.stage(open()) }
            if (staged.duplicateOf != null) duplicate = staged else commit(staged, replace = true)
        }

        fun import(uri: Uri) = scope.launch {
            val failure = try {
                val name = displayName(resolver, uri)
                if (isCompilable(name)) {
                    choosingLanguage = uri to name // compiled on the phone (§16 spike)
                } else {
                    stageAndCommit { resolver.openInputStream(uri) ?: throw IOException("no content") }
                }
                null
            } catch (e: KertFormatException) {
                e.message
            } catch (e: IOException) {
                "Cannot open this file (${e.message})."
            } catch (e: SecurityException) {
                "Cannot open this file (${e.message})."
            }
            failure?.let { snackbar.showSnackbar(it) }
        }

        fun compileAndImport(uri: Uri, name: String, lang: String) = scope.launch {
            compiling = name
            val failure = try {
                val output = withContext(Dispatchers.IO) {
                    val work = File(cacheDir, "compile").apply { deleteRecursively(); mkdirs() }
                    val source = File(work, name)
                    (resolver.openInputStream(uri) ?: throw IOException("no content")).use { input ->
                        source.outputStream().use { input.copyTo(it) }
                    }
                    File(work, "book.kert").also { compiler.compile(source, it, lang) }
                }
                stageAndCommit { output.inputStream() }
                null
            } catch (e: CompileException) {
                e.message
            } catch (e: KertFormatException) {
                e.message
            } catch (e: IOException) {
                "Cannot open this file (${e.message})."
            } finally {
                compiling = null
            }
            failure?.let { snackbar.showSnackbar(it) }
        }

        val picker = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri ->
            uri?.let(::import)
        }
        LaunchedEffect(Unit) { refresh() }
        LaunchedEffect(incoming.value) {
            incoming.value?.let { uri ->
                incoming.value = null
                import(uri)
            }
        }

        val open = reading
        if (open != null) {
            ReaderScreen(open, defaults, dark, host, onBack = {
                reading = null
                scope.launch { refresh() }
            })
        } else {
            LibraryScreen(
                books = books,
                snackbar = snackbar,
                onAdd = { picker.launch(arrayOf("*/*")) },
                onOpen = { reading = it },
                onDelete = { deleting = it },
            )
        }

        choosingLanguage?.let { (uri, name) ->
            AlertDialog(
                onDismissRequest = { choosingLanguage = null },
                title = { Text("Book language") },
                text = { Text("“$name” will be prepared for reading on this phone. Which language is it in?") },
                confirmButton = {
                    TextButton(onClick = { choosingLanguage = null; compileAndImport(uri, name, "ru") }) { Text("Russian") }
                },
                dismissButton = {
                    TextButton(onClick = { choosingLanguage = null; compileAndImport(uri, name, "en") }) { Text("English") }
                },
            )
        }
        compiling?.let { name ->
            AlertDialog(
                onDismissRequest = {},
                title = { Text("Preparing book") },
                text = {
                    Column {
                        LinearProgressIndicator(Modifier.fillMaxWidth())
                        Text(
                            "Analysing “$name”. The first book after installing takes longer " +
                                "while the language models load.",
                            modifier = Modifier.padding(top = 16.dp),
                        )
                    }
                },
                confirmButton = {},
            )
        }
        duplicate?.let { staged ->
            AlertDialog(
                onDismissRequest = {},
                title = { Text("Replace book?") },
                text = {
                    Text(
                        "“${staged.title}” is already in your library. Replacing it resets " +
                            "its reading position.",
                    )
                },
                confirmButton = {
                    TextButton(onClick = { duplicate = null; scope.launch { commit(staged, replace = true) } }) {
                        Text("Replace")
                    }
                },
                dismissButton = {
                    TextButton(onClick = { duplicate = null; scope.launch { commit(staged, replace = false) } }) {
                        Text("Keep")
                    }
                },
            )
        }
        deleting?.let { entry ->
            AlertDialog(
                onDismissRequest = { deleting = null },
                title = { Text("Delete book?") },
                text = { Text("“${entry.title}” and its reading position will be removed from this phone.") },
                confirmButton = {
                    TextButton(onClick = {
                        deleting = null
                        scope.launch {
                            withContext(Dispatchers.IO) { library.delete(entry) }
                            refresh()
                        }
                    }) { Text("Delete") }
                },
                dismissButton = { TextButton(onClick = { deleting = null }) { Text("Cancel") } },
            )
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun LibraryScreen(
    books: List<LibraryEntry>?,
    snackbar: SnackbarHostState,
    onAdd: () -> Unit,
    onOpen: (LibraryEntry) -> Unit,
    onDelete: (LibraryEntry) -> Unit,
) {
    Scaffold(
        topBar = { TopAppBar(title = { Text("kert") }) },
        floatingActionButton = { FloatingActionButton(onClick = onAdd) { Text("+") } },
        snackbarHost = { SnackbarHost(snackbar) },
    ) { padding ->
        when {
            books == null -> Unit
            books.isEmpty() -> Text(
                "No books yet. Tap + or open an EPUB, FB2, Markdown or text file " +
                    "(or a .kert compiled on your computer) with kert.",
                modifier = Modifier.padding(padding).padding(24.dp),
            )
            else -> LazyColumn(Modifier.padding(padding).fillMaxSize()) {
                items(books, key = { it.file.toString() }) { entry ->
                    ListItem(
                        headlineContent = { Text(entry.title) },
                        supportingContent = { Text(progress(entry)) },
                        trailingContent = { TextButton(onClick = { onDelete(entry) }) { Text("Delete") } },
                        modifier = Modifier.fillMaxWidth().clickable { onOpen(entry) },
                    )
                    HorizontalDivider()
                }
            }
        }
    }
}

/** The file name another app or the picker reports for [uri]. */
private fun displayName(resolver: ContentResolver, uri: Uri): String =
    resolver.query(uri, arrayOf(android.provider.OpenableColumns.DISPLAY_NAME), null, null, null)
        ?.use { c -> if (c.moveToFirst()) c.getString(0) else null }
        ?: uri.lastPathSegment.orEmpty()

private fun progress(entry: LibraryEntry): String {
    val percent = entry.percent ?: return "Not started"
    val read = entry.lastRead?.let {
        " · " + DateFormat.getDateInstance(DateFormat.MEDIUM, Locale.getDefault()).format(Date(it * 1000))
    }.orEmpty()
    return String.format(Locale.ROOT, "%.1f%%", percent) + read
}
