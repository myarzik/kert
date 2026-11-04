package io.github.myarzik.kert.core

import kotlin.math.pow

/** RGB (0xRRGGBB) colors of one theme on Android (§17.12). */
data class Palette(val background: Int, val active: Int, val rest: Int, val neighbor: Int)

/** The §17.5 presets as xterm-256 RGB, on the app's own backgrounds. */
object Palettes {
    private val DARK = Palette(background = 0x0E0E0E, active = 0xEEEEEE, rest = 0x808080, neighbor = 0x626262)
    private val LIGHT = Palette(background = 0xFFFFFF, active = 0x080808, rest = 0x767676, neighbor = 0x8A8A8A)

    fun of(theme: Theme): Palette = if (theme == Theme.DARK) DARK else LIGHT

    /** WCAG 2.x contrast ratio of two RGB colors. */
    fun contrastRatio(a: Int, b: Int): Double {
        val (darker, lighter) = listOf(luminance(a), luminance(b)).sorted()
        return (lighter + 0.05) / (darker + 0.05)
    }

    private fun luminance(rgb: Int): Double {
        fun channel(shift: Int): Double {
            val c = ((rgb shr shift) and 0xFF) / 255.0
            return if (c <= 0.04045) c / 12.92 else ((c + 0.055) / 1.055).pow(2.4)
        }
        return 0.2126 * channel(16) + 0.7152 * channel(8) + 0.0722 * channel(0)
    }
}
