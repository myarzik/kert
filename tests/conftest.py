import importlib.util
import os
import shutil
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


def require_model(name: str) -> None:
    """Skip when a spaCy model is missing locally; fail in CI (spec §13.1)."""
    if importlib.util.find_spec(name) is not None:
        return
    message = f"spaCy model {name!r} is not installed (uv sync --group models)"
    if os.environ.get("CI"):
        pytest.fail(message)
    pytest.skip(message)


@pytest.fixture(scope="session")
def nlp_ru():
    require_model("ru_core_news_sm")
    from kert.compiler.segment import load_model

    return load_model("ru")


@pytest.fixture(scope="session")
def nlp_en():
    require_model("en_core_web_sm")
    from kert.compiler.segment import load_model

    return load_model("en")


@pytest.fixture(scope="session")
def compiled_ru_template(tmp_path_factory):
    """fixtures/book_ru.txt compiled once per session; copy before mutating."""
    require_model("ru_core_news_sm")
    from kert.compiler.pipeline import compile_book

    out = tmp_path_factory.mktemp("template") / "book.kert"
    compile_book(FIXTURES / "book_ru.txt", out, "ru")
    return out


@pytest.fixture
def book_path(compiled_ru_template, tmp_path):
    """A private, mutable copy of the compiled RU fixture book."""
    path = tmp_path / "book.kert"
    shutil.copyfile(compiled_ru_template, path)
    return path
