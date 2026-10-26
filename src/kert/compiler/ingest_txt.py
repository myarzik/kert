from pathlib import Path
from typing import Protocol, runtime_checkable

from kert.common.model import Lang


class IngestError(Exception):
    pass


@runtime_checkable
class Ingester(Protocol):
    def ingest(self, path: Path) -> list[str]: ...


class TxtIngester:
    def __init__(self, lang: Lang) -> None:
        self.lang = lang

    def ingest(self, path: Path) -> list[str]:
        raise NotImplementedError
