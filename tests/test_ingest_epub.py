"""§14.6 EPUB ingest: minimal EPUBs built in tmp_path → exact raw blocks."""

import zipfile
from pathlib import Path

import pytest

from kert.compiler.ingest import Ingester, IngestError, RawBlock, ingester_for
from kert.compiler.ingest_epub import EpubIngester

CONTAINER = """<?xml version="1.0"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="{opf}" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>"""


def xhtml(body: str, head: str = "<title>t</title>") -> str:
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<html xmlns="http://www.w3.org/1999/xhtml" '
        'xmlns:epub="http://www.idpf.org/2007/ops">'
        f"<head>{head}</head><body>{body}</body></html>"
    )


def make_epub(
    tmp_path,
    docs: dict[str, str],
    spine: list[str | tuple[str, str]],
    *,
    title: str = "Book",
    opf_dir: str = "OEBPS",
    nav: str | None = None,
    extra_manifest: str = "",
):
    """docs: href -> xhtml; spine: hrefs or (href, 'no') for linear="no"."""
    path = tmp_path / "book.epub"
    manifest = [
        f'<item id="d{i}" href="{href}" media-type="application/xhtml+xml"/>'
        for i, href in enumerate(sorted(docs))  # manifest order != spine order
    ]
    ids = {href: f"d{i}" for i, href in enumerate(sorted(docs))}
    if nav is not None:
        manifest.append(
            '<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" '
            'properties="nav"/>'
        )
    itemrefs = []
    for entry in spine:
        href, linear = (entry, None) if isinstance(entry, str) else entry
        idref = "nav" if href == "nav.xhtml" else ids[href]
        attr = f' linear="{linear}"' if linear else ""
        itemrefs.append(f'<itemref idref="{idref}"{attr}/>')
    opf = (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<package xmlns="http://www.idpf.org/2007/opf" version="3.0">'
        '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
        f"<dc:title>{title}</dc:title></metadata>"
        f"<manifest>{''.join(manifest)}{extra_manifest}</manifest>"
        f"<spine>{''.join(itemrefs)}</spine></package>"
    )
    prefix = f"{opf_dir}/" if opf_dir else ""
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("mimetype", "application/epub+zip")
        zf.writestr(
            "META-INF/container.xml", CONTAINER.format(opf=f"{prefix}content.opf")
        )
        zf.writestr(f"{prefix}content.opf", opf)
        for href, content in docs.items():
            zf.writestr(prefix + href.replace("%20", " "), content)
        if nav is not None:
            zf.writestr(f"{prefix}nav.xhtml", nav)
    return path


def ingest(path):
    return EpubIngester("ru").ingest(path)


def one_doc(tmp_path, body, **kwargs):
    return ingest(make_epub(tmp_path, {"c.xhtml": xhtml(body, **kwargs)}, ["c.xhtml"]))


def test_satisfies_ingester_protocol():
    assert isinstance(EpubIngester("ru"), Ingester)


def test_title_from_dc_title(tmp_path):
    path = make_epub(tmp_path, {"c.xhtml": xhtml("<p>x</p>")}, ["c.xhtml"], title="Т")

    assert ingest(path).title == "Т"


def test_documents_follow_spine_order_not_manifest_order(tmp_path):
    docs = {"a.xhtml": xhtml("<p>A.</p>"), "b.xhtml": xhtml("<p>B.</p>")}
    path = make_epub(tmp_path, docs, ["b.xhtml", "a.xhtml"])

    assert ingest(path).blocks == [
        RawBlock("paragraph", "B."),
        RawBlock("paragraph", "A."),
    ]


def test_non_linear_items_and_nav_document_are_skipped(tmp_path):
    docs = {"cover.xhtml": xhtml("<p>Cover.</p>"), "c.xhtml": xhtml("<p>Text.</p>")}
    nav = xhtml('<nav epub:type="toc"><ol><li><a href="c.xhtml">C</a></li></ol></nav>')
    path = make_epub(
        tmp_path, docs, [("cover.xhtml", "no"), "nav.xhtml", "c.xhtml"], nav=nav
    )

    assert ingest(path).blocks == [RawBlock("paragraph", "Text.")]


def test_epub2_ncx_is_not_read(tmp_path):
    ncx = '<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>'
    path = make_epub(
        tmp_path, {"c.xhtml": xhtml("<p>Text.</p>")}, ["c.xhtml"], extra_manifest=ncx
    )

    assert ingest(path).blocks == [RawBlock("paragraph", "Text.")]


def test_opf_at_zip_root_and_url_encoded_hrefs(tmp_path):
    docs = {"Text/ch%201.xhtml": xhtml("<p>Encoded.</p>")}
    path = make_epub(tmp_path, docs, ["Text/ch%201.xhtml"], opf_dir="")

    assert ingest(path).blocks == [RawBlock("paragraph", "Encoded.")]


def test_headings_paragraphs_and_inline_text(tmp_path):
    body = (
        "<h1>Глава <em>1</em></h1><h3>Раздел</h3>"
        '<p>Он <span class="x">сказал</span> <a href="#n1" epub:type="noteref">1</a>.'
        "</p>"
    )

    assert one_doc(tmp_path, body).blocks == [
        RawBlock("heading", "Глава 1", level=1),
        RawBlock("heading", "Раздел", level=3),
        RawBlock("paragraph", "Он сказал 1."),
    ]


