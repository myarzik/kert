"""Cross-platform key input (spec §8.3): thin wrapper over readchar."""

from collections.abc import Callable

import readchar

ESC_TIMEOUT = 0.05


def parse_key(read: Callable[[float | None], bytes]) -> str:
    raise NotImplementedError


def read_key() -> str:
    """Block for one key press; Ctrl+C raises KeyboardInterrupt."""
    return readchar.readkey()
