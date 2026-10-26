"""Golden candidate sets for RU (spec §4.5), bound to ru_core_news_sm==3.8.0.

Goldens are hand-derived by applying §4.5 to the pinned model's parse, shown
above each case as `index:text/dep>head`. A model upgrade changes parses and
requires re-deriving these (spec §2.1).
"""

import pytest
from helpers import assert_candidate_invariants

from kert.compiler.candidates import extract_candidates

pytestmark = pytest.mark.spacy

GOLDEN = [
    pytest.param(
        # 0:Он/nsubj>1 1:вышел/ROOT 2:из/case>3 3:дома/obl>1 [2,3] 4:,/punct>6
        # 5:хотя/mark>6 6:шёл/advcl>1 [4,7] 7:дождь/nsubj>6 8:./punct
        "Он вышел из дома, хотя шёл дождь.",
        "paragraph",
        # R4 obl@2; R1 after ','->5 (1.0) beats R2 mark@5 (0.8);
        # R3 advcl leftmost=4 is ',' -> suppressed
        [(2, 0.4), (5, 1.0)],
        id="comma-mark-advcl",
    ),
    pytest.param(
        # 0:Мы/nsubj 1:долго/advmod 2:гуляли/ROOT 3:по/case>4 4:парку/obl>2 [3,4]
        # 5:и/cc>6 6:разговаривали/conj>2 [5,8] 7:о/case>8 8:книгах/obl>6 [7,8]
        "Мы долго гуляли по парку и разговаривали о книгах.",
        "paragraph",
        # R4 obl@3, obl@7; R2 cc@5 (0.8) beats R3 conj leftmost@5 (0.6)
        [(3, 0.4), (5, 0.8), (7, 0.4)],
        id="cc-conj-obl",
    ),
    pytest.param(
        # 0:Девушка/nsubj>7 [0,6] 1:,/punct>3 2:которая/nsubj>3
        # 3:стояла/acl:relcl>0 [1,5] 4:у/case>5 5:окна/obl>3 [4,5] 6:,/punct>0
        # 7:улыбнулась/ROOT 8:./punct
        "Девушка, которая стояла у окна, улыбнулась.",
        "paragraph",
        # R1 ','@1->2, ','@6->7; R3 relcl leftmost=1 is ',' -> suppressed;
        # R4 obl@4; nsubj leftmost=0 never emitted
        [(2, 1.0), (4, 0.4), (7, 1.0)],
        id="relcl-commas",
    ),
    pytest.param(
        # 0:Я/nsubj 1:купил/ROOT 2:пять/nummod:gov>3 3:яблок/obj>1 [2,5]
        # 4:на/case>5 5:рынке/nmod>3 6:./punct
        "Я купил пять яблок на рынке.",
        "paragraph",
        # R4 obj@2; nmod is not in rule 4
        [(2, 0.4)],
        id="numeral-obj-nmod",
    ),
    pytest.param(
        # 0:Вчера/advmod>3 1:Иван/nsubj>3 [1,2] 2:Петров/flat:name>1
        # 3:приехал/ROOT 4:в/case>5 5:Москву/obl>3 [4,5] 6:./punct
        "Вчера Иван Петров приехал в Москву.",
        "paragraph",
        # R4 nsubj@1 (before the name chain {1,2} is allowed), obl@4
        [(1, 0.4), (4, 0.4)],
        id="flat-name",
    ),
    pytest.param(
        # 0:Он/nsubj 1:сказал/ROOT 2:,/punct>4 3:что/mark>4
        # 4:вернётся/ccomp>1 [2,5] 5:завтра/advmod>4 6:./punct
        "Он сказал, что вернётся завтра.",
        "paragraph",
        # R1 after ','->3 (1.0) beats mark@3; ccomp leftmost=2 is ',' -> suppressed
        [(3, 1.0)],
        id="comma-mark-ccomp",
    ),
    pytest.param(
        # 0:Было/cop>1 1:холодно/ROOT 2:;/punct>4 3:ветер/nsubj>4
        # 4:дул/parataxis>1 [2,6] 5:с/case>6 6:моря/obl>4 [5,6] 7:./punct
        "Было холодно; ветер дул с моря.",
        "paragraph",
        # R1 after ';'->3; single-token nsubj ignored; R4 obl@5
        [(3, 1.0), (5, 0.4)],
        id="semicolon",
    ),
    pytest.param(
        # 0:Она/nsubj 1:хотела/ROOT 2:уехать/xcomp>1 [2,2] 3:,/punct>5
        # 4:но/cc>5 5:осталась/conj>1 [3,6] 6:дома/advmod>5 7:./punct
        "Она хотела уехать, но осталась дома.",
        "paragraph",
        # R3 xcomp@2; R1 after ','->4 (1.0) beats cc@4; conj leftmost=3 is ','
        [(2, 0.6), (4, 1.0)],
        id="xcomp-comma-cc",
    ),
    pytest.param(
        # 0:—/punct>1 1:Привет/ROOT 2:,/punct>4 3:—/punct>4
        # 4:сказал/parataxis>1 [2,7] 5:он/nsubj>4 6:и/cc>7 7:улыбнулся/conj>4 [6,7]
        # 8:./punct
        "— Привет, — сказал он и улыбнулся.",
        "dialogue",
        # leading '—'->1 is a lone-punct left fragment; ','->3 lands on '—';
        # inline '—'@3 -> 4 (1.0); cc@6 (0.8) beats conj leftmost@6
        [(4, 1.0), (6, 0.8)],
        id="dialogue",
    ),
    pytest.param(
        # 0:Старый/amod>1 1:учитель/nsubj>2 [0,1] 2:читал/ROOT 3:детям/iobj>2 [3,3]
        # 4:интересную/amod>5 5:историю/obj>2 [4,5] 6:./punct
        "Старый учитель читал детям интересную историю.",
        "paragraph",
        # nsubj leftmost=0 never emitted; single-token iobj ignored; R4 obj@4
        [(4, 0.4)],
        id="iobj-obj",
    ),
]


@pytest.mark.parametrize(("text", "block_type", "expected"), GOLDEN)
def test_golden_candidates(nlp_ru, text, block_type, expected):
    (sent,) = nlp_ru(text).sents

    result = extract_candidates(sent, block_type, "ru")

    assert [(c.token_index, c.weight) for c in result] == expected


@pytest.mark.parametrize(("text", "block_type", "expected"), GOLDEN)
def test_candidate_invariants(nlp_ru, text, block_type, expected):
    (sent,) = nlp_ru(text).sents

    result = extract_candidates(sent, block_type, "ru")

    assert_candidate_invariants(sent, result, block_type, "ru")
