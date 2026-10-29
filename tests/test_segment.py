import pytest

from kert.compiler.segment import segment, token_spans

pytestmark = pytest.mark.spacy

RU_PARAGRAPHS = [
    "Он вышел из дома. На улице шёл дождь. Пришлось вернуться за зонтом.",
    "Я люблю читать. Книги помогают думать.",
]
EN_PARAGRAPHS = [
    "It was late. Nobody answered the phone. He went to bed.",
    "She opened the door. The room was empty.",
]


@pytest.fixture
def nlp(request):
    return request.getfixturevalue(f"nlp_{request.param}")


@pytest.mark.parametrize("nlp", ["ru", "en"], indirect=True)
def test_model_runs_parser_without_ner_and_lemmatizer(nlp):
    assert "parser" in nlp.pipe_names
    assert "ner" not in nlp.pipe_names
    assert "lemmatizer" not in nlp.pipe_names


@pytest.mark.parametrize(
    ("nlp", "paragraphs"),
    [("ru", RU_PARAGRAPHS), ("en", EN_PARAGRAPHS)],
    indirect=["nlp"],
)
def test_sentence_counts_per_paragraph(nlp, paragraphs):
    result = segment(nlp, paragraphs)

    assert [len(sentences) for sentences in result] == [3, 2]


@pytest.mark.parametrize(
    ("nlp", "paragraphs"),
    [("ru", RU_PARAGRAPHS), ("en", EN_PARAGRAPHS)],
    indirect=["nlp"],
)
def test_token_spans_index_into_sentence_text(nlp, paragraphs):
    for sentences in segment(nlp, paragraphs):
        for sent in sentences:
            spans = token_spans(sent)

            assert [sent.text[s:e] for s, e in spans] == [t.text for t in sent]
            assert all(s < e for s, e in spans)
            assert all(not sent.text[s:e].isspace() for s, e in spans)
            assert spans == sorted(spans)


def test_empty_input_yields_no_blocks(nlp_en):
    assert segment(nlp_en, []) == []


def test_ru_model_loads_without_the_lemmatizer_dictionaries(nlp_ru):
    # exclude (not disable): pymorphy3 and its CC BY-SA dictionaries are never
    # imported, so frozen builds need not ship them (spec §4.4, §15).
    import subprocess
    import sys

    probe = (
        "import sys; from kert.compiler.segment import load_model; "
        "load_model('ru'); print('pymorphy3' in sys.modules)"
    )
    out = subprocess.run(
        [sys.executable, "-c", probe], capture_output=True, text=True, check=True
    )

    assert out.stdout.strip() == "False"
