import pytest

from kert.compiler.ingest import Ingester, IngestError, IngestResult, RawBlock
from kert.compiler.ingest_txt import TxtIngester


@pytest.fixture
def write(tmp_path):
    def _write(data: bytes):
        path = tmp_path / "book.txt"
        path.write_bytes(data)
        return path

    return _write


def ingest(path, lang="ru"):
    """Paragraph texts; a .txt file yields only paragraphs and no title (§14.1)."""
    result = TxtIngester(lang).ingest(path)
    assert isinstance(result, IngestResult)
    assert result.title is None
    assert all(b == RawBlock("paragraph", b.text) for b in result.blocks)
    return [b.text for b in result.blocks]


def test_txt_ingester_satisfies_ingester_protocol():
    assert isinstance(TxtIngester("ru"), Ingester)


def test_splits_paragraphs_on_blank_line(write):
    assert ingest(write(b"One.\n\nTwo.")) == ["One.", "Two."]


def test_whitespace_only_lines_and_runs_are_one_boundary(write):
    assert ingest(write(b"One.\n \n\t\n\nTwo.")) == ["One.", "Two."]


def test_leading_and_trailing_blank_lines_yield_no_paragraphs(write):
    assert ingest(write(b"\n\n  \nOne.\n\n\n")) == ["One."]


def test_joins_consecutive_lines_with_single_space(write):
    assert ingest(write(b"one\ntwo\nthree\n\nfour")) == ["one two three", "four"]


def test_crlf_line_endings(write):
    assert ingest(write(b"one\r\ntwo\r\n\r\nthree\r\n")) == ["one two", "three"]


def test_utf8_bom_is_stripped(write):
    assert ingest(write("\ufeffПривет.".encode())) == ["Привет."]


def test_utf8_without_bom(write):
    assert ingest(write("Привет.\n\nМир.".encode())) == ["Привет.", "Мир."]


def test_cp1251_fallback_for_ru(write):
    data = "Привет.\n\nМир.".encode("cp1251")

    assert ingest(write(data), lang="ru") == ["Привет.", "Мир."]


def test_no_cp1251_fallback_for_en(write):
    data = "Привет.".encode("cp1251")

    with pytest.raises(IngestError, match="--encoding"):
        ingest(write(data), lang="en")


def test_ru_fails_when_cp1251_also_cannot_decode(write):
    # 0x98 is invalid UTF-8 as a lead byte and undefined in cp1251.
    with pytest.raises(IngestError, match="--encoding"):
        ingest(write(b"\x98"), lang="ru")


def test_empty_file_yields_no_paragraphs(write):
    assert ingest(write(b"")) == []
