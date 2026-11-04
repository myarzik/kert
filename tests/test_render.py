import pytest
from helpers import make_sentence, mini_book
from readchar import key
from rich.console import Console

from kert.common.model import Block
from kert.reader.config import Settings
from kert.reader.render import build_frame
from kert.reader.state import Book, handle_key, initial_state
from kert.reader.store import Position

DARK = Settings(chunk_width=5, theme="dark")
LIGHT = Settings(chunk_width=5, theme="light")

# mini_book at 44 columns: text width min(44-4, 88) = 40, left margin 2.
B1 = "Глава один."
B2 = ("alpha bravo charlie delta echo foxtrot", "golf hotel india. Short one.")
B3 = ("one two three four five six seven eight", "nine.")


def state_at(position, size, settings=DARK, book=None):
    return initial_state(book or mini_book(), settings, position, size=size)


def console_for(state):
    width, height = state.size
    return Console(
        width=width,
        height=height,
        record=True,
        force_terminal=True,
        color_system="256",
        legacy_windows=False,
    )


def lines(state):
    console = console_for(state)
    console.print(build_frame(state))
    return [line.rstrip() for line in console.export_text().split("\n")[:-1]]


def segments(state):
    console = console_for(state)
    return list(console.render(build_frame(state)))


def style_of(state, text):
    segment = next(s for s in segments(state) if text in s.text)
    return segment.style.color.name, bool(segment.style.bold)


def status(percent, left="", margin=2, width=40):
    return " " * margin + left + " " * (width - len(left) - len(percent)) + percent


# --- Center focus layout (§7.1) -------------------------------------------------------
# Reading area H = rows - 1; the active chunk's first line sits on row (H - h) // 2.


ACTIVE_COLORS = {"grey93", "grey3"}  # §17.5 active unit; headings are bold too


def active_rows(state):
    """Rows whose text includes the bold active chunk."""
    console = console_for(state)
    rendered = console.render_lines(build_frame(state), console.options, pad=False)
    return [
        row
        for row, line in enumerate(rendered)
        if any(
            seg.style
            and seg.style.bold
            and seg.style.color.name in ACTIVE_COLORS
            and seg.text.strip()
            for seg in line
        )
    ]


def test_chunk_on_first_line_of_block_sits_on_center_row():
    # H=11, h=1 -> row 5; above: B1 + blank; below: rest of B2, blank, B3.
    assert lines(state_at(Position(2, 0), (44, 12))) == [
        "",
        "",
        "",
        f"  {B1}",
        "",
        f"  {B2[0]}",
        f"  {B2[1]}",
        "",
        f"  {B3[0]}",
        f"  {B3[1]}",
        "",
        status("9.1%"),  # 2 / 22 words
    ]


def test_chunk_on_second_line_of_block_also_sits_on_center_row():
    # "Short one." is on B2's second line: B2's first line moves above the center.
    assert lines(state_at(Position(3, 0), (44, 12))) == [
        "",
        "",
        f"  {B1}",
        "",
        f"  {B2[0]}",
        f"  {B2[1]}",
        "",
        f"  {B3[0]}",
        f"  {B3[1]}",
        "",
        "",
        status("50.0%"),  # 11 / 22 words
    ]


def test_two_line_chunk_is_centered_as_a_whole():
    # "foxtrot golf hotel india." spans both B2 lines: h=2 -> rows 4-5.
    state = state_at(Position(2, 5), (44, 12))

    assert lines(state) == [
        "",
        "",
        f"  {B1}",
        "",
        f"  {B2[0]}",
        f"  {B2[1]}",
        "",
        f"  {B3[0]}",
        f"  {B3[1]}",
        "",
        "",
        status("31.8%"),  # 7 / 22 words
    ]
    assert active_rows(state) == [4, 5]


def test_book_start_leaves_space_above_and_cuts_text_below():
    # Nothing precedes B1; B3's second line falls below the screen edge, unmarked.
    assert lines(state_at(Position(1, 0), (44, 12))) == [
        "",
        "",
        "",
        "",
        "",
        f"  {B1}",
        "",
        f"  {B2[0]}",
        f"  {B2[1]}",
        "",
        f"  {B3[0]}",
        status("0.0%"),
    ]


