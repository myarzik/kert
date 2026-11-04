"""Reading tempo and active time from advance_log rows (spec §17.6)."""

import statistics
from collections.abc import Iterable, Iterator
from itertools import pairwise
from typing import NamedTuple

MIN_DWELL, MAX_DWELL = 0.15, 60.0  # skip-through / idle bounds, seconds
WINDOW, MIN_SAMPLES = 200, 30


class LogRow(NamedTuple):
    ts: float
    chunk_words: int
    direction: int
    kind: str
    mode: str


def _forward_steps(rows: Iterable[LogRow], mode: str) -> list[LogRow]:
    steps = (
        r for r in rows if r.kind == "step" and r.direction == 1 and r.mode == mode
    )
    return sorted(steps, key=lambda row: row.ts)


def _kept_dwells(rows: list[LogRow]) -> Iterator[tuple[LogRow, float]]:
    """Each row with the time spent on the unit it left, idle and skips dropped."""
    for previous, row in pairwise(rows):
        dwell = row.ts - previous.ts
        if MIN_DWELL <= dwell <= MAX_DWELL:
            yield row, dwell


def tempo_wps(rows: Iterable[LogRow], mode: str) -> float | None:
    """Median words per second over the last 200 forward steps in `mode`."""
    window = _forward_steps(rows, mode)[-WINDOW:]
    samples = [row.chunk_words / dwell for row, dwell in _kept_dwells(window)]
    return statistics.median(samples) if len(samples) >= MIN_SAMPLES else None


def active_seconds(rows: Iterable[LogRow], mode: str, since: float) -> float:
    """Reading time in `mode` after `since`: the kept dwells only."""
    steps = _forward_steps(rows, mode)
    return sum(dwell for row, dwell in _kept_dwells(steps) if row.ts > since)
