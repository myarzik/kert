"""§14.4 Markdown ingest: hand-written fixtures → exact raw blocks."""

import pytest

from kert.compiler.ingest import Ingester, IngestError, RawBlock, ingester_for
from kert.compiler.ingest_md import MarkdownIngester


@pytest.fixture
def md(tmp_path):
    def _md(text: str, *, data: bytes | None = None, name: str = "book.md"):
        path = tmp_path / name
        path.write_bytes(data if data is not None else text.encode())
        return MarkdownIngester("ru").ingest(path)

    return _md


def blocks(result):
    return result.blocks


def test_satisfies_ingester_protocol():
    assert isinstance(MarkdownIngester("ru"), Ingester)


def test_has_no_metadata_title(md):
    assert md("# Title\n").title is None


def test_atx_and_setext_headings_with_levels(md):
    text = "# One\n\n### Three\n\nTwo\n---\n\nUno\n===\n"

    assert blocks(md(text)) == [
        RawBlock("heading", "One", level=1),
        RawBlock("heading", "Three", level=3),
        RawBlock("heading", "Two", level=2),
        RawBlock("heading", "Uno", level=1),
    ]


def test_paragraph_lines_join_and_blockquote_paragraphs(md):
    text = "First line\nsecond line.\n\n> Quoted\n> text.\n>\n> Again.\n"

    assert blocks(md(text)) == [
        RawBlock("paragraph", "First line second line."),
        RawBlock("paragraph", "Quoted text."),
        RawBlock("paragraph", "Again."),
    ]


def test_bullet_list_items_get_bullet_prefix(md):
    assert blocks(md("- one\n- two\n* three\n")) == [
        RawBlock("list_item", "• one"),
        RawBlock("list_item", "• two"),
        RawBlock("list_item", "• three"),
    ]


def test_ordered_list_numbers_from_start(md):
    assert blocks(md("3. three\n4. four\n9. five\n")) == [
        RawBlock("list_item", "3. three"),
        RawBlock("list_item", "4. four"),
        RawBlock("list_item", "5. five"),
    ]


def test_loose_item_with_two_paragraphs_prefixes_only_the_first(md):
    text = "1. First para.\n\n   Second para.\n\n2. Next.\n"

    assert blocks(md(text)) == [
        RawBlock("list_item", "1. First para."),
        RawBlock("list_item", "Second para."),
        RawBlock("list_item", "2. Next."),
    ]


def test_nested_lists_flatten_in_document_order(md):
    text = "- outer\n  1. inner a\n  2. inner b\n- after\n"

    assert blocks(md(text)) == [
        RawBlock("list_item", "• outer"),
        RawBlock("list_item", "1. inner a"),
        RawBlock("list_item", "2. inner b"),
        RawBlock("list_item", "• after"),
    ]


def test_fenced_and_indented_code_keep_content_and_drop_info(md):
    text = "```python\ndef f():\n    return 1\n```\n\n    indented\n      more\n"

    assert blocks(md(text)) == [
        RawBlock("code", "def f():\n    return 1\n"),
        RawBlock("code", "indented\n  more\n"),
    ]


def test_inline_markup_becomes_plain_text(md):
    text = (
        "Some *em* and **strong** and ~~gone~~, `code()`,\n"
        "a [link](http://x) and ![alt text](i.png).  \nHard break.\n"
    )

    assert blocks(md(text)) == [
        RawBlock(
            "paragraph",
            "Some em and strong and gone, code(), a link and alt text. Hard break.",
        ),
    ]


def test_html_rules_and_tables_are_skipped(md):
    text = (
        "<div>\nraw html\n</div>\n\n---\n\n"
        "| a | b |\n|---|---|\n| 1 | 2 |\n\nAfter <b>inline</b> html.\n"
    )

    assert blocks(md(text)) == [RawBlock("paragraph", "After inline html.")]


def test_front_matter_is_skipped(md):
    text = "---\ntitle: X\ntags: [a]\n---\n\n# Real\n\nBody.\n"

    assert blocks(md(text)) == [
        RawBlock("heading", "Real", level=1),
        RawBlock("paragraph", "Body."),
    ]


def test_thematic_break_at_start_is_not_front_matter_without_closing(md):
    assert blocks(md("---\n\nText.\n")) == [RawBlock("paragraph", "Text.")]


def test_crlf_and_bom(md):
    data = "﻿# Т\r\n\r\nА б.\r\n".encode()

    assert blocks(md("", data=data)) == [
        RawBlock("heading", "Т", level=1),
        RawBlock("paragraph", "А б."),
    ]


def test_cp1251_fallback_for_ru(md):
    data = "# Глава\n\nТекст.\n".encode("cp1251")

    assert blocks(md("", data=data)) == [
        RawBlock("heading", "Глава", level=1),
        RawBlock("paragraph", "Текст."),
    ]


def test_undecodable_en_markdown_is_user_error(tmp_path):
    path = tmp_path / "book.md"
    path.write_bytes("Привет".encode("cp1251"))

    with pytest.raises(IngestError):
        MarkdownIngester("en").ingest(path)


# --- Format dispatch by suffix (§14.1) ----------------------------------------------


@pytest.mark.parametrize(
    ("name", "kind", "source_format"),
    [
        ("book.txt", "TxtIngester", "txt"),
        ("book.TXT", "TxtIngester", "txt"),
        ("book.md", "MarkdownIngester", "md"),
        ("notes.markdown", "MarkdownIngester", "md"),
        ("book.Md", "MarkdownIngester", "md"),
    ],
)
def test_ingester_for_suffix(name, kind, source_format):
    from pathlib import Path

    ingester, fmt = ingester_for(Path(name), "ru")

    assert type(ingester).__name__ == kind
    assert fmt == source_format


@pytest.mark.parametrize("name", ["book.docx", "book", "book.pdf"])
def test_unsupported_suffix_is_user_error_listing_supported(name):
    from pathlib import Path

    with pytest.raises(IngestError, match=r"\.txt.*\.md"):
        ingester_for(Path(name), "ru")
