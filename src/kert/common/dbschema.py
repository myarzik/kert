import sqlite3

SCHEMA_VERSION = "1"

# §17.8; also created on open in books compiled before it (§17.4).
CHECKPOINTS_DDL = """
CREATE TABLE IF NOT EXISTS checkpoints (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    ts                   REAL    NOT NULL,
    trigger              TEXT    NOT NULL
                         CHECK (trigger IN ('open','goal','quit','heading')),
    mode                 TEXT    NOT NULL
                         CHECK (mode IN ('chunk','sentence','paragraph')),
    span_start_sentence  INTEGER NOT NULL,
    span_end_sentence    INTEGER NOT NULL,
    span_words           INTEGER NOT NULL,
    recall_text          TEXT,
    self_rating          INTEGER CHECK (self_rating IN (0,1,2))
);
"""

# §17.4: columns added to the advance_log of books compiled before them.
_ADVANCE_LOG_COLUMNS = {
    "kind": "kind TEXT NOT NULL DEFAULT 'step' "
    "CHECK (kind IN ('step','sentence','block','jump','peek'))",
    "mode": "mode TEXT NOT NULL DEFAULT 'chunk' "
    "CHECK (mode IN ('chunk','sentence','paragraph'))",
}

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
    direction   INTEGER NOT NULL,
    kind        TEXT    NOT NULL DEFAULT 'step'
                CHECK (kind IN ('step','sentence','block','jump','peek')),
    mode        TEXT    NOT NULL DEFAULT 'chunk'
                CHECK (mode IN ('chunk','sentence','paragraph'))
);
"""


def create_schema(conn: sqlite3.Connection) -> None:
    """Create the `.kert` schema (spec §3) on an empty database."""
    conn.executescript(DDL + CHECKPOINTS_DDL)


def upgrade_state_tables(conn: sqlite3.Connection) -> None:
    """Bring a 0.1/0.2 book's mutable tables up to §17.4; idempotent.

    Content tables are untouched, so `schema_version` stays the same.
    """
    present = {row[1] for row in conn.execute("PRAGMA table_info(advance_log)")}
    with conn:
        for name, definition in _ADVANCE_LOG_COLUMNS.items():
            if name not in present:
                conn.execute(f"ALTER TABLE advance_log ADD COLUMN {definition}")
        conn.execute(CHECKPOINTS_DDL)
