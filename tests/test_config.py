import sys
import tomllib

import pytest

from kert.common.errors import KertError
from kert.reader import config
from kert.reader.config import HARDCODED, Settings, load_global, resolve, set_setting


class FakeBook:
    """reader_state stand-in: the load_setting/save_setting half of BookStore."""

    def __init__(self, **state):
        self.state = dict(state)

    def load_setting(self, key):
        return self.state.get(key)

    def save_setting(self, key, value):
        self.state[key] = value


@pytest.fixture
def toml(tmp_path):
    return tmp_path / "kert" / "config.toml"


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


# --- Location (§8.4) --------------------------------------------------------------


@pytest.mark.parametrize("platform", ["linux", "darwin"])
def test_config_path_is_xdg_on_linux_and_macos(monkeypatch, tmp_path, platform):
    monkeypatch.setattr(sys, "platform", platform)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))

    assert config.config_path() == tmp_path / "kert" / "config.toml"


@pytest.mark.skipif(sys.platform != "win32", reason="Windows known-folder lookup")
def test_config_path_is_roaming_appdata_on_windows(monkeypatch, tmp_path):
    monkeypatch.setenv("WIN_PD_OVERRIDE_APPDATA", str(tmp_path))

    assert config.config_path() == tmp_path / "kert" / "config.toml"


def test_load_global_defaults_to_config_path(monkeypatch, toml):
    monkeypatch.setattr(config, "config_path", lambda: toml)
    write(toml, "chunk_width = 10\n")

    assert load_global() == Settings(chunk_width=10, theme="dark")


# --- Global layer: TOML > hardcoded -------------------------------------------------


def test_hardcoded_defaults():
    assert Settings(chunk_width=8, theme="dark") == HARDCODED


def test_missing_file_falls_back_to_hardcoded(toml):
    assert load_global(toml) == HARDCODED


def test_toml_values_override_hardcoded(toml):
    write(toml, 'chunk_width = 6\ntheme = "light"\n')

    assert load_global(toml) == Settings(chunk_width=6, theme="light")


def test_absent_key_keeps_hardcoded(toml):
    write(toml, 'theme = "light"\n')

    assert load_global(toml) == Settings(chunk_width=8, theme="light")


@pytest.mark.parametrize(
    "text",
    [
        "chunk_width = = 6\n",  # syntax error
        "chunk_width = 6\nchunk_width = 7\n",  # duplicate key
        "",
    ],
)
def test_corrupt_toml_falls_back_to_hardcoded(toml, text):
    write(toml, text)

    assert load_global(toml) == HARDCODED


def test_non_utf8_toml_falls_back_to_hardcoded(toml):
    toml.parent.mkdir(parents=True)
    toml.write_bytes(b'theme = "\xff"\n')

    assert load_global(toml) == HARDCODED


def test_unreadable_path_falls_back_to_hardcoded(toml):
    toml.mkdir(parents=True)  # a directory where the file should be

    assert load_global(toml) == HARDCODED


@pytest.mark.parametrize("value", ["4", "13", '"8"', "true", "8.0"])
def test_invalid_toml_width_falls_back_alone(toml, value):
    write(toml, f'chunk_width = {value}\ntheme = "light"\n')

    assert load_global(toml) == Settings(chunk_width=8, theme="light")


@pytest.mark.parametrize("value", ['"blue"', "1"])
def test_invalid_toml_theme_falls_back_alone(toml, value):
    write(toml, f"chunk_width = 6\ntheme = {value}\n")

    assert load_global(toml) == Settings(chunk_width=6, theme="dark")


def test_unknown_toml_keys_are_ignored(toml):
    write(toml, "position = 5\nchunk_width = 9\n[other]\nx = 1\n")

    assert load_global(toml) == Settings(chunk_width=9, theme="dark")


# --- Per-book layer: reader_state > TOML > hardcoded ---------------------------------

GLOBAL = Settings(chunk_width=10, theme="light")


def test_empty_book_state_takes_global_layer():
    assert resolve(FakeBook(), GLOBAL) == GLOBAL


