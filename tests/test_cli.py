import sqlite3
from importlib.metadata import version
from pathlib import Path

import pytest
from conftest import require_model
from typer.testing import CliRunner

from kert.cli import app, main

FIXTURE = Path(__file__).parent / "fixtures" / "book_ru.txt"

runner = CliRunner()


def test_version_flag_prints_package_version_and_exits_zero():
    result = runner.invoke(app, ["--version"])

    assert result.exit_code == 0
    assert result.output.strip() == f"kert {version('kert')}"


def test_main_returns_zero_for_version():
    assert main(["--version"]) == 0


# --- kert compile (spec §9) ---------------------------------------------------


@pytest.fixture
def out(tmp_path):
    return tmp_path / "out" / "book.kert"


@pytest.fixture(autouse=True)
def _out_dir(tmp_path):
    (tmp_path / "out").mkdir()


@pytest.mark.spacy
def test_compile_succeeds_and_prints_summary(out, capsys):
    require_model("ru_core_news_sm")

    code = main(["compile", str(FIXTURE), "-o", str(out), "--lang", "ru"])

    assert code == 0
    assert out.is_file()
    stdout = capsys.readouterr().out
    assert "4 blocks" in stdout
    assert "6 sentences" in stdout


def test_refuses_to_overwrite_without_force(out, capsys):
    out.write_bytes(b"original")

    code = main(["compile", str(FIXTURE), "-o", str(out), "--lang", "ru"])

    assert code == 1
    assert "--force" in capsys.readouterr().err
    assert out.read_bytes() == b"original"


@pytest.mark.spacy
def test_force_overwrites_and_removes_stale_sidecars(out):
    require_model("ru_core_news_sm")
    out.write_bytes(b"original")
    Path(f"{out}-wal").write_bytes(b"stale")
    Path(f"{out}-shm").write_bytes(b"stale")

    code = main(["compile", str(FIXTURE), "-o", str(out), "--lang", "ru", "--force"])

    assert code == 0
    assert sorted(p.name for p in out.parent.iterdir()) == ["book.kert"]
    conn = sqlite3.connect(out)
    try:
        language = conn.execute("SELECT value FROM meta WHERE key = 'language'")
        assert language.fetchone() == ("ru",)
    finally:
        conn.close()


def test_force_keeps_original_when_compile_fails(tmp_path, out):
    bad = tmp_path / "bad.txt"
    bad.write_bytes("Привет.".encode("cp1251"))  # undecodable for --lang en
    out.write_bytes(b"original")

    code = main(["compile", str(bad), "-o", str(out), "--lang", "en", "--force"])

    assert code == 1
    assert out.read_bytes() == b"original"
    assert sorted(p.name for p in out.parent.iterdir()) == ["book.kert"]


def test_failed_compile_leaves_no_output(tmp_path, out, capsys):
    bad = tmp_path / "bad.txt"
    bad.write_bytes("Привет.".encode("cp1251"))

    code = main(["compile", str(bad), "-o", str(out), "--lang", "en"])

    assert code == 1
    assert "--encoding" in capsys.readouterr().err
    assert list(out.parent.iterdir()) == []


SRC = str(FIXTURE)


@pytest.mark.parametrize(
    "argv",
    [
        pytest.param(
            ["compile", "nope.txt", "-o", "x.kert", "--lang", "ru"], id="missing-input"
        ),
        pytest.param(
            ["compile", SRC, "-o", "x.kert", "--lang", "de"], id="unknown-lang"
        ),
        pytest.param(["compile", SRC, "--lang", "ru"], id="missing-output"),
        pytest.param(["compile", SRC, "-o", "x.kert"], id="missing-lang"),
        pytest.param(["frobnicate"], id="unknown-command"),
    ],
)
def test_bad_arguments_are_user_errors(argv, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    assert main(argv) == 1


@pytest.mark.parametrize("mode", ["indent", "single-newline"])
def test_reserved_paragraph_modes_are_user_errors(mode, out, capsys):
    argv = ["compile", str(FIXTURE), "-o", str(out), "--lang", "ru"]

    code = main([*argv, "--paragraph-mode", mode])

    assert code == 1
    assert mode in capsys.readouterr().err
    assert not out.exists()


def test_unexpected_exception_is_internal_error(out, capsys, monkeypatch):
    from kert.compiler import pipeline

    def boom(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(pipeline, "compile_book", boom)

    code = main(["compile", str(FIXTURE), "-o", str(out), "--lang", "ru"])

    assert code == 2
    assert "internal error" in capsys.readouterr().err.lower()


# --- Formats by suffix (§14.1) --------------------------------------------------


MARKDOWN = """# Глава первая

Он вышел из дома, хотя шёл дождь.

- Мы долго гуляли по парку.

```
x = 1
```
"""


@pytest.mark.spacy
def test_compile_markdown_records_format_title_and_block_types(tmp_path, out):
    require_model("ru_core_news_sm")
    source = tmp_path / "notes.md"
    source.write_text(MARKDOWN, encoding="utf-8")

    assert main(["compile", str(source), "-o", str(out), "--lang", "ru"]) == 0

    conn = sqlite3.connect(out)
    try:
        meta = dict(conn.execute("SELECT key, value FROM meta"))
        rows = conn.execute("SELECT type, chapter FROM blocks ORDER BY id").fetchall()
    finally:
        conn.close()
    assert (meta["source_format"], meta["title"]) == ("md", "notes")
    assert rows == [("heading", 1), ("paragraph", 1), ("list_item", 1), ("code", 1)]


def test_compile_unsupported_suffix_is_user_error(tmp_path, out, capsys):
    source = tmp_path / "book.docx"
    source.write_bytes(b"PK")

    assert main(["compile", str(source), "-o", str(out), "--lang", "ru"]) == 1
    err = capsys.readouterr().err
    assert ".txt" in err and ".md" in err
    assert not out.exists()


# --- Reader-only build: compile is unavailable (§15) ----------------------------


@pytest.mark.parametrize("missing", ["kert.compiler.pipeline", "spacy"])
def test_compile_without_compiler_is_user_error(
    monkeypatch, tmp_path, out, capsys, missing
):
    import sys

    import kert.compiler

    # As in the kert-reader build: the import of the compiler stack fails.
    monkeypatch.delitem(sys.modules, "kert.compiler.pipeline", raising=False)
    monkeypatch.delattr(kert.compiler, "pipeline", raising=False)
    monkeypatch.setitem(sys.modules, missing, None)
    source = tmp_path / "book.txt"
    source.write_text("Текст.", encoding="utf-8")

    code = main(["compile", str(source), "-o", str(out), "--lang", "ru"])

    assert code == 1
    assert "cannot compile" in capsys.readouterr().err
    assert not out.exists()
