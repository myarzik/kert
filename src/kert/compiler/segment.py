from spacy.language import Language
from spacy.tokens import Span

from kert.common.model import Lang


def load_model(lang: Lang) -> Language:
    raise NotImplementedError


def segment(nlp: Language, texts: list[str]) -> list[list[Span]]:
    raise NotImplementedError


def token_spans(sent: Span) -> list[tuple[int, int]]:
    raise NotImplementedError
