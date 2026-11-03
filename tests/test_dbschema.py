import sqlite3

import pytest

from kert.common.dbschema import SCHEMA_VERSION, create_schema, upgrade_state_tables

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
        ("kind", "TEXT", 1, 0),
        ("mode", "TEXT", 1, 0),
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


# --- §17.4: advance_log kind/mode, checkpoints, migration of 0.1/0.2 books ----------

LEGACY_ADVANCE_LOG = """
CREATE TABLE advance_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          REAL NOT NULL,
    sentence_id INTEGER NOT NULL,
    chunk_words INTEGER NOT NULL,
    direction   INTEGER NOT NULL
);
"""


def make_legacy(conn):
    """Turn a fresh schema into the 0.2 state tables (§3 before §17)."""
    conn.executescript(
        "DROP TABLE checkpoints; DROP TABLE advance_log;" + LEGACY_ADVANCE_LOG
    )


def insert_advance(conn, **extra):
    names = ", ".join(["ts", "sentence_id", "chunk_words", "direction", *extra])
    marks = ", ".join("?" * (4 + len(extra)))
    conn.execute(
        f"INSERT INTO advance_log ({names}) VALUES ({marks})",
        (1.0, 1, 3, 1, *extra.values()),
    )


def test_four_column_insert_defaults_to_a_chunk_step(conn):
    # Readers that predate §17 (Android 0.2) insert only the original columns.
    insert_advance(conn)

    assert conn.execute("SELECT kind, mode FROM advance_log").fetchall() == [
        ("step", "chunk")
    ]


@pytest.mark.parametrize("kind", ["step", "sentence", "block", "jump", "peek"])
@pytest.mark.parametrize("mode", ["chunk", "sentence", "paragraph"])
def test_advance_log_accepts_known_kinds_and_modes(conn, kind, mode):
    insert_advance(conn, kind=kind, mode=mode)


@pytest.mark.parametrize(("kind", "mode"), [("chunk", "chunk"), ("step", "plain")])
def test_advance_log_rejects_unknown_kind_or_mode(conn, kind, mode):
    with pytest.raises(sqlite3.IntegrityError):
        insert_advance(conn, kind=kind, mode=mode)


def test_checkpoints_columns(conn):
    assert columns(conn, "checkpoints") == [
        ("id", "INTEGER", 0, 1),
        ("ts", "REAL", 1, 0),
        ("trigger", "TEXT", 1, 0),
        ("mode", "TEXT", 1, 0),
        ("span_start_sentence", "INTEGER", 1, 0),
        ("span_end_sentence", "INTEGER", 1, 0),
        ("span_words", "INTEGER", 1, 0),
        ("recall_text", "TEXT", 0, 0),
        ("self_rating", "INTEGER", 0, 0),
    ]


def insert_checkpoint(conn, trigger="goal", mode="chunk", rating=None):
    conn.execute(
        "INSERT INTO checkpoints (ts, trigger, mode, span_start_sentence, "
        "span_end_sentence, span_words, recall_text, self_rating) "
        "VALUES (1.0, ?, ?, 1, 2, 40, NULL, ?)",
        (trigger, mode, rating),
    )


@pytest.mark.parametrize("trigger", ["open", "goal", "quit", "heading"])
@pytest.mark.parametrize("rating", [None, 0, 1, 2])
def test_checkpoints_accept_known_triggers_and_ratings(conn, trigger, rating):
    insert_checkpoint(conn, trigger=trigger, rating=rating)


@pytest.mark.parametrize(
    ("trigger", "mode", "rating"),
    [("exit", "chunk", None), ("goal", "plain", None), ("goal", "chunk", 3)],
)
def test_checkpoints_reject_unknown_values(conn, trigger, mode, rating):
    with pytest.raises(sqlite3.IntegrityError):
        insert_checkpoint(conn, trigger=trigger, mode=mode, rating=rating)


def test_upgrade_adds_columns_with_defaults_for_old_rows(conn):
    make_legacy(conn)
    insert_advance(conn)

    upgrade_state_tables(conn)

    assert conn.execute("SELECT kind, mode FROM advance_log").fetchall() == [
        ("step", "chunk")
    ]
    insert_advance(conn, kind="peek", mode="sentence")
    with pytest.raises(sqlite3.IntegrityError):
        insert_advance(conn, kind="bogus")


def test_upgrade_creates_checkpoints(conn):
    make_legacy(conn)

    upgrade_state_tables(conn)

    insert_checkpoint(conn)


def test_upgrade_is_idempotent_and_keeps_a_current_schema_unchanged(conn):
    def schema():
        return conn.execute(
            "SELECT name, sql FROM sqlite_master ORDER BY name"
        ).fetchall()

    before = schema()
    upgrade_state_tables(conn)
    upgrade_state_tables(conn)

    assert schema() == before
