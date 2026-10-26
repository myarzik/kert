"""Plain-text view of split candidates and assembled chunks (spec §9)."""

from collections.abc import Sequence

from kert.common.errors import KertError
from kert.common.model import Sentence
from kert.reader.chunker import chunk_sentence


def render_inspection(sentence: Sentence, width: int) -> str:
    """Sentence with inline `⟨w⟩` cut markers, then its chunks at `width`."""
    text, tokens = sentence.text, sentence.tokens
    marked, pos = [], 0
    for candidate in sentence.candidates:
        # The marker follows the last token before the cut.
        end = tokens[candidate.token_index - 1][1]
        marked.append(f"{text[pos:end]}⟨{candidate.weight:.1f}⟩")
        pos = end
    marked.append(text[pos:])

    chunks = " ".join(
        f"[{text[tokens[start][0] : tokens[end - 1][1]]}]"
        for start, end in chunk_sentence(len(tokens), sentence.candidates, width)
    )
    return f"{''.join(marked)}\n{chunks}"


def select_sentences(
    sentences: Sequence[Sentence],
    *,
    sentence: int | None = None,
    block: int | None = None,
    span: tuple[int, int] | None = None,
) -> list[Sentence]:
    """Sentences matching at most one selector; all of them when none is given."""
    given = [s for s in (sentence, block, span) if s is not None]
    if len(given) > 1:
        raise KertError("Use at most one of --sentence, --block, --range.")
    if sentence is not None:
        selected = [s for s in sentences if s.id == sentence]
        what = f"sentence {sentence}"
    elif block is not None:
        selected = [s for s in sentences if s.block_id == block]
        what = f"block {block}"
    elif span is not None:
        selected = [s for s in sentences if span[0] <= s.id <= span[1]]
        what = f"range {span[0]}:{span[1]}"
    else:
        return list(sentences)
    if not selected:
        raise KertError(f"No sentences match {what}.")
    return selected


def parse_range(raw: str) -> tuple[int, int]:
    """Parse `A:B` into an inclusive sentence-id range."""
    parts = raw.split(":")
    try:
        start, end = (int(p) for p in parts)
    except ValueError:
        raise KertError(f"--range must be A:B with integer ids, got {raw!r}.") from None
    return start, end
