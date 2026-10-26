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
    conn = sqlite3.connect(out)
    yield summary, conn, out
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
    _, _, out = compiled

    assert sorted(p.name for p in out.parent.iterdir()) == ["book.kert"]
