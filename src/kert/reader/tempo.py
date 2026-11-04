"""Reading tempo and active time from advance_log rows (spec §17.6)."""

from typing import NamedTuple


class LogRow(NamedTuple):
    ts: float
    chunk_words: int
    direction: int
    kind: str
    mode: str


def tempo_wps(rows, mode: str) -> float | None:
    raise NotImplementedError


def active_seconds(rows, mode: str, since: float) -> float:
    raise NotImplementedError