def test_lists_get_prefixes_and_nested_lists_flatten(tmp_path):
    body = (
        "<ul><li>one</li><li>two<ol start='4'><li>four</li><li>five</li></ol></li>"
        "<li><p>para in item</p></li></ul>"
    )

    assert one_doc(tmp_path, body).blocks == [
        RawBlock("list_item", "• one"),
        RawBlock("list_item", "• two"),
        RawBlock("list_item", "4. four"),
        RawBlock("list_item", "5. five"),
        RawBlock("list_item", "• para in item"),
    ]


def test_pre_keeps_layout_and_br_is_a_space_elsewhere(tmp_path):
    body = (
        "<pre><code>def f():\n    return 1<br/>x = 2</code></pre>"
        "<p>line one<br/>line two</p>"
    )

    assert one_doc(tmp_path, body).blocks == [
        RawBlock("code", "def f():\n    return 1\nx = 2"),
        RawBlock("paragraph", "line one line two"),
    ]


def test_loose_text_in_containers_becomes_paragraphs(tmp_path):
    body = (
        "<div>Loose text <b>in div</b>.<p>Inside p.</p>Tail text.</div>"
        "<blockquote>Quoted.</blockquote><section>Sectioned.</section>"
    )

    assert one_doc(tmp_path, body).blocks == [
        RawBlock("paragraph", "Loose text in div."),
        RawBlock("paragraph", "Inside p."),
        RawBlock("paragraph", "Tail text."),
        RawBlock("paragraph", "Quoted."),
        RawBlock("paragraph", "Sectioned."),
    ]


def test_skipped_elements_and_footnotes(tmp_path):
    body = (
        "<script>var x = 1;</script><style>p {}</style>"
        "<nav><p>Menu</p></nav>"
        "<p>Text.</p>"
        '<aside epub:type="footnote" id="n1"><p>Note body.</p></aside>'
        '<section epub:type="endnotes"><p>End note.</p></section>'
        '<div epub:type="rearnote"><p>Rear.</p></div>'
    )

    assert one_doc(tmp_path, body, head="<title>Head title</title>").blocks == [
        RawBlock("paragraph", "Text."),
    ]


def test_character_references_are_decoded(tmp_path):
    body = "<p>A &amp; B &#8212; C&nbsp;D &#x2014; &lt;e&gt;</p>"

    assert one_doc(tmp_path, body).blocks == [
        RawBlock("paragraph", "A & B — C D — <e>"),
    ]


def test_html_style_unclosed_tags_are_tolerated(tmp_path):
    body = "<p>One<p>Two<br>three"

    assert one_doc(tmp_path, body).blocks == [
        RawBlock("paragraph", "One"),
        RawBlock("paragraph", "Two three"),
    ]


@pytest.mark.parametrize(
    "broken",
    ["not-zip", "no-container", "no-opf", "bad-opf-xml", "missing-document"],
)
def test_malformed_epub_is_user_error(tmp_path, broken):
    path = tmp_path / "book.epub"
    if broken == "not-zip":
        path.write_bytes(b"not a zip")
    else:
        good = make_epub(tmp_path, {"c.xhtml": xhtml("<p>x</p>")}, ["c.xhtml"])
        with zipfile.ZipFile(good) as src:
            entries = {n: src.read(n) for n in src.namelist()}
        if broken == "no-container":
            del entries["META-INF/container.xml"]
        elif broken == "no-opf":
            del entries["OEBPS/content.opf"]
        elif broken == "bad-opf-xml":
            entries["OEBPS/content.opf"] = b"<package><unclosed></package>"
        elif broken == "missing-document":
            del entries["OEBPS/c.xhtml"]
        path.unlink()
        with zipfile.ZipFile(path, "w") as dst:
            for name, data in entries.items():
                dst.writestr(name, data)

    with pytest.raises(IngestError):
        ingest(path)


# --- Dispatch (§14.1) -----------------------------------------------------------------


@pytest.mark.parametrize("name", ["book.epub", "BOOK.EPUB"])
def test_ingester_for_epub(name):
    ingester, fmt = ingester_for(Path(name), "ru")

    assert isinstance(ingester, EpubIngester)
    assert fmt == "epub"


# --- End to end: chapters run across documents (§14.2, §14.6) -------------------------


@pytest.mark.spacy
def test_compile_epub_numbers_chapters_across_documents(tmp_path):
    import sqlite3

    from conftest import require_model

    from kert.cli import main

    require_model("ru_core_news_sm")
    docs = {
        "1.xhtml": xhtml("<h1>Глава 1</h1><p>Он вышел из дома.</p>"),
        "2.xhtml": xhtml("<h1>Глава 2</h1><h2>Часть</h2><p>На улице было пусто.</p>"),
    }
    source = make_epub(tmp_path, docs, ["1.xhtml", "2.xhtml"], title="Роман")
    out = tmp_path / "book.kert"

    assert main(["compile", str(source), "-o", str(out), "--lang", "ru"]) == 0

    conn = sqlite3.connect(out)
    try:
        meta = dict(conn.execute("SELECT key, value FROM meta"))
        rows = conn.execute("SELECT type, chapter FROM blocks ORDER BY id").fetchall()
    finally:
        conn.close()
    assert (meta["source_format"], meta["title"]) == ("epub", "Роман")
    assert rows == [
        ("heading", 1),
        ("paragraph", 1),
        ("heading", 2),
        ("heading", 2),
        ("paragraph", 2),
    ]
