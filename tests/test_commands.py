import pytest

from kert.common.errors import KertError
from kert.reader.commands import GotoCommand, QuitCommand, SetCommand, parse_command


@pytest.mark.parametrize(
    ("text", "command"),
    [
        ("set width=6", SetCommand("chunk_width", "6")),
        ("set width=12", SetCommand("chunk_width", "12")),
        ("set theme=light", SetCommand("theme", "light")),
        ("set theme=dark", SetCommand("theme", "dark")),
        ("  set  width = 7 ", SetCommand("chunk_width", "7")),
        ("goto 50", GotoCommand(50.0)),
        ("goto 0", GotoCommand(0.0)),
        ("goto 100", GotoCommand(100.0)),
        ("goto 12.5", GotoCommand(12.5)),
        ("q", QuitCommand()),
    ],
)
def test_parse_valid_commands(text, command):
    assert parse_command(text) == command


@pytest.mark.parametrize(
    "text",
    [
        "",
        "foo",
        "set",
        "set width",
        "set width=4",
        "set width=13",
        "set width=abc",
        "set theme=blue",
        "set position=1",
        "goto",
        "goto abc",
        "goto -1",
        "goto 100.1",
        "goto nan",
        "goto 5 6",
        "q now",
    ],
)
def test_parse_invalid_commands_raise_user_error(text):
    with pytest.raises(KertError):
        parse_command(text)
