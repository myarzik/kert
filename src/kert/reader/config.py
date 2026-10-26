from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True, slots=True)
class Settings:
    chunk_width: int
    theme: str


HARDCODED = Settings(chunk_width=8, theme="dark")


class SettingsStore(Protocol):
    def load_setting(self, key: str) -> str | None: ...

    def save_setting(self, key: str, value: str) -> None: ...


def config_path() -> Path:
    raise NotImplementedError


def load_global(path: Path | None = None) -> Settings:
    raise NotImplementedError


def resolve(book: SettingsStore, defaults: Settings) -> Settings:
    raise NotImplementedError


def set_setting(
    book: SettingsStore, key: str, raw: str, path: Path | None = None
) -> None:
    raise NotImplementedError
