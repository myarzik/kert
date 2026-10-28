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