def test_book_end_leaves_space_below():
    # "six seven eight nine." spans both B3 lines (h=2 -> rows 4-5).
    assert lines(state_at(Position(4, 5), (44, 12))) == [
        "",
        f"  {B2[0]}",
        f"  {B2[1]}",
        "",
        f"  {B3[0]}",
        f"  {B3[1]}",
        "",
        "",
        "",
        "",
        "",
        status("81.8%"),
    ]


def test_short_screen_cuts_neighbors_at_both_edges():
    # H=5, h=1 -> row 2: two rows above, three below.
    assert lines(state_at(Position(2, 0), (44, 6))) == [
        f"  {B1}",
        "",
        f"  {B2[0]}",
        f"  {B2[1]}",
        "",
        status("9.1%"),
    ]


@pytest.mark.parametrize("rows", [6, 12, 25])
def test_focus_stays_on_center_row_while_reading(rows):
    state = state_at(Position(1, 0), (44, rows))
    center = (rows - 1 - 1) // 2
    for _ in range(len(state.chunks.spans)):
        assert center in active_rows(state)
        state = handle_key(state, "j")


def test_text_width_is_capped_at_88_and_centered():
    frame = lines(state_at(Position(2, 0), (120, 12)))

    assert f"{' ' * 16}{B2[0]} {B2[1]}" in frame
    assert frame[-1] == status("9.1%", margin=16, width=88)


def test_frame_fills_terminal_height():
    assert len(lines(state_at(Position(4, 5), (44, 20)))) == 20


# --- Blocks taller than the screen (§7.1) --------------------------------------------

TALL_WORDS = ("alpha", "gamma", "kappa", "omega", "sigma", "theta", "zetas", "betas")
TALL = [f"{w} bravo charlie delta echo golf." for w in TALL_WORDS]  # 36 chars


def tall_book():
    # One 8-line block (each 36-char sentence fills a 40-col line) + a neighbor.
    return Book(
        blocks=(Block(1, "paragraph"), Block(2, "paragraph")),
        sentences=(
            *(make_sentence(i + 1, 1, i, text) for i, text in enumerate(TALL)),
            make_sentence(9, 2, 0, "Short one."),
        ),
        word_count=50,
    )


def tall_at(sentence_id):
    return state_at(Position(sentence_id, 0), (44, 6), book=tall_book())


def test_tall_block_start_keeps_focus_centered():
    assert lines(tall_at(1))[:-1] == ["", "", *(f"  {t}" for t in TALL[:3])]


def test_tall_block_middle_scrolls_like_a_tape():
    assert lines(tall_at(5))[:-1] == [f"  {t}" for t in TALL[2:7]]


def test_tall_block_end_shows_the_next_block():
    assert lines(tall_at(8))[:-1] == [
        *(f"  {t}" for t in TALL[5:]),
        "",
        "  Short one.",
    ]


@pytest.mark.parametrize("sentence_id", range(1, 9))
def test_active_chunk_always_visible_in_tall_block(sentence_id):
    state = tall_at(sentence_id)

    assert style_of(state, TALL[sentence_id - 1]) == ("grey93", True)
    assert active_rows(state) == [2]


def test_cut_edges_have_no_marker():
    assert not any("…" in line for line in lines(tall_at(5)))


# --- Styles (§17.5) -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("settings", "active", "rest", "neighbor", "status_color"),
    [
        (DARK, "grey93", "grey50", "grey39", "grey50"),
        (LIGHT, "grey3", "grey46", "grey54", "grey46"),
    ],
)
def test_theme_presets(settings, active, rest, neighbor, status_color):
    state = state_at(Position(2, 0), (44, 12), settings)

    assert style_of(state, "alpha bravo charlie delta echo") == (active, True)
    assert style_of(state, "foxtrot") == (rest, False)
    assert style_of(state, "golf hotel india. Short one.") == (rest, False)
    assert style_of(state, B1) == (neighbor, False)
    assert style_of(state, B3[0]) == (neighbor, False)
    assert style_of(state, "9.1%") == (status_color, False)


