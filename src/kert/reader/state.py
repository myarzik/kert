from dataclasses import dataclass

from kert.common.model import Block, Sentence
from kert.reader.config import Settings
from kert.reader.store import Position


@dataclass(frozen=True, slots=True)
class Book:
    blocks: tuple[Block, ...]
    sentences: tuple[Sentence, ...]
    word_count: int


@dataclass(frozen=True, slots=True)
class Advance:
    sentence_id: int
    chunk_words: int
    direction: int


@dataclass(frozen=True, slots=True)
class SaveSetting:
    key: str
    value: str


Effect = Advance | SaveSetting


@dataclass(frozen=True, slots=True)
class ReaderState:
    pass


def initial_state(
    book: Book,
    settings: Settings,
    position: Position,
    size: tuple[int, int] = (80, 24),
) -> ReaderState:
    raise NotImplementedError


def handle_key(state: ReaderState, key: str) -> ReaderState:
    raise NotImplementedError
