"""Reader session lifecycle and the `Live`/readkey loop (spec §5, §7.1, §8.3).

`open_session`, `feed` and `close_session` hold all persistence and are tested;
`run` is the thin, untested terminal glue around them.
"""

import time
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

from kert.reader import config
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
        book = Book(store.blocks, store.sentences, int(store.meta["word_count"]))
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
            case Advance(sentence_id=sentence_id, chunk_words=words, direction=d):
                store.log_advance(now(), sentence_id, words, d)
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
    read_key: Callable[[], str] | None = None,
    console: object | None = None,
    config_file: Path | None = None,
) -> None:
    from rich.console import Console
    from rich.live import Live

    from kert.reader.keys import read_key
    from kert.reader.render import build_frame

    console = Console()

    def size() -> tuple[int, int]:
        return console.size.width, console.size.height

    store, state = open_session(path, size=size())
    try:
        with Live(
            build_frame(state), console=console, screen=True, auto_refresh=False
        ) as live:
            while not state.quit:
                try:
                    key = read_key()
                except KeyboardInterrupt:  # Ctrl+C = quit with save (§8.3)
                    break
                state = feed(store, replace(state, size=size()), key)
                live.update(build_frame(state), refresh=True)
    finally:
        close_session(store, state)
