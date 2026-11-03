"""§10.4: compile → open → assemble → navigate → quit → reopen (spec §5, D8)."""

import sqlite3

import pytest
from readchar import key
from test_store import advance_rows, content_digest

from kert.cli import main
from kert.reader.app import ADVANCE_LOG_CAP, close_session, feed, open_session
from kert.reader.config import load_global
from kert.reader.store import Position

pytestmark = pytest.mark.spacy

# Hand-derived from §6 for tests/fixtures/book_ru.txt. At W=8 every sentence has
# n <= W+2 and is one chunk. At W=6 (n > 8 needs DP):
#   S2 n=9, C={2:0.4, 5:1.0}: {5} 0.028+0.111=0.139 beats {} 0.25,
#      {2} 1.444+0.028+0.45=1.922, {2,5} 2.255
#   S4 n=9: {4} 0.139 (golden in test_inspect); S5 n=10: {5} 0.206 (test_chunker)
GOLDEN_W8 = [
    "Глава 1",
    "Он вышел из дома, хотя шёл дождь.",
    "На улице было пусто.",
    "— Привет, — сказал он и улыбнулся.",
    "Мы долго гуляли по парку и разговаривали о книгах.",
    "Вечером мы вернулись домой.",
]
GOLDEN_W6 = [
    "Глава 1",
    "Он вышел из дома,",
    "хотя шёл дождь.",
    "На улице было пусто.",
    "— Привет, —",
    "сказал он и улыбнулся.",
    "Мы долго гуляли по парку",
    "и разговаривали о книгах.",
    "Вечером мы вернулись домой.",
]


@pytest.fixture
def toml(tmp_path_factory):
    # Outside the book's directory: :set creates it (§8.4 write-through).
    return tmp_path_factory.mktemp("config") / "kert" / "config.toml"


def chunk_texts(state):
    by_id = {s.id: s for s in state.book.sentences}
    texts = []
    for span in state.chunks.spans:
        sentence = by_id[span.sentence_id]
        start = sentence.tokens[span.start_token][0]
        end = sentence.tokens[span.end_token - 1][1]
        texts.append(sentence.text[start:end])
    return texts


def type_keys(store, state, keys, toml, clock):
    for k in keys:
        state = feed(store, state, k, config_file=toml, now=clock)
    return state


def test_open_assembles_golden_chunks_at_default_width(book_path, toml):
    store, state = open_session(book_path, config_file=toml)
    try:
        assert state.settings.chunk_width == 8
        assert chunk_texts(state) == GOLDEN_W8
        assert state.index == 0
    finally:
        store.close()


def test_open_uses_global_toml_width(book_path, toml):
    toml.parent.mkdir(parents=True)
    toml.write_text("chunk_width = 6\n", encoding="utf-8")

    store, state = open_session(book_path, config_file=toml)
    try:
        assert chunk_texts(state) == GOLDEN_W6
    finally:
        store.close()


def test_full_session_roundtrip(book_path, toml):
    before = content_digest(book_path)
    ticks = iter(range(100, 200))

    def clock():
        return float(next(ticks))

    store, state = open_session(book_path, size=(60, 20), config_file=toml)
    state = type_keys(
        store, state, [":", *"set width=6", key.ENTER, "j", "j", "j", "j", "k", "j"],
        toml, clock,
    )  # fmt: skip
    assert chunk_texts(state) == GOLDEN_W6
    assert state.index == 4
    state = type_keys(store, state, ["q"], toml, clock)
    assert state.quit
    close_session(store, state)

    # Words of the chunk left (§3): Глава 1=2, Он вышел из дома ,=4,
    # хотя шёл дождь .=3, На улице было пусто .=4, — Привет , —=1.
    assert advance_rows(book_path) == [
        (100.0, 1, 2, 1, "step", "chunk"),
        (101.0, 2, 4, 1, "step", "chunk"),
        (102.0, 2, 3, 1, "step", "chunk"),
        (103.0, 3, 4, 1, "step", "chunk"),
        (104.0, 4, 1, -1, "step", "chunk"),
        (105.0, 3, 4, 1, "step", "chunk"),
    ]
    assert content_digest(book_path) == before
    assert sorted(p.name for p in book_path.parent.iterdir()) == ["book.kert"]
    assert load_global(toml).chunk_width == 6  # :set writes the global layer too

    store, state = open_session(book_path, config_file=toml.with_name("other.toml"))
    try:
        # Per-book reader_state wins without any TOML (§8.4).
        assert state.settings.chunk_width == 6
        assert state.position == Position(sentence_id=4, chunk_start_token=0)
        assert chunk_texts(state)[state.index] == "— Привет, —"
    finally:
        store.close()


