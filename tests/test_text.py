import pytest

from kert.common.text import is_word, whitespace_tokens

# --- Shared word predicate (§14.3) ----------------------------------------------


@pytest.mark.parametrize("text", ["Да", "word", "10", "3,5", "1.25", "ёж"])
def test_words(text):
    assert is_word(text)


@pytest.mark.parametrize("text", ["—", ",", ".", "1.", "кто-то", "a1", "", "def()"])
def test_non_words(text):
    assert not is_word(text)


# --- Tokens of un-chunked blocks: \S+ runs (§14.3) --------------------------------


def test_whitespace_tokens_are_char_spans_of_non_space_runs():
    text = "Глава 1. Начало"
    spans = whitespace_tokens(text)

    assert spans == ((0, 5), (6, 8), (9, 15))
    assert [text[s:e] for s, e in spans] == ["Глава", "1.", "Начало"]


def test_whitespace_tokens_keep_code_layout_offsets():
    text = "def f():\n    return 1"

    assert [text[s:e] for s, e in whitespace_tokens(text)] == [
        "def", "f():", "return", "1",
    ]  # fmt: skip


def test_whitespace_tokens_of_blank_text():
    assert whitespace_tokens("  \n ") == ()
