"""Cross-platform key input (spec §8.3): thin wrapper over readchar."""

import readchar


def read_key() -> str:
    """Block for one key press; Ctrl+C raises KeyboardInterrupt."""
    return readchar.readkey()
