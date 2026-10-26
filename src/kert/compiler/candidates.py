"""Split-point candidate extraction from a dependency parse (spec §4.5).

A candidate at index i means "a new chunk may start at token i".
"""

from collections.abc import Callable
from dataclasses import dataclass

from spacy.tokens import Span

from kert.common.model import BlockType, Lang, SplitCandidate

W_PUNCT = 1.0
W_CONJ = 0.8
W_CLAUSE = 0.6
W_ARGUMENT = 0.4
W_FALLBACK = 0.2

CUT_AFTER_PUNCT = frozenset({",", ";", ":", "—", "–"})
CONJ_DEPS = frozenset({"mark", "cc"})
DIALOGUE_DASH = "—"
FALLBACK_MIN_TOKENS = 15
FALLBACK_STEP = 10


@dataclass(frozen=True, slots=True)
class _Labels:
    clause: frozenset[str]  # rule 3
    argument: frozenset[str]  # rule 4
    chain: frozenset[str]  # prohibition 1
    case: frozenset[str]  # prohibition 2


# RU parses use the UD labels of §4.5 verbatim; EN (ClearNLP scheme) uses the
# equivalents recorded in SPEC_NOTES (Task 4).
LABELS: dict[Lang, _Labels] = {
    "ru": _Labels(
        clause=frozenset({"advcl", "ccomp", "xcomp", "acl", "acl:relcl", "conj"}),
        argument=frozenset({"nsubj", "obj", "iobj", "obl"}),
        chain=frozenset({"flat", "flat:name", "flat:foreign", "fixed"}),
        case=frozenset({"case"}),
    ),
    "en": _Labels(
        clause=frozenset({"advcl", "ccomp", "xcomp", "acl", "relcl", "conj"}),
        argument=frozenset({"nsubj", "dobj", "dative", "prep"}),
        chain=frozenset({"compound"}),
        case=frozenset({"case", "prep"}),
    ),
}


def extract_candidates(
    sent: Span, block_type: BlockType, lang: Lang
) -> list[SplitCandidate]:
    labels = LABELS[lang]
    tokens = list(sent)
    n = len(tokens)
    start = sent.start
    chains = _chain_spans(sent, labels.chain)

    def prohibited(i: int) -> bool:
        prev, tok = tokens[i - 1], tokens[i]
        return (
            tok.is_punct
            or (i == 1 and prev.is_punct)
            or any(lo < i <= hi for lo, hi in chains)
            or prev.dep_ in labels.case
            or (prev.like_num and tok.pos_ == "NOUN")
        )

    weights: dict[int, float] = {}

    def offer(i: int, weight: float) -> None:
        if 0 < i < n and weight > weights.get(i, 0.0):
            weights[i] = weight

    for j, tok in enumerate(tokens):
        dep = tok.dep_
        if dep == "punct" and tok.text in CUT_AFTER_PUNCT:
            offer(j + 1, W_PUNCT)
        if dep in CONJ_DEPS:
            offer(j, W_CONJ)
        if dep in labels.clause:
            offer(tok.left_edge.i - start, W_CLAUSE)
        if dep in labels.argument and tok.right_edge.i > tok.left_edge.i:
            offer(tok.left_edge.i - start, W_ARGUMENT)

    result = {i: w for i, w in weights.items() if not prohibited(i)}

    if block_type == "dialogue":
        # Inline dashes override every prohibition except punctuation-initial.
        for j in range(1, n - 1):
            if tokens[j].text == DIALOGUE_DASH and not tokens[j + 1].is_punct:
                result[j + 1] = W_PUNCT

    if not result and n > FALLBACK_MIN_TOKENS:
        result = _fallback(n, prohibited)

    return [SplitCandidate(i, result[i]) for i in sorted(result)]


def _chain_spans(sent: Span, chain_deps: frozenset[str]) -> list[tuple[int, int]]:
    """Sentence-relative [min, max] of each connected component of chain edges."""
    parent: dict[int, int] = {}

    def find(x: int) -> int:
        while parent.setdefault(x, x) != x:
            x = parent[x]
        return x

    for tok in sent:
        if tok.dep_ in chain_deps:
            parent[find(tok.i)] = find(tok.head.i)

    spans: dict[int, tuple[int, int]] = {}
    for member in list(parent):
        root = find(member)
        lo, hi = spans.get(root, (member, member))
        spans[root] = (min(lo, member), max(hi, member))
    return [(lo - sent.start, hi - sent.start) for lo, hi in spans.values()]


def _fallback(n: int, prohibited: Callable[[int], bool]) -> dict[int, float]:
    result: dict[int, float] = {}
    last = 0
    for mark in range(FALLBACK_STEP, n, FALLBACK_STEP):
        i = max(mark, last + 1)
        while i < n and prohibited(i):
            i += 1
        if i < n:
            result[i] = W_FALLBACK
            last = i
    return result
