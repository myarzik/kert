"""Pure frame builder: `build_frame(state) -> renderable` (spec §7, §13.1)."""

from rich.console import Console, Group, RenderableType
from rich.text import Text

from kert.reader.state import ReaderState, block_range
from kert.reader.theme import THEMES, Theme

MAX_TEXT_WIDTH = 88
MIN_COLUMNS = 40
NARROW_NOTICE = f"Terminal too narrow: {MIN_COLUMNS}+ columns needed"


def build_frame(state: ReaderState) -> RenderableType:
    columns, rows = state.size
    theme = THEMES[state.settings.theme]
    if columns < MIN_COLUMNS:
        notice = Text(NARROW_NOTICE[:columns], style=theme.status)
        return Group(notice, *([Text()] * (rows - 1)))
    width = min(columns - 4, MAX_TEXT_WIDTH)
    margin = " " * ((columns - width) // 2)
    height = rows - 1  # last row is the status line

    # Center focus (§7.1): the chunk's first line sits on row (H - h) // 2 and
    # the text runs above and below it as one tape, cut at the screen edges.
    lines, first, last = _active_block(state, width, theme)
    top = max(0, (height - (last - first + 1)) // 2)
    content = [
        *_tape_above(state, lines[:first], top, width, theme),
        *_tape_below(state, lines[first:], height - top, width, theme),
    ]
    content += [Text()] * (height - len(content))
    content.append(_status(state, width, theme))
    return Group(*(Text(margin) + line if line else line for line in content))


def _wrap(text: Text, width: int) -> list[Text]:
    lines = list(text.wrap(Console(width=width), width))
    for line in lines:
        line.rstrip()  # in place: drop the space left at each break
    return lines


def _block_text(state: ReaderState, start: int, end: int, style: str) -> Text:
    pos = state.chunks.sentence_pos
    sentences = state.book.sentences[pos[start] : pos[end - 1] + 1]
    if state.chunks.block_types[start] == "heading":
        style = f"bold {style}"  # §14.7
    return Text(" ".join(s.text for s in sentences), style=style)


def _active_block(
    state: ReaderState, width: int, theme: Theme
) -> tuple[list[Text], int, int]:
    """Wrapped active block and the first/last line holding the active chunk."""
    start, end = block_range(state.chunks, state.index)
    text = _block_text(state, start, end, theme.rest)

    pos = state.chunks.sentence_pos
    offset = 0
    for sentence in state.book.sentences[pos[start] : pos[state.index]]:
        offset += len(sentence.text) + 1
    tokens = state.book.sentences[pos[state.index]].tokens
    chunk = state.active
    chunk_start = offset + tokens[chunk.start_token][0]
    chunk_end = offset + tokens[chunk.end_token - 1][1]
    text.stylize(theme.active, chunk_start, chunk_end)

    lines = _wrap(text, width)
    hits = [
        i
        for i, line in enumerate(lines)
        if any(span.style == theme.active for span in line.spans)
    ]
    return lines, hits[0], hits[-1]


def _tape_above(
    state: ReaderState, rows: list[Text], space: int, width: int, theme: Theme
) -> list[Text]:
    """Exactly `space` rows ending just above the active chunk."""
    start, _ = block_range(state.chunks, state.index)
    while len(rows) < space and start > 0:
        prev, _ = block_range(state.chunks, start - 1)
        block = _wrap(_block_text(state, prev, start, theme.neighbor), width)
        rows = [*block, Text(), *rows]
        start = prev
    rows = rows[max(0, len(rows) - space) :] if space else []
    return [*([Text()] * (space - len(rows))), *rows]


def _tape_below(
    state: ReaderState, rows: list[Text], space: int, width: int, theme: Theme
) -> list[Text]:
    """At most `space` rows starting at the active chunk."""
    _, end = block_range(state.chunks, state.index)
    count = len(state.chunks.spans)
    while len(rows) < space and end < count:
        _, nxt = block_range(state.chunks, end)
        block = _wrap(_block_text(state, end, nxt, theme.neighbor), width)
        rows = [*rows, Text(), *block]
        end = nxt
    return rows[:space]


def _status(state: ReaderState, width: int, theme: Theme) -> Text:
    left = f":{state.command}" if state.command is not None else state.message or ""
    right = f"{state.percent:.1f}%"
    left = left[: max(0, width - len(right) - 1)]
    return Text(
        left + " " * (width - len(left) - len(right)) + right, style=theme.status
    )
