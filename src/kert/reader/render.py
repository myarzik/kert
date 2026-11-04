"""Pure frame builder: `build_frame(state) -> renderable` (spec §7, §13.1)."""

import math
from dataclasses import replace

from rich.console import Console, Group, RenderableType
from rich.text import Text

from kert.reader.state import (
    ReaderState,
    block_range,
    goal_seconds_left,
    goal_words_left,
    recap_start,
)
from kert.reader.tempo import tempo_wps
from kert.reader.theme import THEMES, Theme

MAX_TEXT_WIDTH = 88
MIN_COLUMNS = 40
NARROW_NOTICE = f"Terminal too narrow: {MIN_COLUMNS}+ columns needed"
# §17.7 re-entry screens: the status prompt of each overlay.
PROMPTS = {
    "recall": "recall: what was happening? — any key",
    "rating": "y recalled / p partial / n blank / Esc skip",
    "recap": "recap — any key",
}
LINE_PROMPT = "recall (one line, Enter to submit, Esc to skip):"  # §17.8


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
    if state.overlay is not None:
        content = []
        if state.overlay == "recap":
            content = _recap(state, height, width, theme)
        elif state.overlay == "line":
            center = (height - 1) // 2
            prompt = Text(LINE_PROMPT[:width], style=theme.status)
            content = [*[Text()] * center, prompt]
        content += [Text()] * (height - len(content))
        content.append(_status(state, width, theme))
        return Group(*(Text(margin) + line if line else line for line in content))

    # Peek (§17.3) frames the previous chunk as if it were active; the real
    # one is then plain rest-of-block text. The status line stays real.
    view = replace(state, index=state.index - 1) if state.peek else state
    lines, first, last = _active_block(view, width, theme)
    top = max(0, (height - (last - first + 1)) // 2)
    content = [
        *_tape_above(view, lines[:first], top, width, theme),
        *_tape_below(view, lines[first:], height - top, width, theme),
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
    first, (last, _) = state.chunks.sentence_pos[start], state.chunks.ends[end - 1]
    sentences = state.book.sentences[first : last + 1]
    if state.chunks.block_types[start] == "heading":
        style = f"bold {style}"  # §14.7
    return Text(" ".join(s.text for s in sentences), style=style)


def _active_block(
    state: ReaderState, width: int, theme: Theme
) -> tuple[list[Text], int, int]:
    """Wrapped active block and the first/last line holding the active chunk."""
    start, end = block_range(state.chunks, state.index)
    text = _block_text(state, start, end, theme.rest)

    # Character offset of each of the block's sentences in the block text.
    sentences = state.book.sentences
    block_first = state.chunks.sentence_pos[start]
    offsets = {block_first: 0}
    for i in range(block_first, state.chunks.ends[end - 1][0]):
        offsets[i + 1] = offsets[i] + len(sentences[i].text) + 1
    first, (last, end_token) = (
        state.chunks.sentence_pos[state.index],
        state.chunks.ends[state.index],
    )
    unit_start = offsets[first] + sentences[first].tokens[state.active.start_token][0]
    unit_end = offsets[last] + sentences[last].tokens[end_token - 1][1]
    text.stylize(theme.active, unit_start, unit_end)

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


def _unit_text(state: ReaderState, index: int) -> str:
    sentences, chunks = state.book.sentences, state.chunks
    first, start_token = chunks.sentence_pos[index], chunks.spans[index].start_token
    last, end_token = chunks.ends[index]
    parts = []
    for i in range(first, last + 1):
        sentence = sentences[i]
        lo = sentence.tokens[start_token][0] if i == first else 0
        hi = sentence.tokens[end_token - 1][1] if i == last else len(sentence.text)
        parts.append(sentence.text[lo:hi])
    return " ".join(parts)


def _recap(state: ReaderState, height: int, width: int, theme: Theme) -> list[Text]:
    """Recap units (§17.7) in rest style, ending just above the center row."""
    start = recap_start(state)
    rows: list[Text] = []
    i = start if start is not None else state.index
    while i < state.index:
        block_end = min(block_range(state.chunks, i)[1], state.index)
        style = theme.rest
        if state.chunks.block_types[i] == "heading":
            style = f"bold {style}"  # §14.7
        text = " ".join(_unit_text(state, j) for j in range(i, block_end))
        rows += [*([Text()] if rows else []), *_wrap(Text(text, style=style), width)]
        i = block_end
    space = (height - 1) // 2
    rows = rows[max(0, len(rows) - space) :] if space else []
    return [*([Text()] * (space - len(rows))), *rows]


def _status(state: ReaderState, width: int, theme: Theme) -> Text:
    if state.overlay == "line":
        left = f"> {state.line}"
    elif state.overlay is not None:
        left = PROMPTS[state.overlay]
    elif state.command is not None:
        left = f":{state.command}"
    else:
        left = state.message or ""
    right = _goal_segment(state) + f"{state.percent:.1f}%"
    left = left[: max(0, width - len(right) - 1)]
    return Text(
        left + " " * (width - len(left) - len(right)) + right, style=theme.status
    )


def _goal_segment(state: ReaderState) -> str:
    """`▸ 640 w · ~4 min` / `▸ 6 min · ~1100 w` before the percent (§17.6)."""
    if state.goal is None:
        return ""
    wps = tempo_wps(state.log, state.settings.mode)
    if state.goal.unit == "w":
        words = goal_words_left(state)
        segment = f"▸ {words} w"
        if wps:
            segment += f" · ~{max(1, math.ceil(words / wps / 60))} min"
    else:
        seconds = goal_seconds_left(state)
        segment = f"▸ {math.ceil(seconds / 60)} min"
        if wps:
            segment += f" · ~{round(seconds * wps, -1):.0f} w"
    return segment + "   "
