import spacy
from spacy.language import Language
from spacy.tokens import Span

from kert.common.errors import KertError
from kert.common.model import Lang

MODELS: dict[Lang, str] = {"ru": "ru_core_news_sm", "en": "en_core_web_sm"}
# Pinned in pyproject.toml [tool.uv.sources]; golden tests depend on it (§2.1).
MODEL_VERSION = "3.8.0"


def _model_requirement(lang: Lang) -> str:
    name = MODELS[lang]
    url = (
        "https://github.com/explosion/spacy-models/releases/download/"
        f"{name}-{MODEL_VERSION}/{name}-{MODEL_VERSION}-py3-none-any.whl"
    )
    return f"{name.replace('_', '-')} @ {url}"


def load_model(lang: Lang) -> Language:
    try:
        return spacy.load(MODELS[lang], exclude=["ner", "lemmatizer"])
    except OSError as exc:
        raise KertError(
            f"spaCy model {MODELS[lang]!r} for --lang {lang} is not installed.\n"
            "  Development checkout: uv sync --group models\n"
            "  Installed with uv tool: from your kert checkout, run\n"
            "    uv tool install . --force --python 3.14 "
            f'--with "{_model_requirement(lang)}"\n'
            "  (one --with per language you compile; see README)"
        ) from exc


def segment(nlp: Language, texts: list[str]) -> list[list[Span]]:
    """Split each block text into parser-derived sentences (spec §4.4)."""
    return [list(doc.sents) for doc in nlp.pipe(texts, batch_size=64)]


def token_spans(sent: Span) -> list[tuple[int, int]]:
    """Char spans of the sentence's tokens, relative to `sent.text`."""
    offset = sent.start_char
    return [(t.idx - offset, t.idx - offset + len(t.text)) for t in sent]
