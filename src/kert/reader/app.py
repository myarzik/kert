"""Reader session lifecycle and the `Live`/readkey loop (spec §5, §7.1, §8.3).

`open_session`, `feed` and `close_session` hold all persistence; `run` is the
thin `Live`/readkey loop around them (keys and console injectable for tests).
"""

import time
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

from rich.console import Console
from rich.live import Live

from kert.common.errors import KertError
from kert.reader import config, keys
from kert.reader.render import build_frame
from kert.reader.state import (
    Advance,
    Book,
    ReaderState,
    SaveSetting,
    handle_key,
    initial_state,
)
from kert.reader.store import BookStore

ADVANCE_LOG_CAP = 10_000


def open_session(
    path: Path, size: tuple[int, int] = (80, 24), config_file: Path | None = None
) -> tuple[BookStore, ReaderState]:
    store = BookStore.open(path)
    try:
        if not store.sentences:
            raise KertError(f"{path} has no text to read.")
        try:
            word_count = int(store.meta["word_count"])
        except (KeyError, ValueError):
            raise KertError(
                f"{path} is not a valid .kert file (bad meta word_count)."
            ) from None
        book = Book(store.blocks, store.sentences, word_count)
        settings = config.resolve(store, config.load_global(config_file))
        state = initial_state(book, settings, store.load_position(), size=size)
    except BaseException:
        store.close()
        raise
    return store, state


def feed(
    store: BookStore,
    state: ReaderState,
    key: str,
    *,
    config_file: Path | None = None,
    now: Callable[[], float] = time.time,
) -> ReaderState:
    """Apply one key and execute the effects it produced."""
    state = handle_key(state, key)
    for effect in state.effects:
        match effect:
            case Advance(sentence_id=sid, chunk_words=words, direction=d, kind=k):
                store.log_advance(
                    now(), sid, words, d, kind=k, mode=state.settings.mode
                )
            case SaveSetting(key=name, value=value):
                config.set_setting(store, name, value, config_file)
    return state


def close_session(store: BookStore, state: ReaderState) -> None:
    """Persist position, cap advance_log, checkpoint and close (§5 on exit)."""
    try:
        store.save_position(state.position)
        store.trim_advance_log(ADVANCE_LOG_CAP)
    finally:
        store.close()


def run(
    path: Path,
    *,
    read_key: Callable[[], str] = keys.read_key,
    console: Console | None = None,
    config_file: Path | None = None,
) -> None:
    console = console or Console()

    def size() -> tuple[int, int]:
        return console.size.width, console.size.height

    store, state = open_session(path, size=size(), config_file=config_file)
    try:
        with Live(
            build_frame(state), console=console, screen=True, auto_refresh=False
        ) as live:
            while not state.quit:
                key = read_key()
                state = feed(
                    store, replace(state, size=size()), key, config_file=config_file
                )
                live.update(build_frame(state), refresh=True)
    except KeyboardInterrupt:  # Ctrl+C = quit with save (§5, §8.3)
        pass
    finally:
        close_session(store, state)
