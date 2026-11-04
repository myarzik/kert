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
from kert.reader.commands import (
    GoalCommand,
    GotoCommand,
    QuitCommand,
    SetCommand,
    parse_command,
)
from kert.reader.config import Settings, parse_goal
from kert.reader.store import Position
from kert.reader.tempo import LogRow, active_seconds

_NEXT = {" ", "j", keys.RIGHT}
_PREVIOUS = {"b", "k", keys.LEFT}
_ENTER = {keys.ENTER, keys.CR, keys.LF}
LOG_KEEP = 1000  # recent advance_log rows held for tempo (§17.6)
GOAL_REACHED = "goal reached — :goal again"


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


@dataclass(frozen=True, slots=True)
class Checkpoint:
    """A checkpoints row (§17.8) for the app to write."""

    trigger: str
    mode: str
    span_start_sentence: int
    span_end_sentence: int
    span_words: int
    recall_text: str | None
    self_rating: int | None


Effect = Advance | SaveSetting | Checkpoint


@dataclass(frozen=True, slots=True)
class Chunks:
    """Book-wide list of reading units at one width and mode (§6, §17.2).

    A unit is a chunk, a sentence or a whole block. `spans[i]` anchors unit i
    at its first sentence and token; `ends[i]` is the (sentence index, end
    token) where it stops, possibly in a later sentence of the same block.
    """

    spans: tuple[ChunkSpan, ...]
    ends: tuple[tuple[int, int], ...]
    words: tuple[int, ...]
    words_before: tuple[int, ...]
    block_ids: tuple[int, ...]
    block_types: tuple[str, ...]
    sentence_pos: tuple[
        int, ...
    ]  # index of each unit's first sentence in Book.sentences


def _units(book: Book, width: int, mode: str) -> list[tuple[ChunkSpan, int, int]]:
    """(anchor span, last sentence index, end token) of each unit."""
    pos = {s.id: i for i, s in enumerate(book.sentences)}
    if mode == "chunk":
        return [
            (span, pos[span.sentence_id], span.end_token)
            for span in assemble(book.sentences, width)
        ]
    units: list[tuple[ChunkSpan, int, int]] = []
    for i, sentence in enumerate(book.sentences):
        end = len(sentence.tokens)
        same_block = (
            units and book.sentences[units[-1][1]].block_id == sentence.block_id
        )
        if mode == "paragraph" and same_block:
            units[-1] = (units[-1][0], i, end)
        else:
            units.append((ChunkSpan(sentence.id, 0, end), i, end))
    return units


def _count_words(book: Book, first: int, start: int, last: int, end: int) -> int:
    total = 0
    for i in range(first, last + 1):
        sentence = book.sentences[i]
        tokens = sentence.tokens[
            start if i == first else 0 : end if i == last else len(sentence.tokens)
        ]
        total += sum(is_word(sentence.text[a:b]) for a, b in tokens)
    return total


def build_chunks(book: Book, width: int, mode: str = "chunk") -> Chunks:
    pos = {s.id: i for i, s in enumerate(book.sentences)}
    types = {b.id: b.type for b in book.blocks}
    units = _units(book, width, mode)
    words, before, total = [], [], 0
    for span, last, end in units:
        count = _count_words(book, pos[span.sentence_id], span.start_token, last, end)
        words.append(count)
        before.append(total)
        total += count
    block_ids = tuple(
        book.sentences[pos[span.sentence_id]].block_id for span, _, _ in units
    )
    return Chunks(
        spans=tuple(span for span, _, _ in units),
        ends=tuple((last, end) for _, last, end in units),
        words=tuple(words),
        words_before=tuple(before),
        block_ids=block_ids,
        block_types=tuple(types[b] for b in block_ids),
        sentence_pos=tuple(pos[span.sentence_id] for span, _, _ in units),
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


def _resolve(book: Book, chunks: Chunks, sentence_id: int, token: int) -> int:
    """Unit containing `token`, else the sentence's first unit, else 0 (§5)."""
    target = next(
        (i for i, s in enumerate(book.sentences) if s.id == sentence_id), None
    )
    if target is None:
        return 0
    first = None
    for i, span in enumerate(chunks.spans):
        last, end = chunks.ends[i]
        if not chunks.sentence_pos[i] <= target <= last:
            continue
        lo = span.start_token if chunks.sentence_pos[i] == target else 0
        if lo <= token and (last > target or token < end):
            return i
        if first is None:
            first = i
    return 0 if first is None else first


@dataclass(frozen=True, slots=True)
class Goal:
    """A session goal (§17.6): `amount` minutes ("m") or words ("w")."""

    amount: int
    unit: str
    armed_at: float  # clock when armed; active time counts after it
    start_words: int  # words before the active unit when armed


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
    now: float = 0.0  # clock at the current key, set by the app loop
    log: tuple[LogRow, ...] = ()  # recent advance_log rows (§17.6)
    goal: Goal | None = None
    last_goal: tuple[int, str] | None = None  # for `:goal again`
    overlay: str | None = None
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
    now: float = 0.0,
    log: tuple[LogRow, ...] = (),
) -> ReaderState:
    chunks = build_chunks(book, settings.chunk_width, settings.mode)
    index = _resolve(book, chunks, position.sentence_id, position.chunk_start_token)
    state = ReaderState(book, settings, chunks, index, size=size, now=now, log=log)
    default = parse_goal(settings.default_goal)
    return _arm(state, *default) if default else state


