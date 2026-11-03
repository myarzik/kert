"""Theme presets meet the §17.5 contrast floor on the fixed 256-color palette."""

import pytest
from rich.color import Color, ColorType
from rich.style import Style

from kert.reader.theme import THEMES, contrast_ratio

BACKGROUND = {"dark": "#000000", "light": "#ffffff"}


def color(style: str) -> str:
    return Style.parse(style).color.name


def test_contrast_ratio_extremes_and_symmetry():
    assert contrast_ratio("#000000", "#ffffff") == pytest.approx(21.0)
    assert contrast_ratio("#ffffff", "#000000") == pytest.approx(21.0)
    assert contrast_ratio("grey50", "grey50") == pytest.approx(1.0)


def test_contrast_ratio_of_palette_greys():
    # Hand-computed WCAG 2.x: grey50 = #808080 vs black.
    assert contrast_ratio("grey50", "#000000") == pytest.approx(5.32, abs=0.01)
    assert contrast_ratio("grey46", "#ffffff") == pytest.approx(4.54, abs=0.01)


@pytest.mark.parametrize("name", ["dark", "light"])
def test_all_colors_come_from_the_fixed_256_palette(name):
    theme = THEMES[name]
    for style in (theme.active, theme.rest, theme.neighbor, theme.status):
        parsed = Color.parse(color(style))
        assert parsed.type is ColorType.EIGHT_BIT
        assert 16 <= parsed.number <= 255


@pytest.mark.parametrize("name", ["dark", "light"])
def test_contrast_floor(name):
    theme, bg = THEMES[name], BACKGROUND[name]
    active, rest = color(theme.active), color(theme.rest)
    neighbor, status = color(theme.neighbor), color(theme.status)

    assert contrast_ratio(rest, bg) >= 4.5
    assert contrast_ratio(neighbor, bg) >= 3.0
    assert contrast_ratio(status, bg) >= 3.0
    assert contrast_ratio(active, rest) >= 3.0
    assert contrast_ratio(rest, neighbor) >= 1.25


@pytest.mark.parametrize("name", ["dark", "light"])
def test_active_unit_is_bold(name):
    assert Style.parse(THEMES[name].active).bold


def test_presets_match_the_spec_table():
    assert THEMES["dark"] == THEMES["dark"].__class__(
        "bold grey93", "grey50", "grey39", "grey50"
    )
    assert THEMES["light"] == THEMES["light"].__class__(
        "bold grey3", "grey46", "grey54", "grey46"
    )
