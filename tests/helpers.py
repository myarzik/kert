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
