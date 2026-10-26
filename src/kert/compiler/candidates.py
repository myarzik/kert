from spacy.tokens import Span

from kert.common.model import BlockType, Lang, SplitCandidate


def extract_candidates(
    sent: Span, block_type: BlockType, lang: Lang
) -> list[SplitCandidate]:
    raise NotImplementedError
