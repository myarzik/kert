from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Protocol, runtime_checkable

from kert.common.errors import KertError
from kert.common.model import Lang

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


def decode_text(data: bytes, path: Path, lang: Lang) -> str:
    """§4.1 decoding chain: UTF-8 (BOM stripped), then cp1251 for RU."""
    # utf-8-sig decodes plain UTF-8 identically and also strips a BOM.
    encodings = ["utf-8-sig"] + (["cp1251"] if lang == "ru" else [])
    for encoding in encodings:
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise IngestError(
        f"Cannot decode {path} as {' or '.join(encodings)}. "
        "Convert the file to UTF-8 (an --encoding flag is planned)."
    )


SUPPORTED_SUFFIXES = (".txt", ".md", ".markdown")


def ingester_for(path: Path, lang: Lang) -> tuple[Ingester, str]:
    """Pick the ingester and `meta.source_format` by input suffix (§14.1)."""
    # Imported here: the ingester modules import this one.
    from kert.compiler.ingest_md import MarkdownIngester
    from kert.compiler.ingest_txt import TxtIngester

    suffix = path.suffix.lower()
    if suffix == ".txt":
        return TxtIngester(lang), "txt"
    if suffix in (".md", ".markdown"):
        return MarkdownIngester(lang), "md"
    raise IngestError(
        f"Unsupported input format {suffix or '(no suffix)'!r} for {path}; "
        f"supported: {', '.join(SUPPORTED_SUFFIXES)}."
    )
