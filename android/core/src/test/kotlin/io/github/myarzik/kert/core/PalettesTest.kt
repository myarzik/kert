package io.github.myarzik.kert.core

import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test
import org.junit.jupiter.params.ParameterizedTest
import org.junit.jupiter.params.provider.EnumSource

/** §17.5 presets on the app's backgrounds (§17.12), same rules as tests/test_theme.py. */
class PalettesTest {
    @Test
    fun `contrast ratio extremes`() {
        assertEquals(21.0, Palettes.contrastRatio(0x000000, 0xFFFFFF), 1e-9)
        assertEquals(1.0, Palettes.contrastRatio(0x808080, 0x808080), 1e-9)
        assertEquals(5.32, Palettes.contrastRatio(0x808080, 0x000000), 0.01)
    }

    @Test
    fun `presets are the xterm-256 greys of the terminal themes`() {
        // dark: grey93, grey50, grey39; light: grey3, grey46, grey54 (§17.5).
        assertEquals(Palette(0x0E0E0E, 0xEEEEEE, 0x808080, 0x626262), Palettes.of(Theme.DARK))
        assertEquals(Palette(0xFFFFFF, 0x080808, 0x767676, 0x8A8A8A), Palettes.of(Theme.LIGHT))
    }

    @ParameterizedTest
    @EnumSource(Theme::class)
    fun `contrast floor on the app background`(theme: Theme) {
        val p = Palettes.of(theme)
        assertTrue(Palettes.contrastRatio(p.rest, p.background) >= 4.5)
        assertTrue(Palettes.contrastRatio(p.neighbor, p.background) >= 3.0)
        assertTrue(Palettes.contrastRatio(p.active, p.rest) >= 3.0)
        assertTrue(Palettes.contrastRatio(p.rest, p.neighbor) >= 1.25)
    }
}
