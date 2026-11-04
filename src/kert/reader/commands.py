"""`:` command-line parser (spec §8.2). Values are validated, not applied."""

import math
from dataclasses import dataclass

from kert.common.errors import KertError
from kert.reader import config


@dataclass(frozen=True, slots=True)
class SetCommand:
    key: str  # storage key (§3 reader_state), e.g. "chunk_width"
    value: str


@dataclass(frozen=True, slots=True)
class GotoCommand:
    percent: float


@dataclass(frozen=True, slots=True)
class QuitCommand:
    pass


@dataclass(frozen=True, slots=True)
class GoalCommand:
    action: str  # "arm", "off" or "again"
    amount: int = 0
    unit: str = ""  # "m" minutes, "w" words


Command = SetCommand | GotoCommand | QuitCommand | GoalCommand

_SET_KEYS = {"width": "chunk_width", "theme": "theme", "mode": "mode"}


def parse_command(text: str) -> Command:
    name, _, arg = text.strip().partition(" ")
    arg = arg.strip()
    if name == "q" and not arg:
        return QuitCommand()
    if name == "set":
        return _parse_set(arg)
    if name == "goto":
        return _parse_goto(arg)
    if name == "goal":
        return _parse_goal(arg)
    raise KertError(f"Unknown command: {text.strip()}")


def _parse_set(arg: str) -> SetCommand:
    name, eq, raw = arg.partition("=")
    if not eq:
        raise KertError(
            "Usage: :set width=N | theme=dark|light | mode=chunk|sentence|paragraph"
        )
    key = _SET_KEYS.get(name.strip())
    if key is None:
        raise KertError(f"Unknown setting: {name.strip()}")
    return SetCommand(key, config.validate(key, raw.strip()))


def _parse_goto(arg: str) -> GotoCommand:
    try:
        percent = float(arg)
    except ValueError:
        raise KertError("Usage: :goto P (percent 0-100)") from None
    if not (math.isfinite(percent) and 0.0 <= percent <= 100.0):
        raise KertError("Usage: :goto P (percent 0-100)")
    return GotoCommand(percent)


def _parse_goal(arg: str) -> GoalCommand:
    if arg in ("off", "again"):
        return GoalCommand(arg)
    goal = config.parse_goal(arg)
    if goal is None:
        raise KertError("Usage: :goal Nm | Nw | off | again (1-600 m, 1-100000 w)")
    return GoalCommand("arm", *goal)
