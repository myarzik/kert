"""Reader settings: per-book reader_state > user TOML > hardcoded (spec §8.4).

Each key resolves independently; an invalid value at one layer falls through
to the next (SPEC_NOTES, Task 8). The TOML stores preferences only.
"""

import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import platformdirs.unix
import platformdirs.windows

from kert.common.errors import KertError

THEMES = ("dark", "light")
MODES = ("chunk", "sentence", "paragraph")
WIDTH_MIN, WIDTH_MAX = 5, 12


@dataclass(frozen=True, slots=True)
class Settings:
    chunk_width: int
    theme: str
    mode: str = "chunk"  # §17.2: per book only, never in the TOML


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


def _valid_width(value: object) -> int | None:
    if type(value) is int and WIDTH_MIN <= value <= WIDTH_MAX:
        return value
    return None


def _valid_theme(value: object) -> str | None:
    return value if value in THEMES else None


def _valid_mode(value: object) -> str | None:
    return value if value in MODES else None


def load_global(path: Path | None = None) -> Settings:
    """TOML layer over hardcoded defaults; never raises on config errors."""
    try:
        with (path or config_path()).open("rb") as f:
            data = tomllib.load(f)
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError):
        return HARDCODED
    width = _valid_width(data.get("chunk_width"))
    theme = _valid_theme(data.get("theme"))
    return Settings(
        chunk_width=HARDCODED.chunk_width if width is None else width,
        theme=theme or HARDCODED.theme,
    )


def _parse_width(raw: str | None) -> int | None:
    try:
        return None if raw is None else _valid_width(int(raw))
    except ValueError:
        return None


def resolve(book: SettingsStore, defaults: Settings) -> Settings:
    """Per-book reader_state over `defaults` (the loaded global layer)."""
    width = _parse_width(book.load_setting("chunk_width"))
    theme = _valid_theme(book.load_setting("theme"))
    mode = _valid_mode(book.load_setting("mode"))
    return Settings(
        chunk_width=defaults.chunk_width if width is None else width,
        theme=theme or defaults.theme,
        mode=mode or HARDCODED.mode,  # §17.2: never from the TOML
    )


def validate(key: str, raw: str) -> str:
    """Normalized storage value for `key`, or KertError if it is invalid."""
    if key == "chunk_width":
        width = _parse_width(raw)
        if width is None:
            raise KertError(
                f"chunk_width must be an integer {WIDTH_MIN}..{WIDTH_MAX}, got {raw!r}."
            )
        return str(width)
    if key == "theme":
        if _valid_theme(raw) is None:
            raise KertError(f"theme must be one of {', '.join(THEMES)}, got {raw!r}.")
        return raw
    if key == "mode":
        if _valid_mode(raw) is None:
            raise KertError(f"mode must be one of {', '.join(MODES)}, got {raw!r}.")
        return raw
    raise KertError(f"Unknown setting {key!r}.")


def set_setting(
    book: SettingsStore, key: str, raw: str, path: Path | None = None
) -> None:
    """Validate, then write `key` to the book and to the global TOML."""
    value = validate(key, raw)
    book.save_setting(key, value)
    if key == "mode":
        return  # §17.2: an experimental condition, kept out of the TOML

    path = path or config_path()
    current = load_global(path)
    width = int(value) if key == "chunk_width" else current.chunk_width
    theme = value if key == "theme" else current.theme
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f'chunk_width = {width}\ntheme = "{theme}"\n', encoding="utf-8")
    except OSError:
        pass  # never crash on config errors (§8.4); the book layer is saved
