"""Rule-level tests for spec §4.5 on hand-specified parses (no model needed).

Each row is (word, head, dep[, pos]); heads are absolute token indices.
Per-language label sets follow SPEC_NOTES (Task 4): RU uses the UD labels of
§4.5 verbatim; EN (ClearNLP scheme) maps acl:relcl→relcl, obj→dobj,
iobj→dative, obl→prep, flat*→compound, case→{prep, case}; `fixed` has no EN
equivalent.
"""

from functools import cache

import pytest
import spacy
from spacy.tokens import Doc

from kert.compiler.candidates import extract_candidates


@cache
def _vocab(lang):
    return spacy.blank(lang).vocab


def build(lang, rows):
    doc = Doc(
        _vocab(lang),
        words=[r[0] for r in rows],
        heads=[r[1] for r in rows],
        deps=[r[2] for r in rows],
        pos=[r[3] if len(r) > 3 else "X" for r in rows],
    )
    return doc[:]


def cands(lang, rows, block_type="paragraph"):
    result = extract_candidates(build(lang, rows), block_type, lang)
    return [(c.token_index, c.weight) for c in result]


def plain(n):
    """n tokens, no rule fires: token 0 is ROOT, the rest advmod on it."""
    return [("w0", 0, "ROOT")] + [(f"w{i}", 0, "advmod") for i in range(1, n)]


# --- Rule 1: sentence-internal punctuation, cut AFTER -----------------------


@pytest.mark.parametrize("lang", ["ru", "en"])
@pytest.mark.parametrize("mark", [",", ";", ":", "—", "–"])
def test_rule1_cut_after_listed_punct(lang, mark):
    rows = [("a", 0, "ROOT"), ("b", 0, "advmod"), (mark, 0, "punct"),
            ("c", 0, "advmod"), ("d", 0, "advmod")]  # fmt: skip

    assert cands(lang, rows) == [(3, 1.0)]


@pytest.mark.parametrize("mark", ["(", ")", '"', "!", "..."])
def test_rule1_ignores_unlisted_punct(mark):
    rows = [("a", 0, "ROOT"), ("b", 0, "advmod"), (mark, 0, "punct"),
            ("c", 0, "advmod"), ("d", 0, "advmod")]  # fmt: skip

    assert cands("ru", rows) == []


def test_rule1_requires_punct_dep():
    rows = [("a", 0, "ROOT"), ("b", 0, "advmod"), (",", 0, "dep"),
            ("c", 0, "advmod"), ("d", 0, "advmod")]  # fmt: skip

    assert cands("ru", rows) == []


def test_rule1_no_candidate_past_sentence_end():
    rows = [("a", 0, "ROOT"), ("b", 0, "advmod"), (",", 0, "punct")]

    assert cands("ru", rows) == []


# --- Rule 2: mark / cc, cut BEFORE ------------------------------------------


@pytest.mark.parametrize("lang", ["ru", "en"])
@pytest.mark.parametrize("dep", ["mark", "cc"])
def test_rule2_cut_before_conjunction(lang, dep):
    rows = [("a", 0, "ROOT"), ("b", 0, "advmod"), ("c", 0, dep),
            ("d", 0, "advmod")]  # fmt: skip

    assert cands(lang, rows) == [(2, 0.8)]


# --- Rule 3: leftmost token of clause-like subtree --------------------------


def clause_rows(dep):
    # token 3 has subtree [2, 4]; leftmost token is 2
    return [("a", 0, "ROOT"), ("b", 0, "advmod"), ("c", 3, "advmod"),
            ("d", 0, dep), ("e", 3, "advmod")]  # fmt: skip


@pytest.mark.parametrize(
    ("lang", "dep"),
    [("ru", d) for d in ["advcl", "ccomp", "xcomp", "acl", "acl:relcl", "conj"]]
    + [("en", d) for d in ["advcl", "ccomp", "xcomp", "acl", "relcl", "conj"]],
)
def test_rule3_cut_before_clause_subtree(lang, dep):
    assert cands(lang, clause_rows(dep)) == [(2, 0.6)]


@pytest.mark.parametrize(("lang", "dep"), [("ru", "relcl"), ("en", "acl:relcl")])
def test_rule3_label_set_is_per_language(lang, dep):
    assert cands(lang, clause_rows(dep)) == []


# --- Rule 4: leftmost token of argument subtree spanning >= 2 tokens --------

RU_ARGS = ["nsubj", "obj", "iobj", "obl"]
EN_ARGS = ["nsubj", "dobj", "dative", "prep"]


