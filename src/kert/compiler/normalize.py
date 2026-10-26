from dataclasses import dataclass

from kert.common.model import BlockType, Lang


@dataclass(frozen=True, slots=True)
class NormalizedBlock:
    type: BlockType
    text: str


def normalize_paragraph(text: str, lang: Lang) -> str:
    raise NotImplementedError


def block_type(text: str) -> BlockType:
    raise NotImplementedError


def normalize(paragraphs: list[str], lang: Lang) -> list[NormalizedBlock]:
    raise NotImplementedError