def test_active_chunk_spanning_a_line_break_is_styled_on_both_lines():
    state = state_at(Position(2, 0), (44, 12), Settings(chunk_width=8, theme="dark"))

    assert style_of(state, B2[0]) == ("grey93", True)
    assert style_of(state, "golf hotel india.") == ("grey93", True)
    assert style_of(state, "Short one.") == ("grey50", False)


@pytest.mark.parametrize("settings", [DARK, LIGHT])
def test_no_dim_attribute_anywhere(settings):
    for state in (
        state_at(Position(2, 0), (44, 12), settings),
        state_at(Position(5, 0), (44, 6), settings, book=tall_book()),
    ):
        assert not any(s.style and s.style.dim for s in segments(state))


# --- Status line (§7.1) ---------------------------------------------------------------


def test_status_shows_command_input():
    state = state_at(Position(2, 0), (44, 12))
    for k in ":set wi":
        state = handle_key(state, k)

    assert lines(state)[-1] == status("9.1%", left=":set wi")
    assert style_of(state, ":set wi") == ("grey50", False)


def test_status_shows_message():
    state = state_at(Position(2, 0), (44, 12))
    for k in [":", "f", "o", "o", key.ENTER]:
        state = handle_key(state, k)

    assert lines(state)[-1] == status("9.1%", left=state.message)


def test_status_percent_has_one_decimal():
    assert lines(state_at(Position(4, 5), (44, 12)))[-1] == status("81.8%")


# --- Narrow terminal (task 10) --------------------------------------------------------

NARROW = "Terminal too narrow: 40+ columns needed"


def test_terminal_narrower_than_40_columns_shows_only_a_notice():
    frame = lines(state_at(Position(2, 0), (39, 12)))

    assert frame == [NARROW] + [""] * 11


def test_notice_is_cropped_to_very_narrow_terminals():
    frame = lines(state_at(Position(2, 0), (20, 5)))

    assert frame == [NARROW[:20]] + [""] * 4


def test_40_columns_renders_the_book():
    frame = lines(state_at(Position(2, 0), (40, 12)))

    assert NARROW not in frame
    assert any("alpha" in line for line in frame)


@pytest.mark.parametrize("settings", [DARK, LIGHT])
def test_narrow_notice_uses_status_style(settings):
    color = "grey50" if settings is DARK else "grey46"
    state = state_at(Position(2, 0), (39, 12), settings)

    assert style_of(state, "Terminal too narrow") == (color, False)


# --- Headings and code blocks (§14.7) ------------------------------------------------


def typed_book():
    from kert.common.model import Sentence
    from kert.common.text import whitespace_tokens

    def unchunked(id, block_id, text):
        return Sentence(id, block_id, 0, text, whitespace_tokens(text), ())

    return Book(
        blocks=(
            Block(1, "heading", chapter=1),
            Block(2, "paragraph", chapter=1),
            Block(3, "code", chapter=1),
            Block(4, "paragraph", chapter=1),
        ),
        sentences=(
            unchunked(1, 1, "Глава один"),
            make_sentence(2, 2, 0, "Short one."),
            unchunked(3, 3, "def f():\n    return 1"),
            make_sentence(4, 4, 0, "Last one."),
        ),
        word_count=8,
    )


def typed_at(sentence_id, settings=DARK):
    return state_at(Position(sentence_id, 0), (44, 12), settings, book=typed_book())


@pytest.mark.parametrize(
    ("settings", "active", "neighbor"),
    [(DARK, "grey93", "grey39"), (LIGHT, "grey3", "grey54")],
)
def test_heading_is_bold_active_or_not(settings, active, neighbor):
    assert style_of(typed_at(1, settings), "Глава один") == (active, True)
    assert style_of(typed_at(2, settings), "Глава один") == (neighbor, True)


