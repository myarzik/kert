from dataclasses import dataclass
from typing import Literal

BlockType = Literal["paragraph", "dialogue", "heading", "code", "list_item"]


@dataclass(frozen=True, slots=True)
class Block:
    id: int
    type: BlockType
    chapter: int | None = None


@dataclass(frozen=True, slots=True)
class SplitCandidate:
    # Index of the first token of the chunk that would start at this cut.
    token_index: int
    weight: float


@dataclass(frozen=True, slots=True)
class Sentence:
    id: int
    block_id: int
    seq: int
    text: str
    # (char_start, char_end) per spaCy token, offsets into `text`.
    tokens: tuple[tuple[int, int], ...]
    candidates: tuple[SplitCandidate, ...]


@dataclass(frozen=True, slots=True)
class ChunkSpan:
    # Half-open token range [start_token, end_token) within the sentence.
    sentence_id: int
    start_token: int
    end_token: int
