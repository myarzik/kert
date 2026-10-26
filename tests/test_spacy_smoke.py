import pytest

spacy = pytest.importorskip("spacy")


@pytest.mark.spacy
@pytest.mark.parametrize("model", ["ru_core_news_sm", "en_core_web_sm"])
def test_pinned_model_loads_with_parser(model):
    pytest.importorskip(model)

    nlp = spacy.load(model, disable=["ner", "lemmatizer"])

    assert "parser" in nlp.pipe_names
