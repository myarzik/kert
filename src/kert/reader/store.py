from dataclasses import dataclass
from pathlib import Path
from typing import Self


@dataclass(frozen=True, slots=True)
class Position:
    sentence_id: int
    chunk_start_token: int


class BookStore:
    @classmethod
    def open(cls, path: Path) -> Self:
        raise NotImplementedError

    def load_position(self) -> Position:
        raise NotImplementedError

    def save_position(self, position: Position) -> None:
        raise NotImplementedError

    def load_setting(self, key: str) -> str | None:
        raise NotImplementedError

    def save_setting(self, key: str, value: str) -> None:
        raise NotImplementedError

    def close(self) -> None:
        raise NotImplementedError

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()
