import sys
import tomllib
from pathlib import Path

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
def test_config_path_is_xdg_on_linux_and_macos(monkeypatch, platform):
    # A POSIX path even on a Windows CI host: platformdirs ignores
    # XDG_CONFIG_HOME unless it is POSIX-absolute.
    monkeypatch.setattr(sys, "platform", platform)
    monkeypatch.setenv("XDG_CONFIG_HOME", "/xdg-config")

    assert config.config_path() == Path("/xdg-config/kert/config.toml")


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


# --- mode: per book only (§17.2, §17.10) --------------------------------------------


def test_mode_resolves_from_the_book():
    assert resolve(FakeBook(mode="paragraph"), HARDCODED).mode == "paragraph"


@pytest.mark.parametrize("state", [{}, {"mode": "plain"}])
def test_missing_or_invalid_book_mode_is_chunk(state):
    assert resolve(FakeBook(**state), HARDCODED).mode == "chunk"


def test_toml_never_sets_the_mode(toml):
    write(toml, 'mode = "paragraph"\n')

    assert load_global(toml).mode == "chunk"


def test_set_mode_writes_the_book_only(toml):
    write(toml, 'chunk_width = 10\ntheme = "light"\n')
    before = toml.read_text(encoding="utf-8")
    book = FakeBook()

    set_setting(book, "mode", "sentence", toml)

    assert book.state == {"mode": "sentence"}
    assert toml.read_text(encoding="utf-8") == before


@pytest.mark.parametrize("raw", ["chunk", "sentence", "paragraph"])
def test_validate_accepts_modes(raw):
    assert config.validate("mode", raw) == raw


def test_validate_rejects_unknown_mode():
    with pytest.raises(KertError, match="mode must be one of"):
        config.validate("mode", "plain")


# --- default_goal: TOML only (§17.6, §17.10) ----------------------------------------


@pytest.mark.parametrize("raw", ["15m", "2000w"])
def test_default_goal_comes_from_the_toml(toml, raw):
    write(toml, f'default_goal = "{raw}"\n')

    assert load_global(toml).default_goal == raw
    assert resolve(FakeBook(), load_global(toml)).default_goal == raw


@pytest.mark.parametrize("value", ['"15x"', '"0m"', "15", '"601m"'])
def test_invalid_default_goal_is_ignored(toml, value):
    write(toml, f"default_goal = {value}\n")

    assert load_global(toml).default_goal is None


def test_set_keeps_the_default_goal_in_the_toml(toml):
    write(toml, 'default_goal = "15m"\n')

    set_setting(FakeBook(), "theme", "light", toml)

    assert load_global(toml).default_goal == "15m"
    assert load_global(toml).theme == "light"
