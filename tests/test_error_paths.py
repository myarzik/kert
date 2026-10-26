"""Task 10 error-path hardening (spec §9 exit codes, §5, §7.1, §8.3)."""

import io
import sqlite3

import msgpack
import pytest
from rich.console import Console

from kert.cli import main
from kert.common.errors import KertError
from kert.compiler import segment
from kert.reader.app import open_session, run
from kert.reader.store import BookStore, Position

FIXTURE = "tests/fixtures/book_ru.txt"


# --- Missing spaCy model (§2.1, §9: exit 1 with an actionable message) ----------------


@pytest.fixture
def no_models(monkeypatch):
    def missing(name, **kwargs):
        raise OSError(f"[E050] Can't find model '{name}'.")

    monkeypatch.setattr(segment.spacy, "load", missing)


@pytest.mark.parametrize(
    ("lang", "model"), [("ru", "ru_core_news_sm"), ("en", "en_core_web_sm")]
)
def test_missing_model_is_user_error_with_remediation(no_models, lang, model):
    with pytest.raises(KertError) as exc:
        segment.load_model(lang)

    assert model in str(exc.value)
    assert "uv sync --group models" in str(exc.value)


def test_compile_with_missing_model_exits_1_and_writes_nothing(
    no_models, tmp_path, capsys
):
    out = tmp_path / "book.kert"

    code = main(["compile", FIXTURE, "-o", str(out), "--lang", "ru"])

    assert code == 1
    assert "uv sync --group models" in capsys.readouterr().err
    assert list(tmp_path.iterdir()) == []


# --- Corrupt .kert (§5 step 1: refuse politely) ---------------------------------------


def write_bytes(tmp_path, data):
    path = tmp_path / "bad.kert"
    path.write_bytes(data)
    return path


@pytest.fixture(params=["garbage", "empty-file", "foreign-sqlite"])
def corrupt_book(request, tmp_path):
    if request.param == "garbage":
        return write_bytes(tmp_path, b"this is not a database at all" * 100)
    if request.param == "empty-file":
        return write_bytes(tmp_path, b"")
    path = tmp_path / "bad.kert"
    conn = sqlite3.connect(path)
    with conn:
        conn.execute("CREATE TABLE notes (x TEXT)")
    conn.close()
    return path


def test_corrupt_book_is_user_error(corrupt_book):
    with pytest.raises(KertError, match=r"not a valid \.kert"):
        BookStore.open(corrupt_book)


@pytest.mark.parametrize("command", ["read", "inspect"])
def test_cli_on_corrupt_book_exits_1(corrupt_book, capsys, command):
    assert main([command, str(corrupt_book)]) == 1
    assert "not a valid .kert" in capsys.readouterr().err


def break_book(path, sql, *params):
    conn = sqlite3.connect(path)
    with conn:
        conn.execute(sql, params)
    conn.close()


@pytest.mark.spacy
@pytest.mark.parametrize(
    ("sql", "params"),
    [
        ("UPDATE sentences SET tokens = ? WHERE id = 2", (b"\xc1\xc1\xc1",)),
        ("UPDATE sentences SET candidates = ? WHERE id = 2", (b"\x93",)),
        ("UPDATE sentences SET candidates = ? WHERE id = 2", (msgpack.packb([1]),)),
        ("DROP TABLE sentences", ()),
    ],
    ids=["bad-tokens-blob", "truncated-candidates", "wrong-shape", "missing-table"],
)
def test_damaged_compiled_book_is_user_error(book_path, sql, params):
    break_book(book_path, sql, *params)

    with pytest.raises(KertError, match=r"not a valid \.kert"):
        BookStore.open(book_path)


@pytest.mark.spacy
@pytest.mark.parametrize("value", [None, "many"])
def test_missing_or_bad_word_count_is_user_error(book_path, value):
    if value is None:
        break_book(book_path, "DELETE FROM meta WHERE key = 'word_count'")
    else:
        break_book(
            book_path, "UPDATE meta SET value = ? WHERE key = 'word_count'", value
        )

    with pytest.raises(KertError, match=r"not a valid \.kert"):
        open_session(book_path)


def test_book_without_text_is_user_error(tmp_path):
    # The compiler accepts an empty .txt (0 blocks); the Reader has nothing to show.
    from kert.common.dbschema import create_schema

    path = tmp_path / "empty.kert"
    conn = sqlite3.connect(path)
    create_schema(conn)
    with conn:
        conn.executemany(
            "INSERT INTO meta (key, value) VALUES (?, ?)",
            [("schema_version", "1"), ("word_count", "0")],
        )
    conn.close()

    with pytest.raises(KertError, match="no text"):
        open_session(path)


# --- Ctrl+C = quit with save (§5 on exit, §8.3) ---------------------------------------


def scripted_keys(*keys):
    """read_key stand-in: yields `keys`, then Ctrl+C as readchar raises it."""
    it = iter(keys)

    def read_key():
        try:
            return next(it)
        except StopIteration:
            raise KeyboardInterrupt from None

    return read_key


def quiet_console():
    return Console(file=io.StringIO(), width=60, height=20, force_terminal=True)


@pytest.mark.spacy
def test_ctrl_c_saves_position_and_returns_normally(book_path, tmp_path):
    run(
        book_path,
        read_key=scripted_keys("j", "j"),
        console=quiet_console(),
        config_file=tmp_path / "config.toml",
    )

    with BookStore.open(book_path) as store:
        assert store.load_position() == Position(sentence_id=3, chunk_start_token=0)
    assert sorted(p.name for p in book_path.parent.iterdir()) == ["book.kert"]


@pytest.mark.spacy
def test_ctrl_c_while_handling_a_key_still_saves(book_path, tmp_path, monkeypatch):
    from kert.reader import app

    real_feed = app.feed
    calls = []

    def interrupted_feed(*args, **kwargs):
        calls.append(1)
        if len(calls) == 2:
            raise KeyboardInterrupt
        return real_feed(*args, **kwargs)

    monkeypatch.setattr(app, "feed", interrupted_feed)

    run(
        book_path,
        read_key=scripted_keys("j", "j", "j"),
        console=quiet_console(),
        config_file=tmp_path / "config.toml",
    )

    with BookStore.open(book_path) as store:
        assert store.load_position() == Position(sentence_id=2, chunk_start_token=0)


@pytest.mark.spacy
def test_q_quits_through_run(book_path, tmp_path):
    run(
        book_path,
        read_key=scripted_keys("j", "q", "j"),  # keys after q are never read
        console=quiet_console(),
        config_file=tmp_path / "config.toml",
    )

    with BookStore.open(book_path) as store:
        assert store.load_position() == Position(sentence_id=2, chunk_start_token=0)
