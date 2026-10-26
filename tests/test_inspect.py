import sqlite3

import pytest

from kert.cli import main
from kert.common.errors import KertError
from kert.common.model import Sentence, SplitCandidate
from kert.reader.inspect import parse_range, render_inspection, select_sentences


def sentence(id, block_id, seq, text, candidates):
    # whitespace-separated words plus a final period as separate tokens
    tokens, pos = [], 0
    for word in text[:-1].split(" "):
        tokens.append((pos, pos + len(word)))
        pos += len(word) + 1
    tokens.append((len(text) - 1, len(text)))
    return Sentence(
        id=id,
        block_id=block_id,
        seq=seq,
        text=text,
        tokens=tuple(tokens),
        candidates=tuple(SplitCandidate(i, w) for i, w in candidates),
    )


# RU golden sentence from test_candidates_ru ("cc-conj-obl"), n=10
RU = sentence(
    5, 4, 0, "Мы долго гуляли по парку и разговаривали о книгах.",
    [(3, 0.4), (5, 0.8), (7, 0.4)],
)  # fmt: skip


# --- Rendering (§9) -------------------------------------------------------------


def test_golden_at_default_width_8():
    assert render_inspection(RU, 8) == (
        "Мы долго гуляли⟨0.4⟩ по парку⟨0.8⟩ и разговаривали⟨0.4⟩ о книгах.\n"
        "[Мы долго гуляли по парку и разговаривали о книгах.]"
    )


def test_golden_at_width_6():
    # §6, W=6: {5} 0.028+0.028+0.15=0.206 beats {} 0.444 (see test_chunker)
    assert render_inspection(RU, 6) == (
        "Мы долго гуляли⟨0.4⟩ по парку⟨0.8⟩ и разговаривали⟨0.4⟩ о книгах.\n"
        "[Мы долго гуляли по парку] [и разговаривали о книгах.]"
    )


def test_sentence_without_candidates_has_no_markers():
    plain = sentence(1, 1, 0, "Глава один.", [])

    assert render_inspection(plain, 8) == "Глава один.\n[Глава один.]"


# --- Selection --------------------------------------------------------------------

BOOK = [
    sentence(1, 1, 0, "A b.", []),
    sentence(2, 2, 0, "C d.", []),
    sentence(3, 2, 1, "E f.", []),
    sentence(4, 3, 0, "G h.", []),
]


def ids(selected):
    return [s.id for s in selected]


def test_select_everything_by_default():
    assert ids(select_sentences(BOOK)) == [1, 2, 3, 4]


def test_select_single_sentence():
    assert ids(select_sentences(BOOK, sentence=3)) == [3]


def test_select_block():
    assert ids(select_sentences(BOOK, block=2)) == [2, 3]


def test_select_inclusive_range():
    assert ids(select_sentences(BOOK, span=(2, 4))) == [2, 3, 4]


@pytest.mark.parametrize(
    "kwargs",
    [{"sentence": 9}, {"block": 9}, {"span": (5, 6)}, {"span": (3, 2)}],
)
def test_selection_matching_nothing_is_user_error(kwargs):
    with pytest.raises(KertError):
        select_sentences(BOOK, **kwargs)


def test_more_than_one_selector_is_user_error():
    with pytest.raises(KertError):
        select_sentences(BOOK, sentence=1, block=1)


def test_parse_range():
    assert parse_range("2:5") == (2, 5)


@pytest.mark.parametrize("raw", ["2", "a:b", "2:", ":5", "2:3:4"])
def test_parse_range_rejects_malformed(raw):
    with pytest.raises(KertError):
        parse_range(raw)


# --- CLI (spec §9) ------------------------------------------------------------------

# Compiled fixture sentence 4 is its own paragraph, so its candidates equal the
# "dialogue" golden in test_candidates_ru: [(4, 1.0), (6, 0.8)], n=9.
DIALOGUE_MARKED = "— Привет, —⟨1.0⟩ сказал он⟨0.8⟩ и улыбнулся."


@pytest.mark.spacy
@pytest.mark.parametrize(
    ("extra", "chunks"),
    [
        ([], "[— Привет, — сказал он и улыбнулся.]"),  # default W=8, n <= W+2
        (["--width", "8"], "[— Привет, — сказал он и улыбнулся.]"),
        # W=6: {4} 0.111+0.028=0.139; {} 0.25; {6} 0.4; {4,6} 1.956
        (["--width", "6"], "[— Привет, —] [сказал он и улыбнулся.]"),
    ],
)
def test_cli_inspect_single_sentence(book_path, capsys, extra, chunks):
    code = main(["inspect", str(book_path), "--sentence", "4", *extra])

    assert code == 0
    assert capsys.readouterr().out == f"{DIALOGUE_MARKED}\n{chunks}\n"


@pytest.mark.spacy
def test_cli_inspect_block_separates_sentences_with_blank_line(book_path, capsys):
    code = main(["inspect", str(book_path), "--block", "4"])

    lines = capsys.readouterr().out.split("\n")
    assert code == 0
    assert len(lines) == 6  # 2 + blank + 2 + trailing newline
    assert lines[2] == "" and lines[-1] == ""
    assert lines[0].startswith("Мы долго гуляли")
    assert lines[3].startswith("Вечером")


@pytest.mark.spacy
def test_cli_inspect_does_not_modify_the_book(book_path):
    main(["inspect", str(book_path)])

    assert sorted(p.name for p in book_path.parent.iterdir()) == ["book.kert"]
    conn = sqlite3.connect(book_path)
    try:
        assert conn.execute("SELECT COUNT(*) FROM reader_state").fetchone() == (0,)
    finally:
        conn.close()


@pytest.mark.spacy
@pytest.mark.parametrize(
    "extra",
    [
        ["--sentence", "99"],
        ["--sentence", "1", "--block", "1"],
        ["--range", "nonsense"],
        ["--width", "4"],
        ["--width", "13"],
    ],
)
def test_cli_inspect_user_errors(book_path, extra):
    assert main(["inspect", str(book_path), *extra]) == 1


def test_cli_inspect_missing_book_is_user_error(tmp_path):
    assert main(["inspect", str(tmp_path / "missing.kert")]) == 1
