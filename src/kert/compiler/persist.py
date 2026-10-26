from collections.abc import Mapping, Sequence
from pathlib import Path

from kert.common.model import Block, Sentence


def write_book(
    path: Path,
    meta: Mapping[str, str],
    blocks: Sequence[Block],
    sentences: Sequence[Sentence],
) -> None:
    raise NotImplementedError
