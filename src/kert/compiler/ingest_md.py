"""Markdown adapter: CommonMark via markdown-it-py (spec §14.4)."""

import re
from pathlib import Path

from markdown_it import MarkdownIt
from markdown_it.token import Token

from kert.common.model import Lang
from kert.compiler.ingest import IngestResult, RawBlock, decode_text

# YAML front matter: `---` on the first line up to the next `---` line.
_FRONT_MATTER = re.compile(r"\A---[ \t]*\n.*?\n---[ \t]*(?:\n|\Z)", re.DOTALL)


class MarkdownIngester:
    def __init__(self, lang: Lang) -> None:
        self.lang = lang
        # Tables are enabled only so that they parse as tables and get skipped.
        self._md = MarkdownIt("commonmark").enable(["table", "strikethrough"])

    def ingest(self, path: Path) -> IngestResult:
        text = decode_text(path.read_bytes(), path, self.lang)
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        text = _FRONT_MATTER.sub("", text, count=1)
        return IngestResult(blocks=_blocks(self._md.parse(text)))


def _blocks(tokens: list[Token]) -> list[RawBlock]:
    blocks: list[RawBlock] = []
    lists: list[list[int | None]] = []  # per open list: [next number] (None = bullet)
    prefix: str | None = None  # pending prefix for an item's first paragraph
    in_item = 0
    for i, token in enumerate(tokens):
        match token.type:
            case "heading_open":
                level = int(token.tag[1])
                blocks.append(RawBlock("heading", _inline(tokens[i + 1]), level=level))
            case "bullet_list_open":
                lists.append([None])
            case "ordered_list_open":
                lists.append([int(token.attrs.get("start", 1))])
            case "bullet_list_close" | "ordered_list_close":
                lists.pop()
            case "list_item_open":
                in_item += 1
                counter = lists[-1]
                if counter[0] is None:
                    prefix = "• "
                else:
                    prefix = f"{counter[0]}. "
                    counter[0] += 1
            case "list_item_close":
                in_item -= 1
                prefix = None
            case "paragraph_open":
                text = _inline(tokens[i + 1])
                if in_item:
                    blocks.append(RawBlock("list_item", (prefix or "") + text))
                    prefix = None
                else:
                    blocks.append(RawBlock("paragraph", text))
            case "fence" | "code_block":
                blocks.append(RawBlock("code", token.content))
    return blocks


def _inline(token: Token) -> str:
    """Plain text of an inline token: markup dropped, breaks become spaces."""
    parts = []
    for child in token.children or []:
        match child.type:
            case "text" | "code_inline" | "image":
                parts.append(child.content)
            case "softbreak" | "hardbreak":
                parts.append(" ")
    return "".join(parts)
