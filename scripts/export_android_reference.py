"""Export the Python reference for the Android port (spec §16.6).

Usage: uv run python scripts/export_android_reference.py OUT_DIR

Compiles the fixture books with the Python compiler into OUT_DIR/*.kert and
writes OUT_DIR/reference.json with the Python Reader's chunk spans, word
counts and words-before per chunk at every width 5..12. The Kotlin `core`
tests read both and must match exactly. Generated, never committed: always
regenerate before running the Android tests.
"""

import json
import sys
import tempfile
import zipfile
from pathlib import Path

from kert.compiler.pipeline import compile_book
from kert.reader.config import WIDTH_MAX, WIDTH_MIN
from kert.reader.state import Book, build_chunks
from kert.reader.store import BookStore

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"

# Characters outside the BMP: 2 UTF-16 code units, 1 Python code point.
NON_BMP_XHTML = """<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml"><head><title>t</title></head><body>
<h1>Emoji 🙂 Chapter</h1>
<p>The 🙂 smile came first, although the 𝔸 letter, the 🚀 rocket and the
𝔹 letter waited patiently in the long line outside the old station.</p>
<p>Short 🎉 one.</p>
</body></html>"""


def _non_bmp_epub(path: Path) -> None:
    container = (
        '<?xml version="1.0"?><container version="1.0" '
        'xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles>'
        '<rootfile full-path="content.opf" '
        'media-type="application/oebps-package+xml"/></rootfiles></container>'
    )
    opf = (
        '<?xml version="1.0"?><package xmlns="http://www.idpf.org/2007/opf" '
        'version="3.0"><metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
        "<dc:title>Non-BMP</dc:title></metadata><manifest>"
        '<item id="c" href="c.xhtml" media-type="application/xhtml+xml"/>'
        '</manifest><spine><itemref idref="c"/></spine></package>'
    )
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("mimetype", "application/epub+zip")
        zf.writestr("META-INF/container.xml", container)
        zf.writestr("content.opf", opf)
        zf.writestr("c.xhtml", NON_BMP_XHTML)


def _reference(kert: Path) -> dict:
    with BookStore.open(kert) as store:
        book = Book(store.blocks, store.sentences, int(store.meta["word_count"]))
    widths = {}
    for width in range(WIDTH_MIN, WIDTH_MAX + 1):
        chunks = build_chunks(book, width)
        widths[str(width)] = [
            [span.sentence_id, span.start_token, span.end_token, words, before]
            for span, words, before in zip(
                chunks.spans, chunks.words, chunks.words_before, strict=True
            )
        ]
    return {"file": kert.name, "word_count": book.word_count, "widths": widths}


def export(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        epub = Path(tmp) / "non_bmp.epub"
        _non_bmp_epub(epub)
        sources = [
            (FIXTURES / "book_ru.txt", "ru", "book_ru.kert"),
            (FIXTURES / "book_en.md", "en", "book_en.kert"),
            (epub, "en", "non_bmp.kert"),
        ]
        books = []
        for source, lang, name in sources:
            compile_book(source, out / name, lang, force=True)
            books.append(_reference(out / name))
    (out / "reference.json").write_text(
        json.dumps({"books": books}, ensure_ascii=False, indent=1), encoding="utf-8"
    )


if __name__ == "__main__":
    export(Path(sys.argv[1]))
