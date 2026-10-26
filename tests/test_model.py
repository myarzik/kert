import dataclasses

import pytest

from kert.common.model import Block, ChunkSpan, Sentence, SplitCandidate


def field_names(cls):
    return [f.name for f in dataclasses.fields(cls)]


def test_block_fields_mirror_blocks_table():
    assert field_names(Block) == ["id", "type", "chapter"]


def test_block_chapter_defaults_to_none():
    assert Block(id=1, type="paragraph").chapter is None


def test_sentence_fields_mirror_sentences_table():
    assert field_names(Sentence) == [
        "id",
        "block_id",
        "seq",
        "text",
        "tokens",
        "candidates",
    ]


def test_split_candidate_fields():
    assert field_names(SplitCandidate) == ["token_index", "weight"]


def test_chunk_span_fields():
    assert field_names(ChunkSpan) == ["sentence_id", "start_token", "end_token"]


@pytest.mark.parametrize(
    "instance",
    [
        Block(id=1, type="paragraph"),
        Sentence(
            id=1,
            block_id=1,
            seq=0,
            text="Hi.",
            tokens=((0, 2), (2, 3)),
            candidates=(),
        ),
        SplitCandidate(token_index=1, weight=1.0),
        ChunkSpan(sentence_id=1, start_token=0, end_token=2),
    ],
)
def test_content_models_are_immutable(instance):
    # Content is write-never after compilation (D8).
    first_field = dataclasses.fields(instance)[0].name
    with pytest.raises(dataclasses.FrozenInstanceError):
        setattr(instance, first_field, 2)
