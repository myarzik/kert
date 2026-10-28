"""§14.5 FB2 ingest: hand-written FictionBook fixtures → exact raw blocks."""

import zipfile
from pathlib import Path

import pytest

from kert.compiler.ingest import Ingester, IngestError, RawBlock, ingester_for
from kert.compiler.ingest_fb2 import Fb2Ingester

NS = "http://www.gribuser.ru/xml/fictionbook/2.0"


def fb2(body: str, *, title: str = "Книга", extra: str = "", encoding="utf-8"):
    return (
        f'<?xml version="1.0" encoding="{encoding}"?>\n'
        f'<FictionBook xmlns="{NS}" xmlns:l="http://www.w3.org/1999/xlink">'
        f"<description><title-info><book-title>{title}</book-title>"
        f"</title-info></description>"
        f"<body>{body}</body>{extra}</FictionBook>"
    ).encode(encoding)


@pytest.fixture
def ingest(tmp_path):
    def _ingest(data: bytes, name: str = "book.fb2"):
        path = tmp_path / name
        path.write_bytes(data)
        return Fb2Ingester("ru").ingest(path)

    return _ingest


def test_satisfies_ingester_protocol():
    assert isinstance(Fb2Ingester("ru"), Ingester)


def test_title_from_description(ingest):
    assert ingest(fb2("<section><p>Текст.</p></section>", title="Война")).title == (
        "Война"
    )


def test_body_and_section_titles_get_depth_levels(ingest):
    body = (
        "<title><p>Книга</p></title>"
        "<section><title><p>Часть 1</p></title>"
        "<section><title><p>Глава 1</p><p>Начало</p></title><p>Текст.</p></section>"
        "</section>"
    )

    assert ingest(fb2(body)).blocks == [
        RawBlock("heading", "Книга", level=1),
        RawBlock("heading", "Часть 1", level=2),
        RawBlock("heading", "Глава 1 Начало", level=3),
        RawBlock("paragraph", "Текст."),
    ]


def test_section_title_level_is_capped_at_6(ingest):
    body = "<section>" * 6 + "<title><p>Deep</p></title>" + "</section>" * 6

    assert ingest(fb2(body)).blocks == [RawBlock("heading", "Deep", level=6)]


def test_subtitle_is_one_level_below_its_section_title(ingest):
    body = "<section><title><p>Глава</p></title><subtitle>* * *</subtitle></section>"

    assert ingest(fb2(body)).blocks == [
        RawBlock("heading", "Глава", level=2),
        RawBlock("heading", "* * *", level=3),
    ]


def test_inline_markup_becomes_text_and_note_refs_keep_their_text(ingest):
    body = (
        "<section><p>Он <emphasis>сказал</emphasis> <strong>громко</strong>"
        '<a l:href="#n1" type="note">[1]</a>.</p></section>'
    )

    assert ingest(fb2(body)).blocks == [
        RawBlock("paragraph", "Он сказал громко[1]."),
    ]


def test_epigraph_cite_poem_and_text_author(ingest):
    body = (
        "<section>"
        "<epigraph><p>Эпиграф.</p><text-author>Автор</text-author></epigraph>"
        "<cite><p>Цитата.</p></cite>"
        "<poem><title><p>Стих</p></title>"
        "<stanza><v>Строка один,</v><v>строка два.</v></stanza></poem>"
        "</section>"
    )

    assert ingest(fb2(body)).blocks == [
        RawBlock("paragraph", "Эпиграф."),
        RawBlock("paragraph", "Автор"),
        RawBlock("paragraph", "Цитата."),
        RawBlock("heading", "Стих", level=3),
        RawBlock("paragraph", "Строка один,"),
        RawBlock("paragraph", "строка два."),
    ]


def test_empty_lines_images_and_tables_are_skipped(ingest):
    body = (
        '<section><p>До.</p><empty-line/><image l:href="#i"/>'
        "<table><tr><td>ячейка</td></tr></table><p>После.</p></section>"
    )

    assert ingest(fb2(body)).blocks == [
        RawBlock("paragraph", "До."),
        RawBlock("paragraph", "После."),
    ]


def test_notes_body_and_binaries_are_skipped(ingest):
    extra = (
        '<body name="notes"><section id="n1"><p>Сноска.</p></section></body>'
        '<binary id="i" content-type="image/png">AAAA</binary>'
    )

    assert ingest(fb2("<section><p>Текст.</p></section>", extra=extra)).blocks == [
        RawBlock("paragraph", "Текст."),
    ]


def test_windows_1251_declaration_is_honored(ingest):
    data = fb2("<section><p>Привет.</p></section>", encoding="windows-1251")

    assert ingest(data).blocks == [RawBlock("paragraph", "Привет.")]


def test_fb2_zip_with_one_member(ingest, tmp_path):
    archive = tmp_path / "book.fb2.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("inner.fb2", fb2("<section><p>Из архива.</p></section>"))

    result = Fb2Ingester("ru").ingest(archive)

    assert result.blocks == [RawBlock("paragraph", "Из архива.")]


@pytest.mark.parametrize("members", [[], ["a.fb2", "b.fb2"], ["a.txt"]])
def test_fb2_zip_needs_exactly_one_fb2(tmp_path, members):
    archive = tmp_path / "book.fb2.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        for name in members:
            zf.writestr(name, fb2("<section><p>x</p></section>"))

    with pytest.raises(IngestError, match="fb2"):
        Fb2Ingester("ru").ingest(archive)


@pytest.mark.parametrize(
    ("data", "name"),
    [
        (b"<FictionBook><body><p>unclosed</body>", "book.fb2"),
        (b"not xml at all", "book.fb2"),
        (
            f'<FictionBook xmlns="{NS}"><description/></FictionBook>'.encode(),
            "book.fb2",
        ),
        (b"PK not really a zip", "book.fb2.zip"),
    ],
    ids=["invalid-xml", "not-xml", "no-body", "bad-zip"],
)
def test_malformed_input_is_user_error(ingest, data, name):
    with pytest.raises(IngestError):
        ingest(data, name)


# --- Dispatch (§14.1) ----------------------------------------------------------------


@pytest.mark.parametrize("name", ["book.fb2", "BOOK.FB2", "book.fb2.zip", "b.FB2.ZIP"])
def test_ingester_for_fb2(name):
    ingester, fmt = ingester_for(Path(name), "ru")

    assert isinstance(ingester, Fb2Ingester)
    assert fmt == "fb2"


def test_plain_zip_is_not_fb2():
    with pytest.raises(IngestError, match=r"\.fb2\.zip"):
        ingester_for(Path("book.zip"), "ru")