def test_code_keeps_line_breaks_and_indentation():
    frame = lines(typed_at(3))

    i = frame.index("  def f():")
    assert frame[i + 1] == "      return 1"


@pytest.mark.parametrize(
    ("sentence_id", "style"), [(3, ("grey93", True)), (2, ("grey39", False))]
)
def test_code_styles_active_and_neighbor(sentence_id, style):
    assert style_of(typed_at(sentence_id), "return 1") == style


def test_code_block_is_centered_as_one_chunk():
    # h=2 -> rows 4-5 of H=11.
    assert active_rows(typed_at(3)) == [4, 5]


def test_long_code_line_wraps_within_text_width():
    from kert.common.model import Sentence
    from kert.common.text import whitespace_tokens

    code = "x = 1  # " + "word " * 12
    book = Book(
        blocks=(Block(1, "code"),),
        sentences=(Sentence(1, 1, 0, code, whitespace_tokens(code), ()),),
        word_count=13,
    )
    frame = lines(state_at(Position(1, 0), (44, 12), book=book))

    assert all(len(line) <= 42 for line in frame[:-1])
    assert sum(1 for line in frame[:-1] if line) == 2


# --- Peek (§17.3) ---------------------------------------------------------------------


def test_peek_renders_the_previous_unit_active_and_the_real_one_as_rest():
    state = handle_key(state_at(Position(2, 5), (44, 12)), "p")

    assert style_of(state, "alpha bravo charlie delta echo") == ("grey93", True)
    assert style_of(state, "golf hotel india.") == ("grey50", False)


def test_leaving_peek_restores_the_frame():
    state = state_at(Position(2, 5), (44, 12))

    assert lines(handle_key(handle_key(state, "p"), "x")) == lines(state)


# --- Reading modes (§17.2) ------------------------------------------------------------


def test_sentence_mode_highlights_the_whole_sentence():
    settings = Settings(chunk_width=5, theme="dark", mode="sentence")
    state = state_at(Position(2, 0), (44, 12), settings)

    assert style_of(state, "alpha bravo charlie delta echo") == ("grey93", True)
    assert style_of(state, "golf hotel india.") == ("grey93", True)
    assert style_of(state, "Short one.") == ("grey50", False)


def test_paragraph_mode_highlights_the_whole_block():
    settings = Settings(chunk_width=5, theme="dark", mode="paragraph")
    state = state_at(Position(2, 0), (44, 12), settings)

    assert style_of(state, "alpha bravo charlie delta echo") == ("grey93", True)
    assert style_of(state, "Short one.") == ("grey93", True)
    assert style_of(state, B1) == ("grey39", False)
    assert active_rows(state) == [4, 5]


def test_paragraph_mode_peek_shows_the_previous_block():
    settings = Settings(chunk_width=5, theme="dark", mode="paragraph")
    state = handle_key(state_at(Position(4, 0), (44, 12), settings), "p")

    assert style_of(state, "Short one.") == ("grey93", True)
    assert style_of(state, B3[0]) == ("grey39", False)


# --- R5 goal segment (§17.6) ----------------------------------------------------------


def fast_log(wps_words=4, dwell=2.0, n=31):
    from kert.reader.tempo import LogRow

    return tuple(
        LogRow(1000.0 + i * dwell, wps_words, 1, "step", "chunk") for i in range(n)
    )


def goal_state(command, log=()):
    # The clock is past the log, so none of its dwells count after arming.
    state = initial_state(
        mini_book(), DARK, Position(1, 0), size=(44, 12), now=2000.0, log=log
    )
    return handle_key_seq(state, [":", *command, key.ENTER])


def handle_key_seq(state, keys):
    for k in keys:
        state = handle_key(state, k)
    return state


def test_words_goal_without_tempo_shows_remaining_words():
    state = goal_state("goal 20w")

    assert lines(state)[-1] == status("▸ 20 w   0.0%", left="goal 20w")


def test_words_goal_with_tempo_adds_the_eta():
    # 2 words per second: 20 words take 10 s, shown as at least ~1 min.
    state = goal_state("goal 20w", log=fast_log())

    assert lines(state)[-1] == status("▸ 20 w · ~1 min   0.0%", left="goal 20w")


