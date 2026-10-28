"""FictionBook 2 adapter: `.fb2` and `.fb2.zip` via xml.etree (spec §14.5)."""

import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from kert.common.model import Lang
from kert.compiler.ingest import IngestError, IngestResult, RawBlock

_NS = "{http://www.gribuser.ru/xml/fictionbook/2.0}"
_MAX_LEVEL = 6
# Containers walked at the current section depth.
_CONTAINERS = {"epigraph", "cite", "annotation", "stanza"}
_PARAGRAPHS = {"p", "v", "text-author"}


class Fb2Ingester:
    def __init__(self, lang: Lang) -> None:
        self.lang = lang

    def ingest(self, path: Path) -> IngestResult:
        try:
            # The XML parser honors the encoding declaration (windows-1251 too).
            root = ET.fromstring(_read(path))
        except ET.ParseError as exc:
            raise IngestError(f"{path} is not valid FB2 XML ({exc}).") from None
        body = next((b for b in root.iter(f"{_NS}body") if b.get("name") is None), None)
        if body is None:
            raise IngestError(f"{path} has no FB2 <body>.")
        blocks: list[RawBlock] = []
        _walk(body, depth=0, out=blocks)
        title = root.findtext(f"{_NS}description/{_NS}title-info/{_NS}book-title")
        return IngestResult(blocks=blocks, title=(title or "").strip() or None)


def _read(path: Path) -> bytes:
    if not path.name.lower().endswith(".zip"):
        return path.read_bytes()
    try:
        with zipfile.ZipFile(path) as archive:
            members = [n for n in archive.namelist() if n.lower().endswith(".fb2")]
            if len(members) != 1:
                raise IngestError(
                    f"{path} must contain exactly one .fb2 file, found {len(members)}."
                )
            return archive.read(members[0])
    except zipfile.BadZipFile:
        raise IngestError(f"{path} is not a valid zip archive.") from None


def _tag(element: ET.Element) -> str:
    return element.tag.removeprefix(_NS)


def _text(element: ET.Element) -> str:
    return "".join(element.itertext())


def _title_level(depth: int) -> int:
    # Body title is level 1; a top-level section title is level 2.
    return min(_MAX_LEVEL, 1 + depth)


def _walk(element: ET.Element, depth: int, out: list[RawBlock]) -> None:
    """Emit blocks for `element`'s children; `depth` = section nesting."""
    for child in element:
        tag = _tag(child)
        if tag == "title":
            text = " ".join(_text(p) for p in child if _tag(p) == "p")
            out.append(RawBlock("heading", text, level=_title_level(depth)))
        elif tag == "section":
            _walk(child, depth + 1, out)
        elif tag in _PARAGRAPHS:
            out.append(RawBlock("paragraph", _text(child)))
        elif tag == "subtitle":
            level = min(_MAX_LEVEL, _title_level(depth) + 1)
            out.append(RawBlock("heading", _text(child), level=level))
        elif tag == "poem":
            _walk_poem(child, depth, out)
        elif tag in _CONTAINERS:
            _walk(child, depth, out)
        # empty-line, image, table and anything unknown: skipped (§14.5)


def _walk_poem(poem: ET.Element, depth: int, out: list[RawBlock]) -> None:
    # A poem title reads like a subtitle; stanza titles too.
    level = min(_MAX_LEVEL, _title_level(depth) + 1)
    for child in poem.iter():
        tag = _tag(child)
        if tag == "title":
            text = " ".join(_text(p) for p in child if _tag(p) == "p")
            out.append(RawBlock("heading", text, level=level))
        elif tag in ("v", "text-author"):
            out.append(RawBlock("paragraph", _text(child)))
