"""Golden candidate sets for EN (spec §4.5), bound to en_core_web_sm==3.8.0.

Goldens are hand-derived by applying §4.5 with the EN label mapping
(SPEC_NOTES, Task 4) to the pinned model's parse, shown above each case as
`index:text/dep>head`. A model upgrade requires re-deriving these (§2.1).
"""

import pytest
from helpers import assert_candidate_invariants

from kert.compiler.candidates import extract_candidates

pytestmark = pytest.mark.spacy

GOLDEN = [
    pytest.param(
        # 0:He/nsubj 1:left/ROOT 2:the/det>3 3:house/dobj>1 [2,3]
        # 4:because/mark>7 5:it/nsubj>7 6:was/aux>7 7:raining/advcl>1 [4,7]
        # 8:./punct
        "He left the house because it was raining.",
        # R4 dobj@2; R2 mark@4 (0.8) beats R3 advcl leftmost@4
        [(2, 0.4), (4, 0.8)],
        id="mark-advcl-dobj",
    ),
    pytest.param(
        # 0:She/nsubj 1:gave/ROOT 2:the/det>4 3:old/amod>4 4:man/dative>1 [2,4]
        # 5:a/det>6 6:book/dobj>1 [5,6] 7:in/prep>1 [7,9] 8:the/det>9
        # 9:morning/pobj>7 10:./punct
        "She gave the old man a book in the morning.",
        # R4 dative@2, dobj@5, prep@7
        [(2, 0.4), (5, 0.4), (7, 0.4)],
        id="dative-dobj-prep",
    ),
    pytest.param(
        # 0:The/det>1 1:girl/nsubj>7 [0,6] 2:who/nsubj>3 3:stood/relcl>1 [2,6]
        # 4:by/prep>3 [4,6] 5:the/det>6 6:window/pobj>4 7:smiled/ROOT 8:./punct
        "The girl who stood by the window smiled.",
        # R3 relcl@2; R4 prep@4; nsubj leftmost=0 never emitted
        [(2, 0.6), (4, 0.4)],
        id="relcl-prep",
    ),
    pytest.param(
        # 0:I/nsubj 1:bought/ROOT 2:five/nummod>3 3:apples/dobj>1 [2,3]
        # 4:at/prep>1 [4,6] 5:the/det>6 6:market/pobj>4 7:./punct
        "I bought five apples at the market.",
        # R4 dobj@2, prep@4
        [(2, 0.4), (4, 0.4)],
        id="numeral-dobj-prep",
    ),
    pytest.param(
        # 0:Yesterday/npadvmod>3 1:John/compound>2 2:Smith/nsubj>3 [1,2]
        # 3:arrived/ROOT 4:in/prep>3 [4,5] 5:London/pobj>4 6:./punct
        "Yesterday John Smith arrived in London.",
        # R4 nsubj@1 (before the compound chain {1,2}), prep@4
        [(1, 0.4), (4, 0.4)],
        id="compound-name",
    ),
    pytest.param(
        # 0:He/nsubj 1:said/ROOT 2:that/mark>5 3:he/nsubj>5 4:would/aux>5
        # 5:come/ccomp>1 [2,7] 6:back/advmod>5 7:tomorrow/npadvmod>5 8:./punct
        "He said that he would come back tomorrow.",
        # R2 mark@2 (0.8) beats R3 ccomp leftmost@2
        [(2, 0.8)],
        id="mark-ccomp",
    ),
    pytest.param(
        # 0:It/nsubj>1 1:was/ccomp>6 [0,2] 2:cold/acomp>1 3:;/punct>6
        # 4:the/det>5 5:wind/nsubj>6 [4,5] 6:blew/ROOT 7:from/prep>6 [7,9]
        # 8:the/det>9 9:sea/pobj>7 10:./punct
        "It was cold; the wind blew from the sea.",
        # R1 after ';'->4 (1.0) beats nsubj@4; ccomp leftmost=0 never emitted;
        # R4 prep@7
        [(4, 1.0), (7, 0.4)],
        id="semicolon",
    ),
    pytest.param(
        # 0:She/nsubj 1:wanted/ROOT 2:to/aux>3 3:leave/xcomp>1 [2,3] 4:,/punct>1
        # 5:but/cc>1 6:she/nsubj>7 7:stayed/conj>1 [6,9] 8:home/advmod>7
        # 9:./punct
        "She wanted to leave, but she stayed home.",
        # R3 xcomp@2; R1 after ','->5 (1.0) beats cc@5; R3 conj leftmost@6
        [(2, 0.6), (5, 1.0), (6, 0.6)],
        id="xcomp-comma-cc-conj",
    ),
    pytest.param(
        # 0:We/nsubj 1:walked/ROOT 2:in/prep>1 [2,4] 3:the/det>4 4:park/pobj>2
        # 5:and/cc>1 6:talked/conj>1 [6,8] 7:about/prep>6 [7,8] 8:books/pobj>7
        # 9:./punct
        "We walked in the park and talked about books.",
        # R4 prep@2, prep@7; R2 cc@5; R3 conj@6
        [(2, 0.4), (5, 0.8), (6, 0.6), (7, 0.4)],
        id="cc-conj-prep",
    ),
    pytest.param(
        # 0:The/det>2 1:old/amod>2 2:teacher/nsubj>3 [0,2] 3:told/ROOT
        # 4:the/det>5 5:children/dative>3 [4,5] 6:an/det>8 7:interesting/amod>8
        # 8:story/dobj>3 [6,8] 9:./punct
        "The old teacher told the children an interesting story.",
        # R4 dative@4, dobj@6; nsubj leftmost=0 never emitted
        [(4, 0.4), (6, 0.4)],
        id="dative-dobj",
    ),
]


@pytest.mark.parametrize(("text", "expected"), GOLDEN)
def test_golden_candidates(nlp_en, text, expected):
    (sent,) = nlp_en(text).sents

    result = extract_candidates(sent, "paragraph", "en")

    assert [(c.token_index, c.weight) for c in result] == expected


@pytest.mark.parametrize(("text", "expected"), GOLDEN)
def test_candidate_invariants(nlp_en, text, expected):
    (sent,) = nlp_en(text).sents

    result = extract_candidates(sent, "paragraph", "en")

    assert_candidate_invariants(sent, result, "paragraph", "en")
