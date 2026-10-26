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

from kert.common.dbschema import SCHEMA_VERSION
from kert.common.errors import KertError
from kert.common.model import Block, Lang, Sentence
from kert.compiler.candidates import extract_candidates
from kert.compiler.ingest_txt import TxtIngester
from kert.compiler.normalize import normalize
from kert.compiler.persist import write_book
from kert.compiler.segment import MODELS, load_model, segment, token_spans

PARAGRAPH_MODE = "blank"


@dataclass(frozen=True, slots=True)
class CompileSummary:
    blocks: int
    sentences: int
    candidates_per_sentence: float
    elapsed: float


def compile_book(
    input_path: Path, output_path: Path, lang: Lang, *, force: bool = False
) -> CompileSummary:
    started = time.perf_counter()
    if output_path.exists() and not force:
        raise KertError(f"{output_path} already exists; use --force to overwrite it.")

    normalized = normalize(TxtIngester(lang).ingest(input_path), lang)
    nlp = load_model(lang)

    blocks: list[Block] = []
    sentences: list[Sentence] = []
    word_count = 0
    parsed = segment(nlp, [b.text for b in normalized])
    for block_id, (block, sents) in enumerate(zip(normalized, parsed, strict=True), 1):
        blocks.append(Block(id=block_id, type=block.type))
        for seq, sent in enumerate(sents):
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

    meta = {
        "schema_version": SCHEMA_VERSION,
        "title": input_path.stem,
        "language": lang,
        "source_format": "txt",
        "source_filename": input_path.name,
        "paragraph_mode": PARAGRAPH_MODE,
        "compiler_version": version("kert"),
        "compiled_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "spacy_model": MODELS[lang],
        "spacy_version": spacy.__version__,
        "model_version": nlp.meta["version"],
        "word_count": str(word_count),
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
