import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass

from kert.common.model import BlockType, Lang
from kert.compiler.ingest import RawBlock

_SOFT_HYPHEN = "\u00ad"
_NO_BREAK_SPACES = str.maketrans({"\u00a0": " ", "\u202f": " "})
_WHITESPACE_RUN = re.compile(r"\s+")
# A hyphen or en-dash that is paragraph-initial or preceded by a space, and
# followed by a space (spec §4.2, RU only).
_RU_SPACED_DASH = re.compile(r"(?:^|(?<= ))[-–](?= )")
_TRAILING_BLANK_LINES = re.compile(r"(?:\n[ \t]*)+\Z")


@dataclass(frozen=True, slots=True)
class NormalizedBlock:
    type: BlockType
    text: str
    chapter: int | None = None


def normalize_paragraph(text: str, lang: Lang) -> str:
    text = unicodedata.normalize("NFC", text)
    text = text.replace(_SOFT_HYPHEN, "").translate(_NO_BREAK_SPACES)
    text = _WHITESPACE_RUN.sub(" ", text).strip()
    if lang == "ru":
        text = _RU_SPACED_DASH.sub("—", text)
    return text


def block_type(text: str) -> BlockType:
    return "dialogue" if text.startswith("— ") else "paragraph"


def normalize_code(text: str) -> str:
    """Code keeps its layout: NFC and newline unification only (§14.2)."""
    text = unicodedata.normalize("NFC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return _TRAILING_BLANK_LINES.sub("", text)


def normalize(raw: Sequence[RawBlock], lang: Lang) -> list[NormalizedBlock]:
    kept: list[tuple[RawBlock, str]] = []
    for block in raw:
        if block.kind == "code":
            text = normalize_code(block.text)
            if not text.strip():
                continue
        else:
            text = normalize_paragraph(block.text, lang)
            if not text:
                continue
        kept.append((block, text))

    # §14.2: each heading of the smallest present level starts a chapter.
    levels = [b.level or 1 for b, _ in kept if b.kind == "heading"]
    top = min(levels, default=None)
    chapter = None
    blocks = []
    for block, text in kept:
        if block.kind == "heading" and (block.level or 1) == top:
            chapter = (chapter or 0) + 1
        kind = block_type(text) if block.kind == "paragraph" else block.kind
        blocks.append(NormalizedBlock(type=kind, text=text, chapter=chapter))
    return blocks
