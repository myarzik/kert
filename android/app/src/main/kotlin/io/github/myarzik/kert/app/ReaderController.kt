package io.github.myarzik.kert.app

import io.github.myarzik.kert.core.Action
import io.github.myarzik.kert.core.ReaderState
import io.github.myarzik.kert.core.ReadingSession
import io.github.myarzik.kert.core.Settings
import io.github.myarzik.kert.core.SettingsDefaults
import java.io.File
import java.util.concurrent.Executors
import kotlinx.coroutines.asCoroutineDispatcher
import kotlinx.coroutines.withContext

/**
 * One book's [ReadingSession], confined to a single background thread: SQLite
 * writes (advance_log, settings, position) never run on the UI thread.
 */
class ReaderController(
    private val file: File,
    private val defaults: SettingsDefaults,
    private val fallback: Settings,
) {
    private val executor = Executors.newSingleThreadExecutor()
    private val thread = executor.asCoroutineDispatcher()
    private var session: ReadingSession? = null

    /** Open (or reopen after [close]) and return the current state. */
    suspend fun open(): ReaderState = withContext(thread) {
        session?.state ?: ReadingSession.open(AndroidSqlConnection.open(file), defaults, fallback, ::now)
            .also { session = it }
            .state
    }

    suspend fun dispatch(action: Action): ReaderState? = withContext(thread) { session?.dispatch(action) }

    /** Save the position, cap advance_log, checkpoint and close (§16.4). */
    suspend fun close() = withContext(thread) { closeNow() }

    /** Close without waiting, then stop the thread: for teardown paths. */
    fun release() {
        executor.execute { closeNow() }
        executor.shutdown()
    }

    private fun closeNow() {
        session?.close()
        session = null
    }

    private fun now(): Double = System.currentTimeMillis() / 1000.0
}
