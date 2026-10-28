"""Ingest → Normalize → Segment → Chunk-Candidates → Persist (spec §4, D1)."""

import os
import tempfile
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path

import spacy
from spacy.language import Language

from kert.common.dbschema import SCHEMA_VERSION
from kert.common.errors import KertError
from kert.common.model import Block, Lang, Sentence
from kert.common.text import is_word, whitespace_tokens
from kert.compiler.candidates import extract_candidates
from kert.compiler.ingest_txt import TxtIngester
from kert.compiler.normalize import NormalizedBlock, normalize
from kert.compiler.persist import write_book
from kert.compiler.segment import MODELS, load_model, segment, token_spans

PARAGRAPH_MODE = "blank"


@dataclass(frozen=True, slots=True)
class CompileSummary:
    blocks: int
    sentences: int
    candidates_per_sentence: float
    elapsed: float


@dataclass(frozen=True, slots=True)
class BookContent:
    blocks: list[Block]
    sentences: list[Sentence]
    word_count: int


# §14.3: headings and code are one unparsed, candidate-free sentence each.
_UNCHUNKED = {"heading", "code"}


def build_book(
    normalized: Sequence[NormalizedBlock], nlp: Language, lang: Lang
) -> BookContent:
    """Segment and extract candidates for typed blocks (§4.4–4.5, §14.3)."""
    parsed_texts = [b.text for b in normalized if b.type not in _UNCHUNKED]
    parsed = iter(segment(nlp, parsed_texts))
    blocks: list[Block] = []
    sentences: list[Sentence] = []
    word_count = 0
    for block_id, block in enumerate(normalized, 1):
        blocks.append(Block(id=block_id, type=block.type, chapter=block.chapter))
        if block.type in _UNCHUNKED:
            tokens = whitespace_tokens(block.text)
            word_count += sum(is_word(block.text[s:e]) for s, e in tokens)
            sentences.append(
                Sentence(
                    id=len(sentences) + 1,
                    block_id=block_id,
                    seq=0,
                    text=block.text,
                    tokens=tokens,
                    candidates=(),
                )
            )
            continue
        for seq, sent in enumerate(next(parsed)):
            word_count += sum(1 for t in sent if t.is_alpha or t.like_num)
            sentences.append(
                Sentence(
                    id=len(sentences) + 1,
                    block_id=block_id,
                    seq=seq,
                    text=sent.text,
                    tokens=tuple(token_spans(sent)),
                    candidates=tuple(extract_candidates(sent, block.type, lang)),
                )
            )
    return BookContent(blocks, sentences, word_count)


def compile_book(
    input_path: Path, output_path: Path, lang: Lang, *, force: bool = False
) -> CompileSummary:
    started = time.perf_counter()
    if output_path.exists() and not force:
        raise KertError(f"{output_path} already exists; use --force to overwrite it.")

    ingested = TxtIngester(lang).ingest(input_path)
    normalized = normalize(ingested.blocks, lang)
    nlp = load_model(lang)
    book = build_book(normalized, nlp, lang)
    blocks, sentences = book.blocks, book.sentences

    meta = {
        "schema_version": SCHEMA_VERSION,
        "title": ingested.title or input_path.stem,
        "language": lang,
        "source_format": "txt",
        "source_filename": input_path.name,
        "paragraph_mode": PARAGRAPH_MODE,
        "compiler_version": version("kert"),
        "compiled_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "spacy_model": MODELS[lang],
        "spacy_version": spacy.__version__,
        "model_version": nlp.meta["version"],
        "word_count": str(book.word_count),
    }
    _write_atomically(output_path, meta, blocks, sentences)

    total_candidates = sum(len(s.candidates) for s in sentences)
    return CompileSummary(
        blocks=len(blocks),
        sentences=len(sentences),
        candidates_per_sentence=total_candidates / len(sentences) if sentences else 0.0,
        elapsed=time.perf_counter() - started,
    )


def _write_atomically(
    output_path: Path,
    meta: Mapping[str, str],
    blocks: Sequence[Block],
    sentences: Sequence[Sentence],
) -> None:
    """Stage next to the target, then replace it: never a partial or lost file."""
    with tempfile.TemporaryDirectory(
        dir=output_path.parent, prefix=f".{output_path.name}."
    ) as staging:
        staged = Path(staging) / output_path.name
        write_book(staged, meta, blocks, sentences)
        for sidecar in ("-wal", "-shm"):
            Path(f"{output_path}{sidecar}").unlink(missing_ok=True)
        os.replace(staged, output_path)
