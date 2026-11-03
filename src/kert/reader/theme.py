"""Theme presets and the WCAG contrast oracle (spec §17.5)."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Theme:
    active: str
    rest: str
    neighbor: str
    status: str


THEMES: dict[str, Theme] = {}


def contrast_ratio(a: str, b: str) -> float:
    raise NotImplementedError
