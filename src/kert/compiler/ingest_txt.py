import re
from pathlib import Path

from kert.common.model import Lang
from kert.compiler.ingest import IngestResult, RawBlock, decode_text

_BLANK_LINE = re.compile(r"^\s*$")


class TxtIngester:
    """Plain-text adapter: paragraphs are separated by blank lines (spec §4.1)."""

    def __init__(self, lang: Lang) -> None:
        self.lang = lang

    def ingest(self, path: Path) -> IngestResult:
        text = decode_text(path.read_bytes(), path, self.lang)
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