def test_book_state_overrides_global_layer():
    book = FakeBook(chunk_width="6", theme="dark")

    assert resolve(book, GLOBAL) == Settings(chunk_width=6, theme="dark")


def test_book_state_overrides_per_key():
    assert resolve(FakeBook(theme="dark"), GLOBAL) == Settings(10, "dark")


@pytest.mark.parametrize(
    "state", [{"chunk_width": "x"}, {"chunk_width": "99"}, {"theme": "blue"}]
)
def test_invalid_book_value_falls_through_to_global(state):
    assert resolve(FakeBook(**state), GLOBAL) == GLOBAL


def test_full_chain_with_missing_toml(toml):
    assert resolve(FakeBook(theme="light"), load_global(toml)) == Settings(8, "light")


# --- :set write-through to both layers ------------------------------------------


def test_set_writes_book_and_global_layers(toml):
    book = FakeBook()

    set_setting(book, "chunk_width", "6", toml)

    assert book.state == {"chunk_width": "6"}
    assert load_global(toml) == Settings(chunk_width=6, theme="dark")


def test_set_keeps_other_global_value(toml):
    write(toml, 'chunk_width = 10\ntheme = "dark"\n')

    set_setting(FakeBook(), "theme", "light", toml)

    assert load_global(toml) == Settings(chunk_width=10, theme="light")


def test_set_writes_valid_toml(toml):
    set_setting(FakeBook(), "theme", "light", toml)
    set_setting(FakeBook(), "chunk_width", "12", toml)

    with toml.open("rb") as f:
        assert tomllib.load(f) == {"chunk_width": 12, "theme": "light"}


def test_set_replaces_corrupt_toml_with_known_keys(toml):
    # SPEC_NOTES, Task 8: the global write rewrites only the known keys.
    write(toml, "chunk_width = = 6\nextra = 1\n")

    set_setting(FakeBook(), "chunk_width", "7", toml)

    assert load_global(toml) == Settings(chunk_width=7, theme="dark")


def test_set_then_resolve_returns_new_value(toml):
    book = FakeBook(chunk_width="10")

    set_setting(book, "chunk_width", "5", toml)

    assert resolve(book, load_global(toml)).chunk_width == 5


def test_global_write_failure_is_silent_and_book_layer_still_written(tmp_path):
    blocker = tmp_path / "kert"
    blocker.write_text("not a directory")
    book = FakeBook()

    set_setting(book, "theme", "light", blocker / "config.toml")

    assert book.state == {"theme": "light"}


@pytest.mark.parametrize(
    ("key", "raw"),
    [
        ("chunk_width", "4"),
        ("chunk_width", "13"),
        ("chunk_width", "abc"),
        ("theme", "blue"),
        ("position", "1"),
    ],
)
def test_set_rejects_invalid_and_writes_nothing(toml, key, raw):
    book = FakeBook()

    with pytest.raises(KertError):
        set_setting(book, key, raw, toml)

    assert book.state == {}
    assert not toml.exists()


@pytest.mark.spacy
def test_set_and_resolve_against_real_book(book_path, toml):
    from kert.reader.store import BookStore

    with BookStore.open(book_path) as store:
        set_setting(store, "chunk_width", "11", toml)
    with BookStore.open(book_path) as store:
        assert resolve(store, HARDCODED) == Settings(chunk_width=11, theme="dark")


# --- Shared value validation (used by :set) ------------------------------------------


@pytest.mark.parametrize(
    ("key", "raw", "value"),
    [
        ("chunk_width", "5", "5"),
        ("chunk_width", " 12", "12"),
        ("theme", "light", "light"),
    ],
)
def test_validate_normalizes_valid_values(key, raw, value):
    assert config.validate(key, raw) == value


@pytest.mark.parametrize(
    ("key", "raw"), [("chunk_width", "4"), ("theme", "blue"), ("position", "1")]
)
def test_validate_rejects_invalid_values(key, raw):
    with pytest.raises(KertError):
        config.validate(key, raw)
