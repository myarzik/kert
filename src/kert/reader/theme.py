"""Theme presets and the WCAG contrast oracle (spec §17.5).

Presets hold Rich color names from the fixed xterm-256 palette (16-255), so
the hierarchy does not depend on the terminal's color scheme.
"""

from dataclasses import dataclass

from rich.color import Color


@dataclass(frozen=True, slots=True)
class Theme:
    active: str
    rest: str
    neighbor: str
    status: str


THEMES = {
    "dark": Theme("bold grey93", "grey50", "grey39", "grey50"),
    "light": Theme("bold grey3", "grey46", "grey54", "grey46"),
}


def _luminance(color: str) -> float:
    """WCAG 2.x relative luminance of a Rich color name or `#rrggbb`."""
    channels = []
    for value in Color.parse(color).get_truecolor():
        c = value / 255
        channels.append(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4)
    red, green, blue = channels
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def contrast_ratio(a: str, b: str) -> float:
    darker, lighter = sorted((_luminance(a), _luminance(b)))
    return (lighter + 0.05) / (darker + 0.05)
