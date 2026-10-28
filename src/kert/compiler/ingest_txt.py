import re
from pathlib import Path

from kert.common.model import Lang
from kert.compiler.ingest import IngestError, IngestResult, RawBlock

_BLANK_LINE = re.compile(r"^\s*$")


class TxtIngester:
    """Plain-text adapter: paragraphs are separated by blank lines (spec §4.1)."""

    def __init__(self, lang: Lang) -> None:
        self.lang = lang

    def ingest(self, path: Path) -> IngestResult:
        text = self._decode(path.read_bytes(), path)
        paragraphs: list[str] = []
        current: list[str] = []
        for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
            if _BLANK_LINE.match(line):
                if current:
                    paragraphs.append(" ".join(current))
                    current = []
            else:
                current.append(line)
        if current:
            paragraphs.append(" ".join(current))
        return IngestResult(blocks=[RawBlock("paragraph", p) for p in paragraphs])

    def _decode(self, data: bytes, path: Path) -> str:
        # utf-8-sig decodes plain UTF-8 identically and also strips a BOM.
        encodings = ["utf-8-sig"] + (["cp1251"] if self.lang == "ru" else [])
        for encoding in encodings:
            try:
                return data.decode(encoding)
            except UnicodeDecodeError:
                continue
        raise IngestError(
            f"Cannot decode {path} as {' or '.join(encodings)}. "
            "Convert the file to UTF-8 (an --encoding flag is planned)."
        )
