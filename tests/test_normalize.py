import pytest

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


# --- normalize(): pipeline over paragraphs -------------------------------------


def test_normalize_types_blocks_after_dash_normalization():
    assert normalize(["- Привет, - сказал он.", "Он ушёл."], "ru") == [
        NormalizedBlock(type="dialogue", text="— Привет, — сказал он."),
        NormalizedBlock(type="paragraph", text="Он ушёл."),
    ]


def test_normalize_drops_paragraphs_empty_after_normalization():
    assert normalize(["  ", "\u00ad", "a"], "en") == [
        NormalizedBlock(type="paragraph", text="a"),
    ]


def test_en_paragraph_starting_with_em_dash_is_dialogue():
    # §4.3 typing rule is language-independent; only dash normalization is RU.
    assert normalize(["— Hi."], "en") == [
        NormalizedBlock(type="dialogue", text="— Hi."),
    ]


def test_en_hyphen_start_is_not_dialogue():
    assert normalize(["- Hi."], "en") == [
        NormalizedBlock(type="paragraph", text="- Hi."),
    ]
