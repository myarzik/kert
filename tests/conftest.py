import importlib.util
import os

import pytest


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
