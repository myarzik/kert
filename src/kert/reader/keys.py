"""Cross-platform key input (spec §8.3).

Windows uses readchar.readkey (msvcrt reports Esc at once). On POSIX this
module reads bytes itself (§8.3 amendment): readchar 4.2.2 returns a lone Esc
only with the next key and flushes typed-ahead input on every key.
`parse_key` is the pure part; `_read_posix` is the thin termios glue.
"""

import codecs
import os
import sys
from collections.abc import Callable

import readchar

ESC_TIMEOUT = 0.05  # seconds to wait for the rest of an escape sequence

Read = Callable[[float | None], bytes]  # one byte; b"" when the timeout runs out


def _char(first: bytes, read: Read) -> str:
    """One character, reading the continuation bytes of multi-byte UTF-8."""
    decoder = codecs.getincrementaldecoder("utf-8")("replace")
    text = decoder.decode(first)
    while not text:
        more = read(None)
        if not more:
            return decoder.decode(b"", final=True)
        text = decoder.decode(more)
    return text


def parse_key(read: Read) -> str:
    """One key as readchar spells it, from a byte source with timeouts."""
    first = read(None)
    if first == b"\x03":
        raise KeyboardInterrupt
    if first != b"\x1b":
        return _char(first, read)
    second = read(ESC_TIMEOUT)
    if not second:
        return readchar.key.ESC
    if second == b"[":  # CSI: parameter bytes, then a final byte in @..~
        sequence = b"\x1b["
        while byte := read(ESC_TIMEOUT):
            sequence += byte
            if 0x40 <= byte[0] <= 0x7E:
                break
        return sequence.decode("ascii", "replace")
    if second == b"O":  # SS3: exactly one more byte
        return "\x1bO" + read(ESC_TIMEOUT).decode("ascii", "replace")
    return "\x1b" + _char(second, read)  # Alt+key


def _read_posix() -> str:
    import select
    import termios

    fd = sys.stdin.fileno()
    saved = termios.tcgetattr(fd)
    mode = termios.tcgetattr(fd)
    mode[3] &= ~(termios.ICANON | termios.ECHO)  # ISIG kept: Ctrl+C is SIGINT
    mode[6][termios.VMIN], mode[6][termios.VTIME] = 1, 0
    termios.tcsetattr(fd, termios.TCSANOW, mode)  # TCSANOW: never flush input

    def read(timeout: float | None) -> bytes:
        if timeout is not None and not select.select([fd], [], [], timeout)[0]:
            return b""
        return os.read(fd, 1)

    try:
        return parse_key(read)
    finally:
        termios.tcsetattr(fd, termios.TCSANOW, saved)


def read_key() -> str:
    """Block for one key press; Ctrl+C raises KeyboardInterrupt."""
    if sys.platform == "win32":
        return readchar.readkey()
    return _read_posix()
