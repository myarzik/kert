import hashlib
import json
import sqlite3

import pytest

from kert.common.errors import KertError
from kert.common.model import Block, Sentence, SplitCandidate
from kert.reader.store import BookStore, Position

spacy = pytest.mark.spacy


@pytest.fixture
def store(book_path):
    s = BookStore.open(book_path)
    yield s
    s.close()


def content_digest(path):
    conn = sqlite3.connect(path)
    try:
        digest = hashlib.sha256()
        for table in ("meta", "blocks", "sentences"):
            for row in conn.execute(f"SELECT * FROM {table} ORDER BY 1"):
                digest.update(repr(row).encode())
        return digest.hexdigest()
    finally:
        conn.close()


# --- Full scan (§5 steps 1-2) -------------------------------------------------


@spacy
def test_reads_meta(store):
    assert store.meta["schema_version"] == "1"
    assert store.meta["language"] == "ru"
    assert store.meta["word_count"] == "31"


@spacy
def test_reads_all_blocks_in_order(store):
    assert store.blocks == (
        Block(id=1, type="paragraph"),
        Block(id=2, type="paragraph"),
        Block(id=3, type="dialogue"),
        Block(id=4, type="paragraph"),
    )


@spacy
def test_reads_all_sentences_in_reading_order(store):
    assert [(s.id, s.block_id, s.seq, s.text) for s in store.sentences] == [
        (1, 1, 0, "Глава 1"),
        (2, 2, 0, "Он вышел из дома, хотя шёл дождь."),
        (3, 2, 1, "На улице было пусто."),
        (4, 3, 0, "— Привет, — сказал он и улыбнулся."),
        (5, 4, 0, "Мы долго гуляли по парку и разговаривали о книгах."),
        (6, 4, 1, "Вечером мы вернулись домой."),
    ]


@spacy
def test_decodes_blobs_into_model(store):
    sentence = store.sentences[3]

    assert isinstance(sentence, Sentence)
    assert sentence.candidates == (
        SplitCandidate(token_index=4, weight=1.0),
        SplitCandidate(token_index=6, weight=0.8),
    )
    # "— Привет, — сказал он и улыбнулся." tokenized as in the candidate golden
    assert [sentence.text[s:e] for s, e in sentence.tokens] == [
        "—", "Привет", ",", "—", "сказал", "он", "и", "улыбнулся", ".",
    ]  # fmt: skip
    assert all(isinstance(span, tuple) for span in sentence.tokens)


# --- Reader state (§3 reader_state, §5 step 3) --------------------------------


@spacy
def test_position_defaults_to_first_sentence_token_zero(store):
    assert store.load_position() == Position(sentence_id=1, chunk_start_token=0)


@spacy
def test_position_persists_across_reopen_as_spec_json(book_path):
    with BookStore.open(book_path) as s:
        s.save_position(Position(sentence_id=4, chunk_start_token=3))

    with BookStore.open(book_path) as s:
        assert s.load_position() == Position(sentence_id=4, chunk_start_token=3)

    conn = sqlite3.connect(book_path)
    try:
        (raw,) = conn.execute(
            "SELECT value FROM reader_state WHERE key = 'position'"
        ).fetchone()
    finally:
        conn.close()
    assert json.loads(raw) == {"sentence_id": 4, "chunk_start_token": 3}


@spacy
def test_absent_setting_is_none(store):
    assert store.load_setting("chunk_width") is None


@spacy
def test_setting_persists_across_reopen_and_last_write_wins(book_path):
    with BookStore.open(book_path) as s:
        s.save_setting("chunk_width", "10")
        s.save_setting("chunk_width", "6")
        s.save_setting("theme", "light")

    with BookStore.open(book_path) as s:
        assert s.load_setting("chunk_width") == "6"
        assert s.load_setting("theme") == "light"


# --- Isolation & lifecycle (D8) ------------------------------------------------


@spacy
def test_state_writes_leave_content_tables_untouched(book_path):
    before = content_digest(book_path)

    with BookStore.open(book_path) as s:
        s.save_position(Position(sentence_id=2, chunk_start_token=5))
        s.save_setting("chunk_width", "12")

    assert content_digest(book_path) == before


@spacy
def test_close_leaves_a_single_file(book_path):
    with BookStore.open(book_path) as s:
        s.save_position(Position(sentence_id=2, chunk_start_token=5))

    assert sorted(p.name for p in book_path.parent.iterdir()) == ["book.kert"]


# --- Rejection (§5 step 1) ------------------------------------------------------


@spacy
def test_rejects_unsupported_schema_version(book_path):
    conn = sqlite3.connect(book_path)
    with conn:
        conn.execute("UPDATE meta SET value = '2' WHERE key = 'schema_version'")
    conn.close()

    with pytest.raises(KertError, match="schema version 2"):
        BookStore.open(book_path)


def test_missing_file_is_user_error_and_is_not_created(tmp_path):
    path = tmp_path / "missing.kert"

    with pytest.raises(KertError):
        BookStore.open(path)

    assert not path.exists()
