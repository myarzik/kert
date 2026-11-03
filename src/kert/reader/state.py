"""Pure Reader state machine: `handle_key(state, key) -> state` (spec §5, §8, §13.1).

Side effects are not performed here: each transition lists them in
`state.effects` (advance_log rows, `:set` writes) for the app loop to execute.
"""

from dataclasses import dataclass, replace

from readchar import key as keys

from kert.common.errors import KertError
from kert.common.model import Block, ChunkSpan, Sentence
from kert.common.text import is_word
from kert.reader.chunker import assemble
from kert.reader.commands import GotoCommand, QuitCommand, SetCommand, parse_command
from kert.reader.config import Settings
from kert.reader.store import Position

_NEXT = {" ", "j", keys.RIGHT}
_PREVIOUS = {"b", "k", keys.LEFT}
_ENTER = {keys.ENTER, keys.CR, keys.LF}


@dataclass(frozen=True, slots=True)
class Book:
    blocks: tuple[Block, ...]
    sentences: tuple[Sentence, ...]
    word_count: int  # meta.word_count


@dataclass(frozen=True, slots=True)
class Advance:
    sentence_id: int
    chunk_words: int  # words of the chunk just left
    direction: int  # +1 forward, -1 backward, 0 peek
    kind: str = "step"  # §17.4


@dataclass(frozen=True, slots=True)
class SaveSetting:
    key: str
    value: str


Effect = Advance | SaveSetting


@dataclass(frozen=True, slots=True)
class Chunks:
    """Book-wide chunk list at one width, with per-chunk lookup columns."""

    spans: tuple[ChunkSpan, ...]
    words: tuple[int, ...]
    words_before: tuple[int, ...]
    block_ids: tuple[int, ...]
    block_types: tuple[str, ...]
    sentence_pos: tuple[int, ...]  # index of each chunk's sentence in Book.sentences


def build_chunks(book: Book, width: int) -> Chunks:
    by_id = {s.id: s for s in book.sentences}
    pos = {s.id: i for i, s in enumerate(book.sentences)}
    types = {b.id: b.type for b in book.blocks}
    spans = tuple(assemble(book.sentences, width))
    words, before, total = [], [], 0
    for span in spans:
        sentence = by_id[span.sentence_id]
        count = sum(
            is_word(sentence.text[start:end])
            for start, end in sentence.tokens[span.start_token : span.end_token]
        )
        words.append(count)
        before.append(total)
        total += count
    return Chunks(
        spans=spans,
        words=tuple(words),
        words_before=tuple(before),
        block_ids=tuple(by_id[s.sentence_id].block_id for s in spans),
        block_types=tuple(types[by_id[s.sentence_id].block_id] for s in spans),
        sentence_pos=tuple(pos[s.sentence_id] for s in spans),
    )


def block_range(chunks: Chunks, index: int) -> tuple[int, int]:
    """Half-open chunk range of the block containing chunk `index`."""
    ids = chunks.block_ids
    start, end = index, index + 1
    while start > 0 and ids[start - 1] == ids[index]:
        start -= 1
    while end < len(ids) and ids[end] == ids[index]:
        end += 1
    return start, end


def _resolve(chunks: Chunks, sentence_id: int, token: int) -> int:
    """Chunk containing `token`, else the sentence's first chunk, else 0 (§5)."""
    first = None
    for i, span in enumerate(chunks.spans):
        if span.sentence_id != sentence_id:
            continue
        if span.start_token <= token < span.end_token:
            return i
        if first is None:
            first = i
    return 0 if first is None else first


@dataclass(frozen=True, slots=True)
class ReaderState:
    book: Book
    settings: Settings
    chunks: Chunks
    index: int
    size: tuple[int, int] = (80, 24)  # terminal (columns, rows)
    command: str | None = None  # `:` line contents; None outside command mode
    pending_g: bool = False
    peek: bool = False  # §17.3, transient
    message: str | None = None
    effects: tuple[Effect, ...] = ()
    quit: bool = False

    @property
    def active(self) -> ChunkSpan:
        return self.chunks.spans[self.index]

    @property
    def position(self) -> Position:
        return Position(self.active.sentence_id, self.active.start_token)

    @property
    def percent(self) -> float:
        if self.book.word_count <= 0:
            return 0.0
        before = self.chunks.words_before[self.index]
        return min(100.0, before / self.book.word_count * 100)


def initial_state(
    book: Book,
    settings: Settings,
    position: Position,
    size: tuple[int, int] = (80, 24),
) -> ReaderState:
    chunks = build_chunks(book, settings.chunk_width)
    index = _resolve(chunks, position.sentence_id, position.chunk_start_token)
    return ReaderState(book, settings, chunks, index, size=size)


