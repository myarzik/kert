package io.github.myarzik.kert.core

import org.junit.jupiter.params.ParameterizedTest
import org.junit.jupiter.params.provider.ValueSource
import org.junit.jupiter.api.Assertions.assertFalse
import org.junit.jupiter.api.Assertions.assertTrue

/** Same cases as tests/test_text.py, plus Unicode beyond ASCII (§16.3). */
class WordsTest {
    @ParameterizedTest
    @ValueSource(strings = ["Да", "word", "10", "3,5", "1.25", "ёж", "𝔸𝔹", "٣", "١٢.٥"])
    fun words(text: String) = assertTrue(Words.isWord(text), text)

    @ParameterizedTest
    @ValueSource(strings = ["—", ",", ".", "1.", "кто-то", "a1", "", "def()", "🙂", "1,"])
    fun `non words`(text: String) = assertFalse(Words.isWord(text), text)
}