def test_minutes_goal_without_tempo_shows_remaining_minutes():
    assert lines(goal_state("goal 6m"))[-1] == status("▸ 6 min   0.0%", left="goal 6m")


def test_minutes_goal_with_tempo_estimates_words_to_the_nearest_ten():
    # 360 s at 2 words per second = 720 words.
    state = goal_state("goal 6m", log=fast_log())

    assert lines(state)[-1] == status("▸ 6 min · ~720 w   0.0%", left="goal 6m")


def test_goal_segment_updates_while_reading():
    state = handle_key(goal_state("goal 20w"), "j")  # 2 words read

    assert lines(state)[-1] == status("▸ 18 w   9.1%")


# --- R3/R4 re-entry frames (§17.7) ----------------------------------------------------


def reopened_at(position, gap, settings=DARK, size=(44, 12)):
    from kert.reader.tempo import LogRow

    log = (LogRow(1000.0, 2, 1, "step", "chunk"),)
    from kert.reader.state import start_session

    return start_session(
        initial_state(
            mini_book(), settings, position, size=size, now=1000.0 + gap, log=log
        )
    )


def test_recall_prompt_clears_the_pane():
    # 60 columns: the 56-wide text column fits the prompt beside the percent.
    frame = lines(reopened_at(Position(4, 0), 3600.0, size=(60, 12)))

    assert frame[:-1] == [""] * 11
    assert frame[-1] == status(
        "59.1%", left="recall: what was happening? — any key", width=56
    )


def test_rating_prompt():
    state = handle_key(reopened_at(Position(4, 0), 3600.0, size=(60, 12)), "x")

    assert lines(state)[-1] == status(
        "59.1%", left="y recalled / p partial / n blank / Esc skip", width=56
    )


def test_recap_frame_ends_just_above_the_center_row():
    # recap_words=10 before S4: chunks 1-3, all of block 2 (two lines). H = 11,
    # the center row is (11 - 1) // 2 = 5, so the recap fills rows 3-4.
    settings = Settings(chunk_width=5, theme="dark", recap_words=10)
    state = reopened_at(Position(4, 0), 60.0, settings)

    frame = lines(state)
    assert frame[:-1] == ["", "", "", "  " + B2[0], "  " + B2[1]] + [""] * 6
    assert frame[-1] == status("59.1%", left="recap — any key")
    assert style_of(state, "Short one.") == ("grey50", False)


def test_recap_across_blocks_separates_them_with_a_blank_line():
    settings = Settings(chunk_width=5, theme="dark", recap_words=12)
    state = reopened_at(Position(4, 0), 60.0, settings)

    assert lines(state)[:5] == ["", "  " + B1, "", "  " + B2[0], "  " + B2[1]]


def test_dismissing_the_recap_shows_the_reading_frame():
    state = reopened_at(Position(4, 0), 60.0)

    assert lines(handle_key(state, "x")) == lines(state_at(Position(4, 0), (44, 12)))


# --- R6 recall line (§17.8) -----------------------------------------------------------


def test_recall_line_frame_shows_the_prompt_and_the_typed_text():
    state = state_at(Position(1, 0), (60, 12))
    for k in [":", *"goal 2w", key.ENTER, "j", *"дождь"]:
        state = handle_key(state, k)

    frame = lines(state)
    prompt = "recall (one line, Enter to submit, Esc to skip):"
    assert frame[:-1] == [""] * 5 + ["  " + prompt] + [""] * 5


def test_goal_reached_message_stays_visible_above_the_recall_prompt():
    state = state_at(Position(1, 0), (60, 12))
    for k in [":", *"goal 2w", key.ENTER, "j"]:
        state = handle_key(state, k)

    frame = lines(state)
    assert frame[4] == "  goal reached — :goal again"
    assert frame[5] == "  recall (one line, Enter to submit, Esc to skip):"
    assert frame[-1] == status("9.1%", left="> дождь", width=56)
