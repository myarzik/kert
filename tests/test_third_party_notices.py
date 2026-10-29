"""Third-party notices shipped with the frozen builds (spec §15)."""

import importlib.util
from pathlib import Path

import pytest
from conftest import require_model

SCRIPT = Path(__file__).resolve().parents[1] / "packaging" / "third_party_notices.py"


@pytest.fixture(scope="module")
def notices():
    spec = importlib.util.spec_from_file_location("third_party_notices", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_reader_build_lists_its_runtime_stack_with_license_texts(notices):
    text = notices.render("reader")

    for name in ("rich", "typer", "click", "readchar", "msgpack", "platformdirs"):
        assert f"\n{name} " in text, name
    assert "Permission is hereby granted, free of charge" in text  # MIT body
    assert "PYTHON SOFTWARE FOUNDATION LICENSE" in text
    assert "PyInstaller" in text and "bootloader" in text
    assert "spacy" not in text


@pytest.mark.spacy
def test_full_build_adds_the_nlp_stack_and_models(notices):
    require_model("ru_core_news_sm")
    require_model("en_core_web_sm")
    text = notices.render("full")

    for name in (
        "spacy",
        "thinc",
        "blis",
        "numpy",
        "ru-core-news-sm",
        "en-core-web-sm",
    ):
        assert f"\n{name} " in text, name


@pytest.mark.spacy
def test_excluded_packages_are_not_listed(notices):
    # Never bundled: the lemmatizer is excluded at load time (§4.4).
    text = notices.render("full")

    assert "pymorphy3" not in text
