from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Protocol, runtime_checkable

from kert.common.errors import KertError

RawKind = Literal["paragraph", "heading", "code", "list_item"]


class IngestError(KertError):
    pass


@dataclass(frozen=True, slots=True)
class RawBlock:
    kind: RawKind
    text: str
    level: int | None = None


@dataclass(frozen=True, slots=True)
class IngestResult:
    blocks: list[RawBlock] = field(default_factory=list)
    title: str | None = None


@runtime_checkable
class Ingester(Protocol):
    def ingest(self, path: Path) -> IngestResult: ...


def ingester_for(path: Path, lang: str) -> tuple[Ingester, str]:
    raise NotImplementedError
