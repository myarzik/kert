import sqlite3

import msgpack
import pytest

from kert.common.model import Block, Sentence, SplitCandidate
from kert.compiler.persist import write_book

META = {"schema_version": "1", "title": "t", "language": "en"}
BLOCKS = [Block(id=1, type="paragraph"), Block(id=2, type="dialogue")]
SENTENCES = [
    Sentence(
        id=1,
        block_id=1,
        seq=0,
        text="Hi there.",
        tokens=((0, 2), (3, 8), (8, 9)),
        candidates=(SplitCandidate(token_index=1, weight=0.4),),
    ),
    Sentence(
        id=2,
        block_id=2,
        seq=0,
        text="— Yes.",
        tokens=((0, 1), (2, 5), (5, 6)),
        candidates=(),
    ),
]


@pytest.fixture
def book(tmp_path):
    path = tmp_path / "book.kert"
    write_book(path, META, BLOCKS, SENTENCES)
    conn = sqlite3.connect(path)
    yield conn
    conn.close()


def test_writes_meta(book):
    assert dict(book.execute("SELECT key, value FROM meta")) == META


def test_writes_blocks(book):
    rows = book.execute("SELECT id, type, chapter FROM blocks ORDER BY id").fetchall()

    assert rows == [(1, "paragraph", None), (2, "dialogue", None)]


def test_writes_sentence_rows(book):
    rows = book.execute(
        "SELECT id, block_id, seq, text FROM sentences ORDER BY id"
    ).fetchall()

    assert rows == [(1, 1, 0, "Hi there."), (2, 2, 0, "— Yes.")]


def test_tokens_and_candidates_are_msgpack_lists(book):
    rows = book.execute(
        "SELECT tokens, candidates FROM sentences ORDER BY id"
    ).fetchall()
    decoded = [(msgpack.unpackb(t), msgpack.unpackb(c)) for t, c in rows]

    assert decoded == [
        ([[0, 2], [3, 8], [8, 9]], [[1, 0.4]]),
        ([[0, 1], [2, 5], [5, 6]], []),
    ]


def test_mutable_tables_left_empty(book):
    assert book.execute("SELECT COUNT(*) FROM reader_state").fetchone() == (0,)
    assert book.execute("SELECT COUNT(*) FROM advance_log").fetchone() == (0,)


def test_no_wal_sidecars_after_write(tmp_path):
    path = tmp_path / "book.kert"

    write_book(path, META, BLOCKS, SENTENCES)

    assert sorted(p.name for p in tmp_path.iterdir()) == ["book.kert"]


def test_single_transaction_rolls_back_on_failure(tmp_path):
    path = tmp_path / "book.kert"
    orphan = Sentence(
        id=3, block_id=99, seq=0, text="x", tokens=((0, 1),), candidates=()
    )

    with pytest.raises(sqlite3.IntegrityError):
        write_book(path, META, BLOCKS, [*SENTENCES, orphan])

    conn = sqlite3.connect(path)
    try:
        for table in ("meta", "blocks", "sentences"):
            assert conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone() == (0,)
    finally:
        conn.close()


def test_refuses_existing_path(tmp_path):
    path = tmp_path / "book.kert"
    path.write_bytes(b"original")

    with pytest.raises(FileExistsError):
        write_book(path, META, BLOCKS, SENTENCES)

    assert path.read_bytes() == b"original"
