import sqlite3

SCHEMA_VERSION = "1"

DDL = """
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- Immutable after compilation ------------------------------------------

CREATE TABLE meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE blocks (
    id      INTEGER PRIMARY KEY,
    type    TEXT NOT NULL CHECK (type IN
            ('paragraph','dialogue','heading','code','list_item')),
    chapter INTEGER
);

CREATE TABLE sentences (
    id            INTEGER PRIMARY KEY,
    block_id      INTEGER NOT NULL REFERENCES blocks(id),
    seq           INTEGER NOT NULL,
    text          TEXT NOT NULL,
    tokens        BLOB NOT NULL,
    candidates    BLOB NOT NULL
);
CREATE INDEX idx_sentences_block ON sentences(block_id, seq);

-- Mutable reader state ---------------------------------------------------

CREATE TABLE reader_state (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE advance_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          REAL NOT NULL,
    sentence_id INTEGER NOT NULL,
    chunk_words INTEGER NOT NULL,
    direction   INTEGER NOT NULL
);
"""


def create_schema(conn: sqlite3.Connection) -> None:
    """Create the `.kert` schema (spec §3) on an empty database."""
    conn.executescript(DDL)