def test_resumes_inside_a_sentence_at_new_width(book_path, toml):
    # W=6 position S2 token 5 ("хотя…"); reopened at W=8 → S2's only chunk.
    store, state = open_session(book_path, config_file=toml)
    state = type_keys(
        store, state, [":", *"set width=6", key.ENTER, "j", "j"], toml, lambda: 1.0
    )
    close_session(store, state)
    store, state = open_session(book_path, config_file=toml)
    state = type_keys(store, state, [":", *"set width=8", key.ENTER], toml, lambda: 1.0)
    assert state.index == 1
    close_session(store, state)

    store, state = open_session(book_path, config_file=toml)
    try:
        assert state.position == Position(sentence_id=2, chunk_start_token=0)
    finally:
        store.close()


def test_advance_log_is_capped_on_close(book_path, toml):
    conn = sqlite3.connect(book_path)
    with conn:
        conn.executemany(
            "INSERT INTO advance_log (ts, sentence_id, chunk_words, direction) "
            "VALUES (?, 1, 0, 1)",
            [(float(i),) for i in range(ADVANCE_LOG_CAP)],
        )
    conn.close()

    store, state = open_session(book_path, config_file=toml)
    state = type_keys(store, state, ["j", "j"], toml, lambda: 99999.0)
    close_session(store, state)

    rows = advance_rows(book_path)
    assert ADVANCE_LOG_CAP == 10_000
    assert len(rows) == ADVANCE_LOG_CAP
    assert rows[0][0] == 2.0  # the two oldest rows were dropped
    assert rows[-2:] == [
        (99999.0, 1, 2, 1, "step", "chunk"),
        (99999.0, 2, 7, 1, "step", "chunk"),
    ]


def test_settings_feedback_is_not_logged_as_advance(book_path, toml):
    store, state = open_session(book_path, config_file=toml)
    state = type_keys(
        store, state, [":", *"set theme=light", key.ENTER], toml, lambda: 1.0
    )
    close_session(store, state)

    assert advance_rows(book_path) == []
    store, state = open_session(book_path, config_file=toml)
    try:
        assert state.settings.theme == "light"
    finally:
        store.close()


def test_each_move_is_logged_with_its_kind(book_path, toml):
    # §17.4 at W=8 each sentence is one chunk; blocks: S1 | S2 S3 | S4 | S5 S6.
    store, state = open_session(book_path, config_file=toml)
    keys = ["J", "j", "(", ")", "p", "x", "G", "g", "g"]
    state = type_keys(store, state, keys, toml, lambda: 1.0)
    close_session(store, state)

    assert [(row[3], row[4], row[5]) for row in advance_rows(book_path)] == [
        (1, "block", "chunk"),
        (1, "step", "chunk"),
        (-1, "sentence", "chunk"),
        (1, "sentence", "chunk"),
        (0, "peek", "chunk"),
        (1, "jump", "chunk"),
        (-1, "jump", "chunk"),
    ]


def test_moves_are_logged_with_the_mode_in_force(book_path, toml):
    store, state = open_session(book_path, config_file=toml)
    keys = ["j", ":", *"set mode=paragraph", key.ENTER, "j"]
    state = type_keys(store, state, keys, toml, lambda: 1.0)
    close_session(store, state)

    # S1 (2 words) as a chunk, then block 2 (S2 + S3 = 11 words) as a paragraph.
    assert [(row[2], row[5]) for row in advance_rows(book_path)] == [
        (2, "chunk"),
        (11, "paragraph"),
    ]
    store, state = open_session(book_path, config_file=toml)
    try:
        assert state.settings.mode == "paragraph"
        assert load_global(toml).mode == "chunk"
    finally:
        store.close()


def test_cli_read_missing_book_is_user_error(tmp_path):
    assert main(["read", str(tmp_path / "missing.kert")]) == 1
