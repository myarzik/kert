"""Text helpers shared by Compiler and Reader (spec §14.3)."""

import re

_NUMBER = re.compile(r"\d+(?:[.,]\d+)*")
_NON_SPACE = re.compile(r"\S+")


def is_word(text: str) -> bool:
    """Alphabetic or numeric token: the spaCy-free word predicate."""
    return text.isalpha() or _NUMBER.fullmatch(text) is not None


def whitespace_tokens(text: str) -> tuple[tuple[int, int], ...]:
    """Char spans of the `\\S+` runs: tokens of un-chunked blocks."""
    return tuple(m.span() for m in _NON_SPACE.finditer(text))
