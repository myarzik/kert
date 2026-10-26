from collections.abc import Sequence

from kert.common.model import ChunkSpan, Sentence, SplitCandidate


def length_penalty(length: int, width: int) -> float:
    raise NotImplementedError


def cut_penalty(weight: float) -> float:
    raise NotImplementedError


def chunk_sentence(
    n: int, candidates: Sequence[SplitCandidate], width: int
) -> list[tuple[int, int]]:
    raise NotImplementedError


def assemble(sentences: Sequence[Sentence], width: int) -> list[ChunkSpan]:
    raise NotImplementedError
