from dataclasses import dataclass
from pathlib import Path

from kert.common.model import Lang


@dataclass(frozen=True, slots=True)
class CompileSummary:
    blocks: int
    sentences: int
    candidates_per_sentence: float
    elapsed: float


def compile_book(
    input_path: Path, output_path: Path, lang: Lang, *, force: bool = False
) -> CompileSummary:
    raise NotImplementedError
