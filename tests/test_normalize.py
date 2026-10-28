import pytest

from kert.compiler.ingest import RawBlock
from kert.compiler.normalize import (
    NormalizedBlock,
    block_type,
    normalize,
    normalize_paragraph,
)

# --- §4.2 character-level normalization (both languages) -------------------


@pytest.mark.parametrize("lang", ["ru", "en"])
def test_nfc(lang):
    assert normalize_paragraph("е\u0308ж", lang) == "ёж"


@pytest.mark.parametrize("lang", ["ru", "en"])
def test_soft_hyphen_removed(lang):
    assert normalize_paragraph("при\u00adвет", lang) == "привет"


@pytest.mark.parametrize("lang", ["ru", "en"])
def test_no_break_spaces_become_spaces(lang):
    assert normalize_paragraph("a\u00a0b\u202fc", lang) == "a b c"


@pytest.mark.parametrize("lang", ["ru", "en"])
def test_whitespace_collapsed_and_stripped(lang):
    assert normalize_paragraph("  a \t  b  ", lang) == "a b"


# --- §4.2 dash normalization (RU only) ---------------------------------------


@pytest.mark.parametrize("dash", ["-", "–"])
def test_ru_paragraph_initial_dash_with_space_becomes_em_dash(dash):
    assert normalize_paragraph(f"{dash} Привет", "ru") == "— Привет"


def test_ru_paragraph_initial_dash_without_space_unchanged():
    assert normalize_paragraph("-Привет", "ru") == "-Привет"


def test_ru_inline_spaced_dashes_become_em_dash():
    assert normalize_paragraph("а - б – в", "ru") == "а — б — в"


def test_ru_hyphenated_word_unchanged():
    assert normalize_paragraph("кто-то", "ru") == "кто-то"


def test_ru_dash_surrounded_by_no_break_spaces():
    assert normalize_paragraph("а\u00a0-\u00a0б", "ru") == "а — б"


def test_ru_leading_whitespace_before_initial_dash():
    assert normalize_paragraph("  - Привет", "ru") == "— Привет"


@pytest.mark.parametrize("text", ["- Hi", "– Hi", "a - b", "a – b"])
def test_en_has_no_dash_normalization(text):
    assert normalize_paragraph(text, "en") == text


# --- §4.3 block typing --------------------------------------------------------


def test_em_dash_with_space_at_start_is_dialogue():
    assert block_type("— Привет") == "dialogue"


@pytest.mark.parametrize("text", ["Привет — сказал он.", "—Привет", "Привет."])
def test_otherwise_paragraph(text):
    assert block_type(text) == "paragraph"


# --- normalize(): typed raw blocks (§4.2–4.3, §14.2) -----------------------------


def paragraphs(*texts):
    return [RawBlock("paragraph", t) for t in texts]


def test_normalize_types_blocks_after_dash_normalization():
    assert normalize(paragraphs("- Привет, - сказал он.", "Он ушёл."), "ru") == [
        NormalizedBlock(type="dialogue", text="— Привет, — сказал он."),
        NormalizedBlock(type="paragraph", text="Он ушёл."),
    ]


def test_normalize_drops_paragraphs_empty_after_normalization():
    assert normalize(paragraphs("  ", "\u00ad", "a"), "en") == [
        NormalizedBlock(type="paragraph", text="a"),
    ]


def test_en_paragraph_starting_with_em_dash_is_dialogue():
    # §4.3 typing rule is language-independent; only dash normalization is RU.
    assert normalize(paragraphs("— Hi."), "en") == [
        NormalizedBlock(type="dialogue", text="— Hi."),
    ]


def test_en_hyphen_start_is_not_dialogue():
    assert normalize(paragraphs("- Hi."), "en") == [
        NormalizedBlock(type="paragraph", text="- Hi."),
    ]


def test_heading_and_list_item_are_normalized_like_paragraphs():
    raw = [
        RawBlock("heading", "  Глава\u00a01 -  начало ", level=1),
        RawBlock("list_item", "• пункт  - один"),
    ]

    assert normalize(raw, "ru") == [
        NormalizedBlock(type="heading", text="Глава 1 — начало", chapter=1),
        NormalizedBlock(type="list_item", text="• пункт — один", chapter=1),
    ]


def test_only_paragraphs_become_dialogue():
    raw = [RawBlock("list_item", "— пункт"), RawBlock("heading", "— Глава", level=1)]

    assert [b.type for b in normalize(raw, "ru")] == ["list_item", "heading"]


def test_code_is_kept_verbatim_except_nfc_and_newlines():
    code = "def f():\r\n    return  1   - 2\r\n\r\n\n"

    assert normalize([RawBlock("code", code)], "ru") == [
        NormalizedBlock(type="code", text="def f():\n    return  1   - 2"),
    ]


def test_code_nfc():
    assert normalize([RawBlock("code", "e\u0301")], "en")[0].text == "\u00e9"


def test_empty_code_is_dropped():
    assert normalize([RawBlock("code", "\n  \n")], "en") == []


# --- Chapters (§14.2) ---------------------------------------------------------------


def chapters(raw):
    return [(b.text, b.chapter) for b in normalize(raw, "en")]


def test_no_headings_means_no_chapters():
    assert chapters(paragraphs("a", "b")) == [("a", None), ("b", None)]


def test_top_level_headings_start_chapters_deeper_ones_do_not():
    raw = [
        RawBlock("paragraph", "preface"),
        RawBlock("heading", "One", level=1),
        RawBlock("paragraph", "a"),
        RawBlock("heading", "One.1", level=2),
        RawBlock("paragraph", "b"),
        RawBlock("heading", "Two", level=1),
        RawBlock("code", "c"),
    ]

    assert chapters(raw) == [
        ("preface", None),
        ("One", 1),
        ("a", 1),
        ("One.1", 1),
        ("b", 1),
        ("Two", 2),
        ("c", 2),
    ]


def test_smallest_present_level_defines_chapters():
    # A document whose headings start at level 2 still gets chapters.
    raw = [
        RawBlock("heading", "A", level=2),
        RawBlock("heading", "A.1", level=3),
        RawBlock("heading", "B", level=2),
    ]

    assert chapters(raw) == [("A", 1), ("A.1", 1), ("B", 2)]


def test_dropped_heading_does_not_start_a_chapter():
    raw = [
        RawBlock("heading", " ", level=1),
        RawBlock("paragraph", "a"),
        RawBlock("heading", "Real", level=1),
    ]

    assert chapters(raw) == [("a", None), ("Real", 1)]
