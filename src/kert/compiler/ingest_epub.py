"""EPUB 2/3 adapter: zipfile + xml.etree (OPF) + html.parser (XHTML), §14.6."""

import posixpath
import re
import zipfile
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote
from xml.etree import ElementTree as ET

from kert.common.model import Lang
from kert.compiler.ingest import IngestError, IngestResult, RawBlock, RawKind

_CONTAINER_NS = "{urn:oasis:names:tc:opendocument:xmlns:container}"
_OPF_NS = "{http://www.idpf.org/2007/opf}"
_DC_NS = "{http://purl.org/dc/elements/1.1/}"
_HTML_TYPES = {"application/xhtml+xml", "text/html"}
_XML_ENCODING = re.compile(rb"""^\s*<\?xml[^>]*encoding=["']([\w.-]+)["']""")


class EpubIngester:
    def __init__(self, lang: Lang) -> None:
        self.lang = lang

    def ingest(self, path: Path) -> IngestResult:
        try:
            with zipfile.ZipFile(path) as archive:
                return _read_book(archive, path)
        except zipfile.BadZipFile:
            raise IngestError(f"{path} is not a valid EPUB (zip) file.") from None


def _member(archive: zipfile.ZipFile, name: str, path: Path) -> bytes:
    try:
        return archive.read(name)
    except KeyError:
        raise IngestError(f"{path} is missing {name}.") from None


def _xml(data: bytes, what: str, path: Path) -> ET.Element:
    try:
        return ET.fromstring(data)
    except ET.ParseError as exc:
        raise IngestError(f"{path}: invalid {what} ({exc}).") from None


def _read_book(archive: zipfile.ZipFile, path: Path) -> IngestResult:
    container = _xml(
        _member(archive, "META-INF/container.xml", path), "container.xml", path
    )
    rootfile = container.find(f".//{_CONTAINER_NS}rootfile")
    if rootfile is None or not rootfile.get("full-path"):
        raise IngestError(f"{path}: container.xml names no package document.")
    opf_name = rootfile.get("full-path", "")
    opf = _xml(_member(archive, opf_name, path), "package document", path)
    base = posixpath.dirname(opf_name)

    manifest = {
        item.get("id"): item
        for item in opf.iterfind(f"{_OPF_NS}manifest/{_OPF_NS}item")
    }
    blocks: list[RawBlock] = []
    for itemref in opf.iterfind(f"{_OPF_NS}spine/{_OPF_NS}itemref"):
        item = manifest.get(itemref.get("idref"))
        if item is None or itemref.get("linear") == "no":
            continue
        if item.get("media-type") not in _HTML_TYPES:
            continue
        if "nav" in (item.get("properties") or "").split():
            continue
        href = unquote(item.get("href", "").split("#")[0])
        name = posixpath.normpath(posixpath.join(base, href))
        blocks += _xhtml_blocks(_member(archive, name, path))

    title = opf.findtext(f"{_OPF_NS}metadata/{_DC_NS}title")
    return IngestResult(blocks=blocks, title=(title or "").strip() or None)


def _decode(data: bytes) -> str:
    match = _XML_ENCODING.match(data)
    encoding = match.group(1).decode() if match else "utf-8-sig"
    try:
        return data.decode(encoding, errors="replace")
    except LookupError:
        return data.decode("utf-8-sig", errors="replace")


def _xhtml_blocks(data: bytes) -> list[RawBlock]:
    parser = _ContentParser()
    parser.feed(_decode(data))
    parser.close()
    return parser.finish()


# Elements whose text is inline content of the surrounding block.
_INLINE = {
    "a", "abbr", "b", "bdi", "bdo", "cite", "code", "data", "dfn", "em", "font",
    "i", "img", "kbd", "mark", "q", "rp", "rt", "ruby", "s", "samp", "small",
    "span", "strike", "strong", "sub", "sup", "time", "tt", "u", "var", "wbr",
}  # fmt: skip
_VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta",
         "param", "source", "track", "wbr"}  # fmt: skip
_SKIP = {"head", "script", "style", "nav", "template"}
_SKIP_EPUB_TYPES = ("footnote", "endnote", "rearnote", "toc")
_HEADINGS = {f"h{n}": n for n in range(1, 7)}


class _Capture:
    def __init__(self, kind: RawKind, level: int | None = None, prefix: str = ""):
        self.kind, self.level, self.parts = kind, level, [prefix] if prefix else []


