import sqlite3

import pytest

from kert.common.dbschema import SCHEMA_VERSION, create_schema

BLOCK_TYPES = ["paragraph", "dialogue", "heading", "code", "list_item"]


@pytest.fixture
def conn(tmp_path):
    connection = sqlite3.connect(tmp_path / "book.kert")
    create_schema(connection)
    yield connection
    connection.close()


def columns(conn, table):
    # (name, declared type, notnull, pk) per column, in declaration order
    return [
        (row[1], row[2], row[3], row[5])
        for row in conn.execute(f"PRAGMA table_info({table})")
    ]


def test_schema_version_is_one():
    assert SCHEMA_VERSION == "1"


def test_creates_all_tables(conn):
    tables = {
        row[0]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    }

    assert {"meta", "blocks", "sentences", "reader_state", "advance_log"} <= tables


@pytest.mark.parametrize("table", ["meta", "reader_state"])
def test_key_value_tables(conn, table):
    assert columns(conn, table) == [
        ("key", "TEXT", 0, 1),
        ("value", "TEXT", 1, 0),
    ]


def test_blocks_columns(conn):
    assert columns(conn, "blocks") == [
        ("id", "INTEGER", 0, 1),
        ("type", "TEXT", 1, 0),
        ("chapter", "INTEGER", 0, 0),
    ]


def test_sentences_columns(conn):
    assert columns(conn, "sentences") == [
        ("id", "INTEGER", 0, 1),
        ("block_id", "INTEGER", 1, 0),
        ("seq", "INTEGER", 1, 0),
        ("text", "TEXT", 1, 0),
        ("tokens", "BLOB", 1, 0),
        ("candidates", "BLOB", 1, 0),
    ]


def test_advance_log_columns(conn):
    assert columns(conn, "advance_log") == [
        ("id", "INTEGER", 0, 1),
        ("ts", "REAL", 1, 0),
        ("sentence_id", "INTEGER", 1, 0),
        ("chunk_words", "INTEGER", 1, 0),
        ("direction", "INTEGER", 1, 0),
    ]


def test_advance_log_id_is_autoincrement(conn):
    (sql,) = conn.execute(
        "SELECT sql FROM sqlite_master WHERE name = 'advance_log'"
    ).fetchone()

    assert "AUTOINCREMENT" in sql.upper()


def test_sentences_index_on_block_and_seq(conn):
    index_columns = [
        row[2] for row in conn.execute("PRAGMA index_info(idx_sentences_block)")
    ]

    assert index_columns == ["block_id", "seq"]


def test_sentences_block_id_references_blocks(conn):
    fks = [
        (row[2], row[3], row[4])
        for row in conn.execute("PRAGMA foreign_key_list(sentences)")
    ]

    assert fks == [("blocks", "block_id", "id")]


@pytest.mark.parametrize("block_type", BLOCK_TYPES)
def test_check_accepts_known_block_types(conn, block_type):
    conn.execute("INSERT INTO blocks (id, type) VALUES (1, ?)", (block_type,))


@pytest.mark.parametrize("block_type", ["chapter", "Paragraph", ""])
def test_check_rejects_unknown_block_types(conn, block_type):
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO blocks (id, type) VALUES (1, ?)", (block_type,))


def test_foreign_keys_enforced(conn):
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO sentences (id, block_id, seq, text, tokens, candidates) "
            "VALUES (1, 99, 0, 'x', x'90', x'90')"
        )


def test_journal_mode_is_wal_and_persists(conn, tmp_path):
    assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"

    conn.close()
    reopened = sqlite3.connect(tmp_path / "book.kert")
    try:
        assert reopened.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    finally:
        reopened.close()
