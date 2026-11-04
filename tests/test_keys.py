"""POSIX key parsing with an Esc timeout (spec §8.3 amendment)."""

import pytest
from readchar import key

from kert.reader.keys import ESC_TIMEOUT, parse_key

PAUSE = object()  # no byte arrives within any timeout


class Source:
    """Scripted terminal: bytes as typed, PAUSE where the user stops typing."""

    def __init__(self, *items):
        self.items = []
        for item in items:
            self.items += [item] if item is PAUSE else [bytes([b]) for b in item]
        self.timeouts = []

    def read(self, timeout):
        self.timeouts.append(timeout)
        while self.items:
            item = self.items.pop(0)
            if item is not PAUSE:
                return item
            if timeout is not None:
                return b""  # the timeout ran out during the pause
        assert timeout is not None, "blocking read past the end of the script"
        return b""


def keys_of(source, count):
    return [parse_key(source.read) for _ in range(count)]


def test_plain_keys():
    assert keys_of(Source(b"j q"), 3) == ["j", " ", "q"]


def test_lone_esc_returns_after_the_timeout():
    source = Source(b"\x1b", PAUSE, b"q")

    assert keys_of(source, 2) == [key.ESC, "q"]
    assert source.timeouts[1] == ESC_TIMEOUT
    assert ESC_TIMEOUT == 0.05


def test_only_the_byte_after_esc_is_timed():
    source = Source(b"ab")

    keys_of(source, 2)
    assert source.timeouts == [None, None]


@pytest.mark.parametrize(
    ("typed", "expected"),
    [
        (key.UP, key.UP),
        (key.LEFT, key.LEFT),
        (key.F5, key.F5),
        (key.DELETE, key.DELETE),
        ("\x1bOP", "\x1bOP"),  # SS3 form of F1
    ],
)
def test_escape_sequences_arrive_whole(typed, expected):
    assert parse_key(Source(typed.encode()).read) == expected


def test_a_key_typed_right_after_a_sequence_is_its_own_key():
    assert keys_of(Source(key.UP.encode() + b"j"), 2) == [key.UP, "j"]


def test_esc_followed_at_once_by_a_key_is_one_alt_key():
    assert parse_key(Source(b"\x1bx").read) == "\x1bx"


def test_utf8_is_decoded_to_one_character():
    assert keys_of(Source("дё".encode()), 2) == ["д", "ё"]


@pytest.mark.parametrize("typed", [b"\n", b"\x7f", b"\x08"])
def test_control_keys_pass_through(typed):
    assert parse_key(Source(typed).read) == typed.decode()


def test_enter_matches_readchar():
    assert parse_key(Source(b"\n").read) == key.ENTER


def test_ctrl_c_byte_raises_keyboard_interrupt():
    with pytest.raises(KeyboardInterrupt):
        parse_key(Source(b"\x03").read)
