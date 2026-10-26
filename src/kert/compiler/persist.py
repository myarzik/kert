import sqlite3
from collections.abc import Mapping, Sequence
from pathlib import Path

import msgpack

from kert.common.dbschema import create_schema
from kert.common.model import Block, Sentence


def write_book(
    path: Path,
    meta: Mapping[str, str],
    blocks: Sequence[Block],
    sentences: Sequence[Sentence],
) -> None:
    """Create a new `.kert` file and write all content in one transaction (§4.6)."""
    if path.exists():
        raise FileExistsError(path)
    conn = sqlite3.connect(path)
    try:
        create_schema(conn)
        with conn:
            conn.executemany(
                "INSERT INTO meta (key, value) VALUES (?, ?)", meta.items()
            )
            conn.executemany(
                "INSERT INTO blocks (id, type, chapter) VALUES (?, ?, ?)",
                ((b.id, b.type, b.chapter) for b in blocks),
            )
            conn.executemany(
                "INSERT INTO sentences (id, block_id, seq, text, tokens, candidates) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    (
                        s.id,
                        s.block_id,
                        s.seq,
                        s.text,
                        msgpack.packb(s.tokens),
                        msgpack.packb(
                            [(c.token_index, c.weight) for c in s.candidates]
                        ),
                    )
                    for s in sentences
                ),
            )
    finally:
        conn.close()
