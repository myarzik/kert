from collections.abc import Sequence

from kert.common.model import Sentence


def render_inspection(sentence: Sentence, width: int) -> str:
    raise NotImplementedError


def select_sentences(
    sentences: Sequence[Sentence],
    *,
    sentence: int | None = None,
    block: int | None = None,
    span: tuple[int, int] | None = None,
) -> list[Sentence]:
    raise NotImplementedError


def parse_range(raw: str) -> tuple[int, int]:
    raise NotImplementedError
