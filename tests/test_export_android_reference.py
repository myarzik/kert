"""The Android reference export (spec §16.6) covers every fixture and width."""

import importlib.util
import json
from pathlib import Path

import pytest
from conftest import require_model

from kert.reader.store import BookStore

pytestmark = pytest.mark.spacy

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "export_android_reference.py"


@pytest.fixture(scope="module")
def exported(tmp_path_factory):
    require_model("ru_core_news_sm")
    require_model("en_core_web_sm")
    spec = importlib.util.spec_from_file_location("export_reference", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    out = tmp_path_factory.mktemp("reference")
    module.export(out)
    return out, json.loads((out / "reference.json").read_text(encoding="utf-8"))


def test_every_fixture_is_compiled_and_referenced(exported):
    out, reference = exported

    names = [b["file"] for b in reference["books"]]
    assert names == ["book_ru.kert", "book_en.kert", "non_bmp.kert"]
    assert all((out / name).is_file() for name in names)


def test_every_width_has_chunks_covering_every_sentence(exported):
    out, reference = exported
    for book in reference["books"]:
        with BookStore.open(out / book["file"]) as store:
            sentence_ids = [s.id for s in store.sentences]
        assert sorted(book["widths"]) == sorted(str(w) for w in range(5, 13))
        for chunks in book["widths"].values():
            assert sorted({c[0] for c in chunks}) == sentence_ids
            assert chunks[0][4] == 0  # words before the first chunk


def test_non_bmp_fixture_really_has_astral_characters(exported):
    out, _ = exported
    with BookStore.open(out / "non_bmp.kert") as store:
        texts = [s.text for s in store.sentences]

    assert any(any(ord(ch) > 0xFFFF for ch in text) for text in texts)


def test_mode_units_are_exported_for_sentence_and_paragraph(exported):
    # [first sentence id, start token, last sentence id, end token, words, before]
    _, reference = exported
    for book in reference["books"]:
        sentence, paragraph = book["modes"]["sentence"], book["modes"]["paragraph"]
        assert all(u[0] == u[2] and u[1] == 0 for u in sentence)
        for units in (sentence, paragraph):
            assert units[0][5] == 0
            assert sum(u[4] for u in units) == sum(c[3] for c in book["widths"]["8"])


def test_paragraph_units_of_the_ru_fixture(exported):
    # tests/fixtures/book_ru.txt blocks: S1 | S2 S3 | S4 | S5 S6.
    _, reference = exported
    (ru,) = [b for b in reference["books"] if b["file"] == "book_ru.kert"]

    assert [(u[0], u[2]) for u in ru["modes"]["paragraph"]] == [
        (1, 1),
        (2, 3),
        (4, 4),
        (5, 6),
    ]
