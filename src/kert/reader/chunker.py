"""Chunk assembly from split-point candidates (spec §6).

Cuts are {0, n} plus a subset of candidate indices. A suffix DP picks the
subset minimizing (chunks longer than 2W+2, §6 cost) lexicographically; on
equal cost the forward walk takes the earliest next cut (SPEC_NOTES, Task 7).
"""

from collections.abc import Sequence

from kert.common.model import ChunkSpan, Sentence, SplitCandidate

_TIE_EPSILON = 1e-9


def length_penalty(length: int, width: int) -> float:
    penalty = ((length - width) / width) ** 2
    if length > 2 * width:
        penalty += 4.0
    if length < 3:
        penalty += 1.0
    return penalty


def cut_penalty(weight: float) -> float:
    return (1.0 - weight) * 0.75


def chunk_sentence(
    n: int, candidates: Sequence[SplitCandidate], width: int
) -> list[tuple[int, int]]:
    if n <= width + 2:
        return [(0, n)]

    cuts = [0, *(c.token_index for c in candidates), n]
    # Penalty for a chunk entered at cuts[i]; the sentence start is free.
    entry = [0.0, *(cut_penalty(c.weight) for c in candidates)]
    limit = 2 * width + 2
    last = len(cuts) - 1

    def option(i: int, j: int) -> tuple[int, float]:
        length = cuts[j] - cuts[i]
        over, cost = best[j]
        return (
            over + (length > limit),
            cost + length_penalty(length, width) + entry[i],
        )

    # best[i]: (overlong chunks, cost) of the optimal cover of [cuts[i], n].
    best: list[tuple[int, float]] = [(0, 0.0)] * len(cuts)
    nxt = [last] * len(cuts)
    for i in range(last - 1, -1, -1):
        nxt[i], best[i] = i + 1, option(i, i + 1)
        for j in range(i + 2, last + 1):
            candidate = option(i, j)
            if _better(candidate, best[i]):
                nxt[i], best[i] = j, candidate

    spans = []
    i = 0
    while i < last:
        spans.append((cuts[i], cuts[nxt[i]]))
        i = nxt[i]
    return spans


def _better(a: tuple[int, float], b: tuple[int, float]) -> bool:
    return a[0] < b[0] or (a[0] == b[0] and a[1] < b[1] - _TIE_EPSILON)


def assemble(sentences: Sequence[Sentence], width: int) -> list[ChunkSpan]:
    """Chunk every sentence at `width` into one flat, reading-ordered list."""
    return [
        ChunkSpan(sentence_id=s.id, start_token=start, end_token=end)
        for s in sentences
        for start, end in chunk_sentence(len(s.tokens), s.candidates, width)
    ]
