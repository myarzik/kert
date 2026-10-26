import spacy
from spacy.language import Language
from spacy.tokens import Span

from kert.common.model import Lang

MODELS: dict[Lang, str] = {"ru": "ru_core_news_sm", "en": "en_core_web_sm"}


def load_model(lang: Lang) -> Language:
    return spacy.load(MODELS[lang], disable=["ner", "lemmatizer"])


def segment(nlp: Language, texts: list[str]) -> list[list[Span]]:
    """Split each block text into parser-derived sentences (spec §4.4)."""
    return [list(doc.sents) for doc in nlp.pipe(texts, batch_size=64)]


def token_spans(sent: Span) -> list[tuple[int, int]]:
    """Char spans of the sentence's tokens, relative to `sent.text`."""
    offset = sent.start_char
    return [(t.idx - offset, t.idx - offset + len(t.text)) for t in sent]