def start_session(state: ReaderState) -> ReaderState:
    """Open a reading session: the re-entry flow of §17.7, if any."""
    return replace(state, overlay=_entry_overlay(state))


def recap_start(state: ReaderState) -> int | None:
    """First unit of the recap (§17.7): whole units back to `recap_words`."""
    if state.index == 0:
        return None
    start, words = state.index - 1, state.chunks.words[state.index - 1]
    while start > 0 and words < state.settings.recap_words:
        start -= 1
        words += state.chunks.words[start]
    return start


def _entry_overlay(state: ReaderState) -> str | None:
    """Re-entry flow (§17.7): recall prompt after a long gap, else the recap."""
    if state.index == 0:
        return None
    if state.log and state.settings.recall:
        gap = state.now - max(row.ts for row in state.log)
        if gap >= state.settings.recall_gap_minutes * 60:
            return "recall"
    return "recap" if state.settings.recap else None


def goal_words_left(state: ReaderState) -> int:
    goal = state.goal
    assert goal is not None and goal.unit == "w"
    read = state.chunks.words_before[state.index] - goal.start_words
    return max(0, goal.amount - read)


def goal_seconds_left(state: ReaderState) -> float:
    goal = state.goal
    assert goal is not None and goal.unit == "m"
    active = active_seconds(state.log, state.settings.mode, goal.armed_at)
    return max(0.0, goal.amount * 60 - active)


def handle_key(state: ReaderState, key: str) -> ReaderState:
    state = _dispatch(replace(state, message=None, effects=()), key)
    rows = tuple(
        LogRow(state.now, e.chunk_words, e.direction, e.kind, state.settings.mode)
        for e in state.effects
        if isinstance(e, Advance)
    )
    if rows:
        state = replace(state, log=(state.log + rows)[-LOG_KEEP:])
    return _check_goal(state)


def _check_goal(state: ReaderState) -> ReaderState:
    goal = state.goal
    if goal is None:
        return state
    left = goal_words_left(state) if goal.unit == "w" else goal_seconds_left(state)
    if left > 0:
        return state
    # No automatic re-arming: the reward resets motivation (§17.6).
    return replace(state, goal=None, message=GOAL_REACHED)


def _arm(state: ReaderState, amount: int, unit: str) -> ReaderState:
    goal = Goal(amount, unit, state.now, state.chunks.words_before[state.index])
    return replace(state, goal=goal, last_goal=(amount, unit))


_RATINGS = {"y": 2, "p": 1, "n": 0, keys.ESC: None}


def _overlay_key(state: ReaderState, key: str) -> ReaderState:
    """Keys on the re-entry screens (§17.7); every key here is consumed."""
    if state.overlay == "recall":
        return replace(state, overlay="rating")
    if state.overlay == "rating":
        if key not in _RATINGS:
            return state
        sentence_id = state.active.sentence_id
        row = Checkpoint(
            trigger="open",
            mode=state.settings.mode,
            span_start_sentence=sentence_id,
            span_end_sentence=sentence_id,
            span_words=0,
            recall_text=None,
            self_rating=_RATINGS[key],
        )
        after = "recap" if state.settings.recap else None
        return replace(state, overlay=after, effects=(row,))
    return replace(state, overlay=None)  # recap: any key starts reading


def _dispatch(state: ReaderState, key: str) -> ReaderState:
    if state.overlay is not None:
        return _overlay_key(state, key)
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
        case GoalCommand(action="off"):
            return replace(state, goal=None, message="goal off")
        case GoalCommand(action="again"):
            if state.last_goal is None:
                return replace(state, message="no goal to re-arm")
            amount, unit = state.last_goal
            return replace(_arm(state, amount, unit), message=f"goal {amount}{unit}")
        case GoalCommand(amount=amount, unit=unit):
            return replace(_arm(state, amount, unit), message=f"goal {amount}{unit}")


def _goto(state: ReaderState, percent: float) -> ReaderState:
    target = percent / 100 * state.book.word_count
    before = state.chunks.words_before
    # min() keeps the first of equally near chunks: ties go to the earlier one.
    index = min(range(len(before)), key=lambda i: abs(before[i] - target))
    return _move(state, index, "jump")


_FEEDBACK = {"chunk_width": "width"}  # :set names that differ from storage keys


def _set(state: ReaderState, key: str, value: str) -> ReaderState:
    effects = (SaveSetting(key, value),)
    message = f"{_FEEDBACK.get(key, key)}={value}"
    if key == "theme":
        settings = replace(state.settings, theme=value)
        return replace(state, settings=settings, effects=effects, message=message)
    if key == "mode":
        settings = replace(state.settings, mode=value)
    else:
        settings = replace(state.settings, chunk_width=int(value))
    chunks = build_chunks(state.book, settings.chunk_width, settings.mode)
    active = state.active
    index = _resolve(state.book, chunks, active.sentence_id, active.start_token)
    return replace(
        state,
        settings=settings,
        chunks=chunks,
        index=index,
        effects=effects,
        message=message,
    )