def handle_key(state: ReaderState, key: str) -> ReaderState:
    state = replace(state, message=None, effects=())
    if state.peek:
        return replace(state, peek=False)  # §17.3: the key that ends peek is consumed
    if state.command is not None:
        return _command_key(state, key)
    if state.pending_g:
        state = replace(state, pending_g=False)
        if key == "g":
            return _move(state, 0, "jump")
    if key in _NEXT:
        return _step(state, 1)
    if key in _PREVIOUS:
        return _step(state, -1)
    if key == "J":
        return _next_block(state)
    if key == "K":
        return _previous_block(state)
    if key == "(":
        return _previous_sentence(state)
    if key == ")":
        return _next_sentence(state)
    if key == "p":
        return _peek(state)
    if key == "g":
        return replace(state, pending_g=True)
    if key == "G":
        return _move(state, len(state.chunks.spans) - 1, "jump")
    if key == ":":
        return replace(state, command="")
    if key == "q":
        return replace(state, quit=True)
    return state


def _move(state: ReaderState, target: int, kind: str) -> ReaderState:
    """Go to chunk `target`, logging the chunk left (§17.4); same chunk: no-op."""
    if target == state.index:
        return state
    left = Advance(
        sentence_id=state.active.sentence_id,
        chunk_words=state.chunks.words[state.index],
        direction=1 if target > state.index else -1,
        kind=kind,
    )
    return replace(state, index=target, effects=(left,))


def _step(state: ReaderState, direction: int) -> ReaderState:
    target = state.index + direction
    if not 0 <= target < len(state.chunks.spans):
        return state
    return _move(state, target, "step")


def _next_block(state: ReaderState) -> ReaderState:
    _, end = block_range(state.chunks, state.index)
    if end == len(state.chunks.spans):
        return state
    return _move(state, end, "block")


def _previous_block(state: ReaderState) -> ReaderState:
    start, _ = block_range(state.chunks, state.index)
    if start == 0:
        return state
    return _move(state, block_range(state.chunks, start - 1)[0], "block")


def _sentence_start(chunks: Chunks, index: int) -> int:
    pos = chunks.sentence_pos
    while index > 0 and pos[index - 1] == pos[index]:
        index -= 1
    return index


def _previous_sentence(state: ReaderState) -> ReaderState:
    start = _sentence_start(state.chunks, state.index)
    if start == state.index and start > 0:
        start = _sentence_start(state.chunks, start - 1)
    return _move(state, start, "sentence")


def _next_sentence(state: ReaderState) -> ReaderState:
    pos, target = state.chunks.sentence_pos, state.index
    while target < len(pos) and pos[target] == pos[state.index]:
        target += 1
    if target == len(pos):
        return state
    return _move(state, target, "sentence")


def _peek(state: ReaderState) -> ReaderState:
    if state.index == 0:
        return state
    shown = state.index - 1
    peeked = Advance(
        sentence_id=state.chunks.spans[shown].sentence_id,
        chunk_words=state.chunks.words[shown],
        direction=0,
        kind="peek",
    )
    return replace(state, peek=True, effects=(peeked,))


def _command_key(state: ReaderState, key: str) -> ReaderState:
    line = state.command or ""
    if key in _ENTER:
        return _run_command(replace(state, command=None), line)
    if key == keys.ESC:
        return replace(state, command=None)
    if key == keys.BACKSPACE:
        return replace(state, command=line[:-1] if line else None)
    if len(key) == 1 and key.isprintable():
        return replace(state, command=line + key)
    return state


def _run_command(state: ReaderState, line: str) -> ReaderState:
    if not line.strip():
        return state
    try:
        command = parse_command(line)
    except KertError as exc:
        return replace(state, message=str(exc))
    match command:
        case QuitCommand():
            return replace(state, quit=True)
        case GotoCommand(percent=percent):
            return _goto(state, percent)
        case SetCommand(key=key, value=value):
            return _set(state, key, value)


def _goto(state: ReaderState, percent: float) -> ReaderState:
    target = percent / 100 * state.book.word_count
    before = state.chunks.words_before
    # min() keeps the first of equally near chunks: ties go to the earlier one.
    index = min(range(len(before)), key=lambda i: abs(before[i] - target))
    return _move(state, index, "jump")


def _set(state: ReaderState, key: str, value: str) -> ReaderState:
    effects = (SaveSetting(key, value),)
    if key == "theme":
        settings = replace(state.settings, theme=value)
        return replace(
            state, settings=settings, effects=effects, message=f"theme={value}"
        )
    settings = replace(state.settings, chunk_width=int(value))
    chunks = build_chunks(state.book, settings.chunk_width)
    active = state.active
    index = _resolve(chunks, active.sentence_id, active.start_token)
    return replace(
        state,
        settings=settings,
        chunks=chunks,
        index=index,
        effects=effects,
        message=f"width={value}",
    )