@pytest.mark.parametrize(
    ("lang", "dep"), [("ru", d) for d in RU_ARGS] + [("en", d) for d in EN_ARGS]
)
def test_rule4_cut_before_multi_token_argument(lang, dep):
    assert cands(lang, clause_rows(dep)) == [(2, 0.4)]


@pytest.mark.parametrize(
    ("lang", "dep"), [("ru", d) for d in RU_ARGS] + [("en", d) for d in EN_ARGS]
)
def test_rule4_ignores_single_token_argument(lang, dep):
    rows = [("a", 0, "ROOT"), ("b", 0, "advmod"), ("c", 0, dep),
            ("d", 0, "advmod")]  # fmt: skip

    assert cands(lang, rows) == []


@pytest.mark.parametrize(
    ("lang", "dep"), [("ru", "dobj"), ("ru", "dative"), ("en", "obj"), ("en", "obl")]
)
def test_rule4_label_set_is_per_language(lang, dep):
    assert cands(lang, clause_rows(dep)) == []


# --- Merging, bounds ----------------------------------------------------------


def test_same_index_keeps_max_weight():
    # mark at 2 (0.8) coincides with the leftmost token of advcl (0.6)
    rows = [("a", 0, "ROOT"), ("b", 0, "advmod"), ("c", 3, "mark"),
            ("d", 0, "advcl"), ("e", 3, "advmod")]  # fmt: skip

    assert cands("ru", rows) == [(2, 0.8)]


def test_punct_and_mark_at_same_index_keeps_one():
    # comma at 2 -> 3 (1.0); mark at 3 (0.8); advcl leftmost is the comma (2)
    rows = [("a", 0, "ROOT"), ("b", 0, "advmod"), (",", 4, "punct"),
            ("c", 4, "mark"), ("d", 0, "advcl"), ("e", 4, "advmod")]  # fmt: skip

    assert cands("ru", rows) == [(3, 1.0)]


def test_never_candidate_at_index_zero():
    rows = [("a", 1, "amod"), ("b", 2, "nsubj"), ("c", 2, "ROOT")]

    assert cands("ru", rows) == []


def test_indices_are_relative_to_the_sentence():
    doc = Doc(
        _vocab("ru"),
        words=["x", ".", "a", "b", ",", "c", "d"],
        heads=[0, 0, 2, 2, 2, 2, 2],
        deps=["ROOT", "punct", "ROOT", "advmod", "punct", "advmod", "advmod"],
    )
    second = list(doc.sents)[1]

    result = extract_candidates(second, "paragraph", "ru")

    assert [(c.token_index, c.weight) for c in result] == [(3, 1.0)]


def test_output_sorted_by_token_index():
    rows = [("a", 0, "ROOT"), ("b", 0, "advmod"), (",", 0, "punct"),
            ("c", 0, "advmod"), ("d", 0, "cc"), ("e", 0, "advmod")]  # fmt: skip

    assert cands("ru", rows) == [(3, 1.0), (4, 0.8)]


# --- Prohibition 1: never cut inside a flat/fixed (EN: compound) chain -------


@pytest.mark.parametrize("dep", ["flat", "flat:name", "flat:foreign", "fixed"])
def test_ru_no_cut_inside_chain_but_before_and_after_allowed(dep):
    # chain = {1, 3}; comma at 2 would cut at 3 (inside the chain)
    rows = [("x", 0, "ROOT"), ("Иван", 0, "obj"), (",", 3, "punct"),
            ("Петров", 1, dep), ("что", 5, "mark"),
            ("y", 0, "advcl")]  # fmt: skip

    assert cands("ru", rows) == [(1, 0.4), (4, 0.8)]


def test_en_compound_is_a_chain():
    rows = [("x", 0, "ROOT"), ("John", 3, "compound"), (",", 3, "punct"),
            ("Smith", 0, "dobj"), ("that", 5, "mark"),
            ("y", 0, "advcl")]  # fmt: skip

    assert cands("en", rows) == [(1, 0.4), (4, 0.8)]


def test_ru_compound_is_not_a_chain():
    rows = [("x", 0, "ROOT"), ("a", 3, "compound"), (",", 3, "punct"),
            ("b", 0, "obj"), ("что", 5, "mark"), ("y", 0, "advcl")]  # fmt: skip

    assert cands("ru", rows) == [(1, 0.4), (3, 1.0), (4, 0.8)]


# --- Prohibition 2: never cut right after a bare preposition -----------------


