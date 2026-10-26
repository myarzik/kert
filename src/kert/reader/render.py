"""Pure frame builder: `build_frame(state) -> renderable` (spec §7, §13.1)."""

from dataclasses import dataclass

from rich.console import Console, Group, RenderableType
from rich.text import Text

from kert.reader.state import ReaderState, block_range

MAX_TEXT_WIDTH = 88
MARKER = "…"


@dataclass(frozen=True, slots=True)
class Theme:
    active: str
    rest: str
    neighbor: str
    status: str
    marker: str


# §7.2 / D12: explicit 256-color greys, never the `dim` attribute.
THEMES = {
    "dark": Theme("bold white", "grey50", "grey35", "grey50", "grey35"),
    "light": Theme("bold black", "grey62", "grey74", "grey62", "grey74"),
}


def build_frame(state: ReaderState) -> RenderableType:
    columns, rows = state.size
    width = min(columns - 4, MAX_TEXT_WIDTH)
    margin = " " * ((columns - width) // 2)
    theme = THEMES[state.settings.theme]
    height = rows - 1  # last row is the status line

    lines, first, last = _active_block(state, width, theme)
    if len(lines) > height:
        content = _clip(lines, first, last, height, theme)
    else:
        content = _with_neighbors(state, lines, height, width, theme)
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


def _clip(
    lines: list[Text], first: int, last: int, height: int, theme: Theme
) -> list[Text]:
    """Window of `height` rows centered on the active chunk, `…` per cut edge."""
    marker = Text(MARKER, style=theme.marker)
    shown = height - 2
    top = (first + last) // 2 - shown // 2
    top = max(min(top, first), last - shown + 1)  # keep the chunk visible
    top = max(0, min(top, len(lines) - shown))
    if top == 0:
        return [*lines[: height - 1], marker]
    if top + shown >= len(lines):
        return [marker, *lines[len(lines) - (height - 1) :]]
    return [marker, *lines[top : top + shown], marker]


def _with_neighbors(
    state: ReaderState, lines: list[Text], height: int, width: int, theme: Theme
) -> list[Text]:
    """Center the active block; add each neighbor only if it fits whole."""
    above_space = (height - len(lines)) // 2
    below_space = height - len(lines) - above_space
    start, end = block_range(state.chunks, state.index)

    above: list[Text] = []
    if start > 0:
        prev = _wrap(
            _block_text(state, *block_range(state.chunks, start - 1), theme.neighbor),
            width,
        )
        if len(prev) + 1 <= above_space:
            above = [*prev, Text()]
    below: list[Text] = []
    if end < len(state.chunks.spans):
        nxt = _wrap(
            _block_text(state, *block_range(state.chunks, end), theme.neighbor), width
        )
        if len(nxt) + 1 <= below_space:
            below = [Text(), *nxt]

    padding = [Text()] * (above_space - len(above))
    return [*padding, *above, *lines, *below]


def _status(state: ReaderState, width: int, theme: Theme) -> Text:
    left = f":{state.command}" if state.command is not None else state.message or ""
    right = f"{state.percent:.1f}%"
    left = left[: max(0, width - len(right) - 1)]
    return Text(
        left + " " * (width - len(left) - len(right)) + right, style=theme.status
    )
