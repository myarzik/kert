"""Chunk assembly (spec §6). Goldens are hand-computed from the §6 formulas:

    lp(L) = ((L - W) / W)**2 + (4 if L > 2W) + (1 if L < 3)
    cp(w) = (1 - w) * 0.75, charged to every chunk except the first

Overlong priority (SPEC_NOTES, Task 7): the DP minimizes the number of chunks
longer than 2W+2 first, then the §6 cost; ties prefer the earlier cut.
"""

import itertools
import random
import unicodedata

import pytest

from kert.common.model import ChunkSpan, Sentence, SplitCandidate
from kert.reader.chunker import (
    assemble,
    chunk_sentence,
    cut_penalty,
    length_penalty,
)


def cands(pairs):
    return [SplitCandidate(token_index=i, weight=w) for i, w in pairs]


# --- Cost terms ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("length", "width", "expected"),
    [
        (8, 8, 0.0),
        (6, 8, 0.0625),  # (2/8)^2
        (2, 8, 1.5625),  # (6/8)^2 + 1 crumb
        (16, 8, 1.0),  # (8/8)^2, not > 2W
        (17, 8, 1.265625 + 4.0),  # (9/8)^2 + 4
        (3, 5, 0.16),  # (2/5)^2, not a crumb
    ],
)
def test_length_penalty(length, width, expected):
    assert length_penalty(length, width) == pytest.approx(expected)


@pytest.mark.parametrize(
    ("weight", "expected"), [(1.0, 0.0), (0.8, 0.15), (0.4, 0.45), (0.2, 0.6)]
)
def test_cut_penalty(weight, expected):
    assert cut_penalty(weight) == pytest.approx(expected)


# --- Golden fixture sentences at W = 6, 8, 12 ---------------------------------

# EN "She gave the old man a book in the morning." (test_candidates_en)
EN_N, EN_CANDS = 11, cands([(2, 0.4), (5, 0.4), (7, 0.4)])
# RU "Мы долго гуляли по парку и разговаривали о книгах." (test_candidates_ru)
RU_N, RU_CANDS = 10, cands([(3, 0.4), (5, 0.8), (7, 0.4)])


@pytest.mark.parametrize(
    ("n", "candidates", "width", "expected"),
    [
        # W=6: {} 0.694; {2} 2.144; {5} 0.028+0+0.45=0.478; {7} 0.589; pairs > 1.9
        (EN_N, EN_CANDS, 6, [(0, 5), (5, 11)]),
        # W=8: {} (3/8)^2=0.141; {5} 0.141+0.063+0.45=0.653
        (EN_N, EN_CANDS, 8, [(0, 11)]),
        # W=12: n <= W+2
        (EN_N, EN_CANDS, 12, [(0, 11)]),
        # W=6: {} 0.444; {3} 0.728; {5} 0.028+0.028+0.15=0.206; {7} 0.728
        (RU_N, RU_CANDS, 6, [(0, 5), (5, 10)]),
        # W=8 and W=12: n <= W+2
        (RU_N, RU_CANDS, 8, [(0, 10)]),
        (RU_N, RU_CANDS, 12, [(0, 10)]),
    ],
)
def test_golden_fixture_sentences(n, candidates, width, expected):
    assert chunk_sentence(n, candidates, width) == expected


# --- Synthetic goldens: one behavior each --------------------------------------


def test_short_sentence_is_one_chunk_without_dp():
    assert chunk_sentence(10, cands([(5, 1.0)]), 8) == [(0, 10)]


def test_no_candidates_is_one_chunk():
    assert chunk_sentence(20, [], 6) == [(0, 20)]


def test_strong_boundary_preferred():
    # W=6: {5} 0.028+0.028+0.45=0.506; {7} 0.028+0.028+0=0.056; {} 1.0
    assert chunk_sentence(12, cands([(5, 0.4), (7, 1.0)]), 6) == [(0, 7), (7, 12)]


def test_crumbs_avoided_even_at_strong_boundaries():
    # W=8: {} 0.25; {2} or {10}: 1.5625+0.0625=1.625
    assert chunk_sentence(12, cands([(2, 1.0), (10, 1.0)]), 8) == [(0, 12)]


def test_long_sentence_split_at_fallback_candidates():
    # W=5: {10,20} 1+1+1+2*0.6=4.2; {10} or {20}: 1+13+0.6=14.6; {} 29
    result = chunk_sentence(30, cands([(10, 0.2), (20, 0.2)]), 5)

    assert result == [(0, 10), (10, 20), (20, 30)]


