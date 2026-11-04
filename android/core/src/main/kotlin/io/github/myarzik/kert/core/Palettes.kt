package io.github.myarzik.kert.core

/** RGB (0xRRGGBB) colors of one theme on Android (§17.12). */
data class Palette(val background: Int, val active: Int, val rest: Int, val neighbor: Int)

object Palettes {
    fun of(theme: Theme): Palette = TODO()

    fun contrastRatio(a: Int, b: Int): Double = TODO()
}