class _ContentParser(HTMLParser):
    """Block elements → raw blocks; loose container text → paragraphs."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.blocks: list[RawBlock] = []
        self.captures: list[_Capture] = []  # open h*/p/li/pre, innermost last
        self.loose: list[str] = []
        self.lists: list[list[int | None]] = []  # [next number]; None = bullet
        self.skip: list[str] = []  # open skipped elements (their content is dropped)
        self.pre = 0

    # --- output -----------------------------------------------------------------

    def _emit(self, kind: RawKind, text: str, level: int | None = None) -> None:
        if text.strip():
            self.blocks.append(RawBlock(kind, text, level=level))

    def _flush_loose(self) -> None:
        self._emit("paragraph", "".join(self.loose))
        self.loose = []

    def _flush_capture(self) -> None:
        """Emit the innermost capture's text so far (its element stays open)."""
        capture = self.captures[-1]
        self._emit(capture.kind, "".join(capture.parts), capture.level)
        capture.parts = []

    def finish(self) -> list[RawBlock]:
        while self.captures:
            self._flush_capture()
            self.captures.pop()
        self._flush_loose()
        return self.blocks

    # --- parser callbacks ---------------------------------------------------------

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self.skip:
            if tag not in _VOID:
                self.skip.append(tag)
            return
        attributes = dict(attrs)
        epub_type = attributes.get("epub:type") or ""
        if tag in _SKIP or any(t in epub_type for t in _SKIP_EPUB_TYPES):
            if tag not in _VOID:
                self.skip.append(tag)
            return
        if tag == "br":
            self._data("\n" if self.pre else " ")
            return
        if tag in _INLINE or tag in _VOID:
            return
        self._flush_loose()
        if tag in ("ul", "ol"):
            self.lists.append([None] if tag == "ul" else [_start(attributes)])
        elif tag == "li":
            self._open(_Capture("list_item", prefix=self._item_prefix()))
        elif tag == "p" and self.captures and self.captures[-1].kind == "list_item":
            # A paragraph inside a list item is part of the item's text.
            if not "".join(self.captures[-1].parts).endswith(" "):
                self._data(" ")
        elif tag == "p":
            self._open(_Capture("paragraph"))
        elif tag in _HEADINGS:
            self._open(_Capture("heading", level=_HEADINGS[tag]))
        elif tag == "pre":
            self.pre += 1
            self._open(_Capture("code"))

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "br" and not self.skip:
            self._data("\n" if self.pre else " ")

    def handle_endtag(self, tag: str) -> None:
        if self.skip:
            if tag == self.skip[-1]:
                self.skip.pop()
            return
        if tag in _INLINE or tag in _VOID:
            return
        if tag in ("ul", "ol"):
            if self.lists:
                self.lists.pop()
        elif tag in ("li", "p", "pre") or tag in _HEADINGS:
            kind = {"li": "list_item", "p": "paragraph", "pre": "code"}.get(
                tag, "heading"
            )
            if tag == "p" and self.captures and self.captures[-1].kind == "list_item":
                return
            if tag == "pre":
                self.pre = max(0, self.pre - 1)
            if self.captures and self.captures[-1].kind == kind:
                self._flush_capture()
                self.captures.pop()
        else:
            self._flush_loose()  # a container closed: its loose text ends here

    def handle_data(self, data: str) -> None:
        if not self.skip:
            self._data(data)

    # --- helpers --------------------------------------------------------------------

    def _open(self, capture: _Capture) -> None:
        # HTML allows <p> to be closed implicitly by the next block element.
        if self.captures and self.captures[-1].kind == "paragraph":
            self._flush_capture()
            self.captures.pop()
        if self.captures:
            self._flush_capture()  # e.g. a nested list inside an item
        self.captures.append(capture)

    def _data(self, data: str) -> None:
        if not self.pre:
            data = data.replace("\n", " ")
        (self.captures[-1].parts if self.captures else self.loose).append(data)

    def _item_prefix(self) -> str:
        if not self.lists:
            return "• "
        counter = self.lists[-1]
        if counter[0] is None:
            return "• "
        prefix = f"{counter[0]}. "
        counter[0] += 1
        return prefix


def _start(attributes: dict[str, str | None]) -> int:
    try:
        return int(attributes.get("start") or 1)
    except ValueError:
        return 1
