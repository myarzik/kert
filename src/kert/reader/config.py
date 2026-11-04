"""Reader settings: per-book reader_state > user TOML > hardcoded (spec §8.4).

Each key resolves independently; an invalid value at one layer falls through
to the next (SPEC_NOTES, Task 8). The TOML stores preferences only.
"""

import re
import sys
import tomllib
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Protocol

import platformdirs.unix
import platformdirs.windows

from kert.common.errors import KertError

THEMES = ("dark", "light")
MODES = ("chunk", "sentence", "paragraph")
WIDTH_MIN, WIDTH_MAX = 5, 12
GOAL_MAX = {"m": 600, "w": 100_000}  # §17.6: minutes / words


@dataclass(frozen=True, slots=True)
class Settings:
    chunk_width: int
    theme: str
    mode: str = "chunk"  # §17.2: per book only, never in the TOML
    default_goal: str | None = None  # §17.6: TOML only
    recap: bool = True  # §17.7
    recap_words: int = 40
    recall: bool = True
    recall_gap_minutes: int = 60


HARDCODED = Settings(chunk_width=8, theme="dark")


class SettingsStore(Protocol):
    def load_setting(self, key: str) -> str | None: ...

    def save_setting(self, key: str, value: str) -> None: ...


def config_path() -> Path:
    # Spec §8.4 names ~/.config on macOS too, so use XDG rules off Windows.
    if sys.platform == "win32":
        dirs = platformdirs.windows.Windows("kert", appauthor=False, roaming=True)
    else:
        dirs = platformdirs.unix.Unix("kert")
    return dirs.user_config_path / "config.toml"


def _int_range(low: int, high: int) -> Callable[[object], int | None]:
    def parse(value: object) -> int | None:
        return value if type(value) is int and low <= value <= high else None

    return parse


def _choice(options: tuple[str, ...]) -> Callable[[object], str | None]:
    return lambda value: value if value in options else None


def _switch(value: object) -> bool | None:
    return {"on": True, "off": False}.get(value) if isinstance(value, str) else None


# Settings key -> (parser of a typed value, what a valid value is, TOML layer).
# Keys are the Settings field names and the reader_state keys (§8.4, §17.10).
_KEYS: dict[str, tuple[Callable[[object], object], str, bool]] = {
    "chunk_width": (
        _int_range(WIDTH_MIN, WIDTH_MAX),
        f"an integer {WIDTH_MIN}..{WIDTH_MAX}",
        True,
    ),
    "theme": (_choice(THEMES), f"one of {', '.join(THEMES)}", True),
    # §17.2: an experimental condition, kept out of the TOML.
    "mode": (_choice(MODES), f"one of {', '.join(MODES)}", False),
    "recap": (_switch, "on or off", True),
    "recap_words": (_int_range(10, 120), "an integer 10..120", True),
    "recall": (_switch, "on or off", True),
    "recall_gap_minutes": (_int_range(5, 1440), "an integer 5..1440", True),
}
_INT_KEYS = {"chunk_width", "recap_words", "recall_gap_minutes"}


def parse_goal(raw: object) -> tuple[int, str] | None:
    """`"15m"` -> (15, "m"); None unless N is in 1..GOAL_MAX for its unit."""
    match = re.fullmatch(r"(\d+)([mw])", raw) if isinstance(raw, str) else None
    if match is None:
        return None
    amount, unit = int(match[1]), match[2]
    return (amount, unit) if 1 <= amount <= GOAL_MAX[unit] else None


def _from_text(key: str, raw: str | None) -> object:
    """A reader_state or `:set` text as the setting's value, None if invalid."""
    if raw is None:
        return None
    value: object = raw
    if key in _INT_KEYS:
        try:
            value = int(raw)
        except ValueError:
            return None
    return _KEYS[key][0](value)


def load_global(path: Path | None = None) -> Settings:
    """TOML layer over hardcoded defaults; never raises on config errors."""
    try:
        with (path or config_path()).open("rb") as f:
            data = tomllib.load(f)
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError):
        return HARDCODED
    values = {}
    for key, (parse, _, in_toml) in _KEYS.items():
        if in_toml and (value := parse(data.get(key))) is not None:
            values[key] = value
    goal = data.get("default_goal")
    if parse_goal(goal):
        values["default_goal"] = goal
    return replace(HARDCODED, **values)


def resolve(book: SettingsStore, defaults: Settings) -> Settings:
    """Per-book reader_state over `defaults` (the loaded global layer)."""
    values = {}
    for key in _KEYS:
        if (value := _from_text(key, book.load_setting(key))) is not None:
            values[key] = value
    return replace(defaults, **values)


def validate(key: str, raw: str) -> str:
    """Normalized storage value for `key`, or KertError if it is invalid."""
    if key not in _KEYS:
        raise KertError(f"Unknown setting {key!r}.")
    value = _from_text(key, raw)
    if value is None:
        raise KertError(f"{key} must be {_KEYS[key][1]}, got {raw!r}.")
    return str(value) if key in _INT_KEYS else raw


def _toml_value(value: object) -> str:
    if isinstance(value, bool):
        return '"on"' if value else '"off"'
    return str(value) if isinstance(value, int) else f'"{value}"'


def set_setting(
    book: SettingsStore, key: str, raw: str, path: Path | None = None
) -> None:
    """Validate, then write `key` to the book and, for TOML keys, the global TOML."""
    value = validate(key, raw)
    book.save_setting(key, value)
    if not _KEYS[key][2]:
        return

    path = path or config_path()
    updated = replace(load_global(path), **{key: _from_text(key, value)})
    lines = [
        f"{name} = {_toml_value(getattr(updated, name))}"
        for name, (_, _, in_toml) in _KEYS.items()
        if in_toml
    ]
    if updated.default_goal:
        lines.append(f'default_goal = "{updated.default_goal}"')
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    except OSError:
        pass  # never crash on config errors (§8.4); the book layer is saved