def test_ru_no_cut_after_case():
    rows = [("x", 0, "ROOT"), ("в", 0, "case"), ("и", 0, "cc")]

    assert cands("ru", rows) == []


@pytest.mark.parametrize("dep", ["prep", "case"])
def test_en_no_cut_after_prep_or_case(dep):
    rows = [("x", 0, "ROOT"), ("in", 0, dep), ("and", 0, "cc")]

    assert cands("en", rows) == []


def test_ru_prep_label_is_not_case():
    rows = [("x", 0, "ROOT"), ("в", 0, "prep"), ("и", 0, "cc")]

    assert cands("ru", rows) == [(2, 0.8)]


# --- Prohibition 3: number + noun stay together -----------------------------


def test_no_cut_between_number_and_noun():
    rows = [("x", 0, "ROOT"), ("5", 0, "nummod", "NUM"), ("y", 0, "cc", "NOUN")]

    assert cands("ru", rows) == []


def test_number_followed_by_non_noun_may_be_cut():
    rows = [("x", 0, "ROOT"), ("5", 0, "nummod", "NUM"), ("y", 0, "cc", "ADJ")]

    assert cands("ru", rows) == [(2, 0.8)]


# --- Prohibitions 4 and 5: punctuation ----------------------------------------


def test_chunk_never_starts_with_punctuation():
    # advcl leftmost token is the comma at 2 -> suppressed; comma itself -> 3
    rows = [("x", 0, "ROOT"), ("y", 0, "advmod"), (",", 3, "punct"),
            ("z", 0, "advcl")]  # fmt: skip

    assert cands("ru", rows) == [(3, 1.0)]


def test_left_fragment_never_a_lone_punctuation_token():
    rows = [("—", 1, "punct"), ("x", 1, "ROOT"), ("y", 1, "advmod")]

    assert cands("ru", rows) == []


# --- Dialogue augmentation (D10) ----------------------------------------------


def test_dialogue_inline_dash_cut_even_without_punct_dep():
    rows = [("x", 0, "ROOT"), ("y", 0, "advmod"), ("—", 0, "dep"),
            ("z", 0, "advmod")]  # fmt: skip

    assert cands("ru", rows, "dialogue") == [(3, 1.0)]
    assert cands("ru", rows, "paragraph") == []


def test_dialogue_dash_overrides_chain_prohibition():
    rows = [("x", 0, "ROOT"), ("Иван", 0, "obj"), ("—", 3, "punct"),
            ("Петров", 1, "flat:name")]  # fmt: skip

    assert cands("ru", rows, "paragraph") == [(1, 0.4)]
    assert cands("ru", rows, "dialogue") == [(1, 0.4), (3, 1.0)]


def test_dialogue_dash_still_never_starts_chunk_with_punctuation():
    rows = [("x", 0, "ROOT"), ("y", 0, "advmod"), ("—", 0, "punct"),
            (",", 0, "punct"), ("z", 0, "advmod")]  # fmt: skip

    assert cands("ru", rows, "dialogue") == [(4, 1.0)]


def test_dialogue_leading_dash_is_not_inline():
    rows = [("—", 1, "punct"), ("x", 1, "ROOT"), ("y", 1, "advmod")]

    assert cands("ru", rows, "dialogue") == []


# --- Guaranteed fallback -------------------------------------------------------


@pytest.mark.parametrize(
    ("n", "expected"),
    [
        (15, []),
        (16, [(10, 0.2)]),
        (20, [(10, 0.2)]),
        (21, [(10, 0.2), (20, 0.2)]),
        (25, [(10, 0.2), (20, 0.2)]),
    ],
)
def test_fallback_every_ten_tokens_for_long_candidate_less_sentence(n, expected):
    assert cands("ru", plain(n)) == expected


def test_fallback_shifts_forward_past_prohibited_positions():
    rows = plain(16)
    rows[9] = ("в", 0, "case")  # forbids a cut at 10
    rows[11] = ("(", 0, "punct")  # forbids a cut at 11

    assert cands("ru", rows) == [(12, 0.2)]


def test_fallback_emits_nothing_when_no_allowed_position_remains():
    rows = plain(16)
    for i in range(10, 16):
        rows[i] = ("(", 0, "punct")

    assert cands("ru", rows) == []


def test_no_fallback_when_any_candidate_exists():
    rows = plain(20)
    rows[3] = ("и", 0, "cc")

    assert cands("ru", rows) == [(3, 0.8)]
