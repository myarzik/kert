import time
from collections.abc import Callable
from pathlib import Path

from kert.reader.state import ReaderState
from kert.reader.store import BookStore

ADVANCE_LOG_CAP = 10_000


def open_session(
    path: Path, size: tuple[int, int] = (80, 24), config_file: Path | None = None
) -> tuple[BookStore, ReaderState]:
    raise NotImplementedError


def feed(
    store: BookStore,
    state: ReaderState,
    key: str,
    *,
    config_file: Path | None = None,
    now: Callable[[], float] = time.time,
) -> ReaderState:
    raise NotImplementedError


def close_session(store: BookStore, state: ReaderState) -> None:
    raise NotImplementedError