def test_tie_prefers_earlier_cut():
    # W=6: {4} 0.111+0.111=0.222 == {8} 0.111+0.111; {4,8} 0.333; {} 1.0
    assert chunk_sentence(12, cands([(4, 1.0), (8, 1.0)]), 6) == [(0, 4), (4, 12)]


def test_overlong_chunk_avoided_when_bounded_partition_exists():
    # W=5, 2W+2=12: {} costs 6.56 but L=13 > 12; {2} costs 1.36+5.44+0.45=7.25
    assert chunk_sentence(13, cands([(2, 0.4)]), 5) == [(0, 2), (2, 13)]


# --- assemble(): whole book ------------------------------------------------------


def test_assemble_flattens_sentences_in_order():
    sentences = [
        Sentence(1, 1, 0, "x", tokens=((0, 1),) * 12,
                 candidates=tuple(cands([(4, 1.0), (8, 1.0)]))),
        Sentence(2, 1, 1, "y", tokens=((0, 1),) * 3, candidates=()),
    ]  # fmt: skip

    assert assemble(sentences, 6) == [
        ChunkSpan(sentence_id=1, start_token=0, end_token=4),
        ChunkSpan(sentence_id=1, start_token=4, end_token=12),
        ChunkSpan(sentence_id=2, start_token=0, end_token=3),
    ]


# --- Properties (§10.3) ------------------------------------------------------------


def bounded_partition_exists(n, candidates, width):
    """Independent reachability check: cuts at 0, candidates, n; steps <= 2W+2."""
    points = [0, *(c.token_index for c in candidates), n]
    reachable = {0}
    for p in points[1:]:
        if any(p - q <= 2 * width + 2 for q in reachable):
            reachable.add(p)
    return n in reachable


def random_cases(count=2000, seed=20261026):
    rnd = random.Random(seed)
    for _ in range(count):
        n = rnd.randint(1, 80)
        width = rnd.randint(5, 12)
        k = rnd.randint(0, min(n - 1, 12))
        indices = sorted(rnd.sample(range(1, n), k)) if n > 1 else []
        weights = [rnd.choice([1.0, 0.8, 0.6, 0.4, 0.2]) for _ in indices]
        yield n, cands(zip(indices, weights, strict=True)), width


def test_property_chunks_partition_the_sentence():
    for n, candidates, width in random_cases():
        spans = chunk_sentence(n, candidates, width)

        assert spans[0][0] == 0 and spans[-1][1] == n
        assert all(a < b for a, b in spans)
        assert all(prev[1] == nxt[0] for prev, nxt in itertools.pairwise(spans))


def test_property_cuts_only_at_candidates():
    for n, candidates, width in random_cases():
        allowed = {c.token_index for c in candidates}
        cuts = {a for a, _ in chunk_sentence(n, candidates, width)[1:]}

        assert cuts <= allowed


def test_property_no_chunk_longer_than_2w_plus_2_when_avoidable():
    for n, candidates, width in random_cases():
        if not bounded_partition_exists(n, candidates, width):
            continue
        spans = chunk_sentence(n, candidates, width)

        assert all(b - a <= 2 * width + 2 for a, b in spans), (n, width, spans)


def test_property_short_sentences_are_single_chunks():
    for n, candidates, width in random_cases():
        if n <= width + 2:
            assert chunk_sentence(n, candidates, width) == [(0, n)]


def test_property_deterministic():
    for n, candidates, width in random_cases(count=200):
        assert chunk_sentence(n, candidates, width) == chunk_sentence(
            n, candidates, width
        )


def is_punct_token(text):
    return all(unicodedata.category(ch).startswith("P") for ch in text)


@pytest.mark.spacy
@pytest.mark.parametrize("width", range(5, 13))
def test_property_no_chunk_starts_with_punctuation_on_compiled_book(book_path, width):
    from kert.reader.store import BookStore

    with BookStore.open(book_path) as store:
        by_id = {s.id: s for s in store.sentences}
        for span in assemble(store.sentences, width):
            if span.start_token == 0:
                continue  # sentence start, e.g. a leading dialogue dash
            sentence = by_id[span.sentence_id]
            s, e = sentence.tokens[span.start_token]
            assert not is_punct_token(sentence.text[s:e])
