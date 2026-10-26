import re
import unicodedata
from dataclasses import dataclass

from kert.common.model import BlockType, Lang

_SOFT_HYPHEN = "\u00ad"
_NO_BREAK_SPACES = str.maketrans({"\u00a0": " ", "\u202f": " "})
_WHITESPACE_RUN = re.compile(r"\s+")
# A hyphen or en-dash that is paragraph-initial or preceded by a space, and
# followed by a space (spec §4.2, RU only).
_RU_SPACED_DASH = re.compile(r"(?:^|(?<= ))[-–](?= )")


@dataclass(frozen=True, slots=True)
class NormalizedBlock:
    type: BlockType
    text: str


def normalize_paragraph(text: str, lang: Lang) -> str:
    text = unicodedata.normalize("NFC", text)
    text = text.replace(_SOFT_HYPHEN, "").translate(_NO_BREAK_SPACES)
    text = _WHITESPACE_RUN.sub(" ", text).strip()
    if lang == "ru":
        text = _RU_SPACED_DASH.sub("—", text)
    return text


def block_type(text: str) -> BlockType:
    return "dialogue" if text.startswith("— ") else "paragraph"


def normalize(paragraphs: list[str], lang: Lang) -> list[NormalizedBlock]:
    blocks = []
    for paragraph in paragraphs:
        text = normalize_paragraph(paragraph, lang)
        if text:
            blocks.append(NormalizedBlock(type=block_type(text), text=text))
    return blocks
