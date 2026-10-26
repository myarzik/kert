"""Shared invariants for §4.5 candidate sets (independent of the implementation)."""

ALLOWED_WEIGHTS = {1.0, 0.8, 0.6, 0.4, 0.2}
CASE_DEPS = {"ru": {"case"}, "en": {"case", "prep"}}


def assert_candidate_invariants(sent, candidates, block_type, lang):
    n = len(sent)
    indices = [c.token_index for c in candidates]

    assert indices == sorted(set(indices)), "sorted, unique"
    assert all(0 < i < n for i in indices), "index 0 never present, within sentence"
    assert all(c.weight in ALLOWED_WEIGHTS for c in candidates)
    assert all(not sent[i].is_punct for i in indices), "chunk never starts with punct"
    if block_type == "paragraph":
        assert all(sent[i - 1].dep_ not in CASE_DEPS[lang] for i in indices)


def make_sentence(id, block_id, seq, text, candidates=()):
    """Whitespace-separated words plus the final period as separate tokens."""
    from kert.common.model import Sentence, SplitCandidate

    tokens, pos = [], 0
    for word in text[:-1].split(" "):
        tokens.append((pos, pos + len(word)))
        pos += len(word) + 1
    tokens.append((len(text) - 1, len(text)))
    return Sentence(
        id=id,
        block_id=block_id,
        seq=seq,
        text=text,
        tokens=tuple(tokens),
        candidates=tuple(SplitCandidate(i, w) for i, w in candidates),
    )


def mini_book():
    """Three blocks, 22 words. At W=5 (§6, n=10, C={5: 1.0}: {5} costs 0.0,
    {} costs 1.0) the chunks are, as (sentence, tokens, words, words before):

    0: S1 [0,3) 2 0   block 1  "Глава один."
    1: S2 [0,5) 5 2   block 2  "alpha bravo charlie delta echo"
    2: S2 [5,10) 4 7  block 2  "foxtrot golf hotel india."
    3: S3 [0,3) 2 11  block 2  "Short one."
    4: S4 [0,5) 5 13  block 3  "one two three four five"
    5: S4 [5,10) 4 18 block 3  "six seven eight nine."

    At W=8 every sentence has n <= W+2: one chunk each (S1..S4 = 0..3).
    """
    from kert.common.model import Block
    from kert.reader.state import Book

    return Book(
        blocks=(Block(1, "paragraph"), Block(2, "paragraph"), Block(3, "paragraph")),
        sentences=(
            make_sentence(1, 1, 0, "Глава один."),
            make_sentence(
                2,
                2,
                0,
                "alpha bravo charlie delta echo foxtrot golf hotel india.",
                [(5, 1.0)],
            ),
            make_sentence(3, 2, 1, "Short one."),
            make_sentence(
                4, 3, 0, "one two three four five six seven eight nine.", [(5, 1.0)]
            ),
        ),
        word_count=22,
    )
