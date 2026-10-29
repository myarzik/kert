package io.github.myarzik.kert.app

/** What the activity forwards to the open reader: volume keys and lifecycle. */
class ReaderHost {
    /** Returns true when the key was used. */
    var onKey: ((keyCode: Int) -> Boolean)? = null
    var onStart: (() -> Unit)? = null
    var onStop: (() -> Unit)? = null
}
