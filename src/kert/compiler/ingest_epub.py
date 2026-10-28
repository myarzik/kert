from pathlib import Path

from kert.common.model import Lang
from kert.compiler.ingest import IngestResult


class EpubIngester:
    def __init__(self, lang: Lang) -> None:
        self.lang = lang

    def ingest(self, path: Path) -> IngestResult:
        raise NotImplementedError
