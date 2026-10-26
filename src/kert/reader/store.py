"""Reader-side `.kert` access: one full scan at open, isolated state writes (§5, D8)."""

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Self

import msgpack

from kert.common.dbschema import SCHEMA_VERSION
from kert.common.errors import KertError
from kert.common.model import Block, Sentence, SplitCandidate


@dataclass(frozen=True, slots=True)
class Position:
    sentence_id: int
    chunk_start_token: int


class BookStore:
    def __init__(
        self,
        conn: sqlite3.Connection,
        meta: dict[str, str],
        blocks: tuple[Block, ...],
        sentences: tuple[Sentence, ...],
    ) -> None:
        self._conn = conn
        self.meta = meta
        self.blocks = blocks
        self.sentences = sentences

    @classmethod
    def open(cls, path: Path) -> Self:
        try:
            # mode=rw: never create a missing file.
            conn = sqlite3.connect(f"{path.resolve().as_uri()}?mode=rw", uri=True)
        except sqlite3.OperationalError as exc:
            raise KertError(f"Cannot open {path}: {exc}.") from exc
        try:
            meta = dict(conn.execute("SELECT key, value FROM meta"))
            schema_version = meta.get("schema_version")
            if schema_version != SCHEMA_VERSION:
                raise KertError(
                    f"{path} has schema version {schema_version}; this kert reads "
                    f"version {SCHEMA_VERSION}. Recompile the book."
                )
            blocks = tuple(
                Block(id=row[0], type=row[1], chapter=row[2])
                for row in conn.execute(
                    "SELECT id, type, chapter FROM blocks ORDER BY id"
                )
            )
            sentences = tuple(
                Sentence(
                    id=row[0],
                    block_id=row[1],
                    seq=row[2],
                    text=row[3],
                    tokens=msgpack.unpackb(row[4], use_list=False),
                    candidates=tuple(
                        SplitCandidate(token_index=i, weight=w)
                        for i, w in msgpack.unpackb(row[5], use_list=False)
                    ),
                )
                for row in conn.execute(
                    "SELECT id, block_id, seq, text, tokens, candidates "
                    "FROM sentences ORDER BY id"
                )
            )
        except BaseException:
            conn.close()
            raise
        return cls(conn, meta, blocks, sentences)

    def load_position(self) -> Position:
        raw = self.load_setting("position")
        if raw is None:
            return Position(sentence_id=self.sentences[0].id, chunk_start_token=0)
        return Position(**json.loads(raw))

    def save_position(self, position: Position) -> None:
        self.save_setting(
            "position",
            json.dumps(
                {
                    "sentence_id": position.sentence_id,
                    "chunk_start_token": position.chunk_start_token,
                }
            ),
        )

    def load_setting(self, key: str) -> str | None:
        row = self._conn.execute(
            "SELECT value FROM reader_state WHERE key = ?", (key,)
        ).fetchone()
        return None if row is None else row[0]

    def save_setting(self, key: str, value: str) -> None:
        with self._conn:
            self._conn.execute(
                "INSERT INTO reader_state (key, value) VALUES (?, ?) "
                "ON CONFLICT (key) DO UPDATE SET value = excluded.value",
                (key, value),
            )

    def log_advance(
        self, ts: float, sentence_id: int, chunk_words: int, direction: int
    ) -> None:
        raise NotImplementedError

    def trim_advance_log(self, keep: int) -> None:
        raise NotImplementedError

    def close(self) -> None:
        # Fold the WAL back so the .kert stays a single portable file.
        self._conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        self._conn.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()
