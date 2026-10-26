from rich.console import RenderableType

from kert.reader.state import ReaderState


def build_frame(state: ReaderState) -> RenderableType:
    raise NotImplementedError
