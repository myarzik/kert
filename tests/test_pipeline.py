import sqlite3
from datetime import timedelta
from importlib.metadata import version
from pathlib import Path

import msgpack
import pytest
import spacy
from conftest import require_model

from kert.compiler.pipeline import compile_book

pytestmark = pytest.mark.spacy

FIXTURE = Path(__file__).parent / "fixtures" / "book_ru.txt"

REQUIRED_META_KEYS = {
    "schema_version",
    "title",
    "language",
    "source_format",
    "source_filename",
    "paragraph_mode",
    "compiler_version",
    "compiled_at",
    "spacy_model",
    "spacy_version",
    "model_version",
    "word_count",
}


@pytest.fixture(scope="module")
def compiled(tmp_path_factory):
    require_model("ru_core_news_sm")
    out = tmp_path_factory.mktemp("compiled") / "book.kert"
    summary = compile_book(FIXTURE, out, "ru")
    # Snapshot before connecting: reading a WAL database creates sidecars.
    listing = sorted(p.name for p in out.parent.iterdir())
    conn = sqlite3.connect(out)
    yield summary, conn, listing
    conn.close()


def meta(conn):
    return dict(conn.execute("SELECT key, value FROM meta"))


def test_summary_counts(compiled):
    summary, _, _ = compiled

    assert (summary.blocks, summary.sentences) == (4, 6)


def test_summary_mean_matches_stored_candidates(compiled):
    summary, conn, _ = compiled
    blobs = [row[0] for row in conn.execute("SELECT candidates FROM sentences")]
    total = sum(len(msgpack.unpackb(b)) for b in blobs)

    assert summary.candidates_per_sentence == pytest.approx(total / 6)


def test_meta_has_exactly_the_required_keys(compiled):
    _, conn, _ = compiled

    assert set(meta(conn)) == REQUIRED_META_KEYS


def test_meta_values(compiled):
    _, conn, _ = compiled
    m = meta(conn)

    assert {k: v for k, v in m.items() if k != "compiled_at"} == {
        "schema_version": "1",
        "title": "book_ru",
        "language": "ru",
        "source_format": "txt",
        "source_filename": "book_ru.txt",
        "paragraph_mode": "blank",
        "compiler_version": version("kert"),
        "spacy_model": "ru_core_news_sm",
        "spacy_version": spacy.__version__,
        "model_version": "3.8.0",
        # is_alpha or like_num, hand-counted: 2 + 7 + 4 + 5 + 9 + 4
        "word_count": "31",
    }


def test_compiled_at_is_iso8601_utc(compiled):
    from datetime import datetime

    _, conn, _ = compiled
    stamp = datetime.fromisoformat(meta(conn)["compiled_at"])

    assert stamp.utcoffset() == timedelta(0)


def test_blocks(compiled):
    _, conn, _ = compiled
    rows = conn.execute("SELECT id, type, chapter FROM blocks ORDER BY id").fetchall()

    assert rows == [
        (1, "paragraph", None),
        (2, "paragraph", None),
        (3, "dialogue", None),
        (4, "paragraph", None),
    ]


def test_sentences_in_global_reading_order(compiled):
    _, conn, _ = compiled
    rows = conn.execute(
        "SELECT id, block_id, seq, text FROM sentences ORDER BY id"
    ).fetchall()

    assert rows == [
        (1, 1, 0, "Глава 1"),
        (2, 2, 0, "Он вышел из дома, хотя шёл дождь."),
        (3, 2, 1, "На улице было пусто."),
        (4, 3, 0, "— Привет, — сказал он и улыбнулся."),
        (5, 4, 0, "Мы долго гуляли по парку и разговаривали о книгах."),
        (6, 4, 1, "Вечером мы вернулись домой."),
    ]


def test_token_spans_index_into_sentence_text(compiled):
    _, conn, _ = compiled
    for text, blob in conn.execute("SELECT text, tokens FROM sentences"):
        spans = msgpack.unpackb(blob)

        assert spans == sorted(spans)
        assert all(text[s:e] and not text[s:e].isspace() for s, e in spans)
        assert "".join(text[s:e] for s, e in spans) == text.replace(" ", "")


def test_dialogue_sentence_candidates(compiled):
    # Same paragraph text as the "dialogue" golden in test_candidates_ru.
    _, conn, _ = compiled
    (blob,) = conn.execute("SELECT candidates FROM sentences WHERE id = 4").fetchone()

    assert msgpack.unpackb(blob) == [[4, 1.0], [6, 0.8]]


def test_mutable_tables_empty(compiled):
    _, conn, _ = compiled

    assert conn.execute("SELECT COUNT(*) FROM reader_state").fetchone() == (0,)
    assert conn.execute("SELECT COUNT(*) FROM advance_log").fetchone() == (0,)


def test_output_is_a_single_file(compiled):
    _, _, listing = compiled

    assert listing == ["book.kert"]


# --- Typed blocks: un-chunked heading/code, chapters (§14.2–14.3) ------------------


@pytest.fixture(scope="module")
def typed_book(nlp_ru):
    from kert.compiler.normalize import NormalizedBlock
    from kert.compiler.pipeline import build_book

    return build_book(
        [
            NormalizedBlock("heading", "Глава 1. Начало", chapter=1),
            NormalizedBlock(
                "paragraph", "Он вышел из дома, хотя шёл дождь.", chapter=1
            ),
            NormalizedBlock("code", "x = 1\ny = 2", chapter=1),
            NormalizedBlock(
                "list_item",
                "• Мы долго гуляли по парку и разговаривали о книгах.",
                chapter=1,
            ),
        ],
        nlp_ru,
        "ru",
    )


def by_block(book, block_id):
    return [s for s in book.sentences if s.block_id == block_id]


def test_blocks_keep_type_and_chapter(typed_book):
    assert [(b.id, b.type, b.chapter) for b in typed_book.blocks] == [
        (1, "heading", 1),
        (2, "paragraph", 1),
        (3, "code", 1),
        (4, "list_item", 1),
    ]


@pytest.mark.parametrize(
    ("block_id", "text", "tokens"),
    [
        (1, "Глава 1. Начало", ["Глава", "1.", "Начало"]),
        (3, "x = 1\ny = 2", ["x", "=", "1", "y", "=", "2"]),
    ],
)
def test_heading_and_code_are_one_unparsed_sentence(typed_book, block_id, text, tokens):
    (sentence,) = by_block(typed_book, block_id)

    assert (sentence.seq, sentence.text) == (0, text)
    assert [text[s:e] for s, e in sentence.tokens] == tokens
    assert sentence.candidates == ()


def test_paragraph_is_parsed_with_golden_candidates(typed_book):
    (sentence,) = by_block(typed_book, 2)

    # test_candidates_ru "comma-mark-advcl"
    assert [(c.token_index, c.weight) for c in sentence.candidates] == [
        (2, 0.4),
        (5, 1.0),
    ]


def test_list_item_is_parsed_like_a_paragraph(typed_book):
    (sentence,) = by_block(typed_book, 4)

    assert [sentence.text[s:e] for s, e in sentence.tokens][:2] == ["•", "Мы"]
    assert len(sentence.tokens) == 11


def test_sentence_ids_are_contiguous_in_reading_order(typed_book):
    assert [s.id for s in typed_book.sentences] == [1, 2, 3, 4]


def test_word_count_mixes_spacy_and_shared_predicate(typed_book):
    # heading 2 (Глава, Начало) + paragraph 7 + code 4 (x 1 y 2) + list item 9
    assert typed_book.word_count == 22
