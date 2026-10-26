import pytest
from helpers import make_sentence, mini_book
from readchar import key

from kert.common.model import Block
from kert.reader.config import Settings
from kert.reader.state import (
    Advance,
    Book,
    SaveSetting,
    handle_key,
    initial_state,
)
from kert.reader.store import Position

W5 = Settings(chunk_width=5, theme="dark")
W8 = Settings(chunk_width=8, theme="dark")


def at(index, settings=W5):
    """State on chunk `index` of mini_book (see helpers.mini_book)."""
    book = mini_book()
    starts = [(1, 0), (2, 0), (2, 5), (3, 0), (4, 0), (4, 5)]
    if settings.chunk_width == 8:
        starts = [(1, 0), (2, 0), (3, 0), (4, 0)]
    state = initial_state(book, settings, Position(*starts[index]))
    assert state.index == index
    return state


def press(state, *keys):
    for k in keys:
        state = handle_key(state, k)
    return state


# --- Position resolution (§5 step 4) --------------------------------------------------


@pytest.mark.parametrize(
    ("position", "index"),
    [
        (Position(1, 0), 0),
        (Position(2, 5), 2),
        (Position(2, 3), 1),  # chunk containing the token
        (Position(2, 7), 2),
        (Position(4, 99), 4),  # no chunk contains it: first chunk of the sentence
        (Position(99, 0), 0),  # unknown sentence: first chunk of the book
    ],
)
def test_initial_position_resolves_to_nearest_chunk(position, index):
    assert initial_state(mini_book(), W5, position).index == index


def test_position_reports_active_chunk_start():
    assert at(2).position == Position(sentence_id=2, chunk_start_token=5)


def test_initial_state_is_clean():
    state = at(0)

    assert state.command is None
    assert state.message is None
    assert state.effects == ()
    assert state.quit is False


# --- Percent (§7.1, word-based) -------------------------------------------------------


@pytest.mark.parametrize(
    ("index", "percent"),
    [(0, 0.0), (1, 2 / 22 * 100), (2, 7 / 22 * 100), (5, 18 / 22 * 100)],
)
def test_percent_is_words_before_active_chunk_over_word_count(index, percent):
    assert at(index).percent == pytest.approx(percent)


def test_percent_is_stable_across_widths():
    assert at(1, W5).percent == at(1, W8).percent  # both start S2 token 0


def test_percent_counts_only_words():
    book = Book(
        blocks=(Block(1, "dialogue"),),
        sentences=(
            make_sentence(1, 1, 0, "— Да , 10 раз."),
            make_sentence(2, 1, 1, "Ок."),
        ),
        word_count=4,
    )
    state = initial_state(book, W8, Position(2, 0))

    # "—", ",", "." are not words; "Да", "10", "раз" are.
    assert state.percent == pytest.approx(3 / 4 * 100)


def test_percent_is_clamped_to_100_when_meta_word_count_is_lower():
    book = mini_book()
    book = Book(blocks=book.blocks, sentences=book.sentences, word_count=10)

    assert initial_state(book, W5, Position(4, 5)).percent == 100.0


def test_percent_with_zero_word_count_is_zero():
    book = mini_book()
    book = Book(blocks=book.blocks, sentences=book.sentences, word_count=0)

    assert initial_state(book, W5, Position(4, 5)).percent == 0.0


# --- Chunk navigation + advance_log effects (§8.1, D5) --------------------------------


@pytest.mark.parametrize("k", [" ", "j", key.RIGHT])
def test_next_chunk_logs_the_chunk_left(k):
    state = press(at(1), k)

    assert state.index == 2
    assert state.effects == (Advance(sentence_id=2, chunk_words=5, direction=1),)


@pytest.mark.parametrize("k", ["b", "k", key.LEFT])
def test_previous_chunk_logs_the_chunk_left(k):
    state = press(at(2), k)

    assert state.index == 1
    assert state.effects == (Advance(sentence_id=2, chunk_words=4, direction=-1),)


def test_next_crosses_sentence_and_block_boundaries():
    assert press(at(3), "j").index == 4


def test_next_at_last_chunk_is_a_no_op():
    state = press(at(5), "j")

    assert state.index == 5
    assert state.effects == ()


def test_previous_at_first_chunk_is_a_no_op():
    state = press(at(0), "k")

    assert state.index == 0
    assert state.effects == ()


def test_effects_are_per_key():
    assert press(at(1), "j", "x").effects == ()


# --- Block and book jumps (no advance_log, SPEC_NOTES Task 8a) ------------------------


@pytest.mark.parametrize(("start", "index"), [(1, 4), (2, 4), (3, 4), (0, 1)])
def test_next_block_goes_to_its_first_chunk(start, index):
    state = press(at(start), "J")

    assert state.index == index
    assert state.effects == ()


def test_next_block_in_last_block_is_a_no_op():
    assert press(at(4), "J").index == 4


@pytest.mark.parametrize(("start", "index"), [(5, 1), (4, 1), (2, 0), (3, 0)])
def test_previous_block_goes_to_its_first_chunk(start, index):
    state = press(at(start), "K")

    assert state.index == index
    assert state.effects == ()


def test_previous_block_in_first_block_is_a_no_op():
    assert press(at(0), "K").index == 0


def test_gg_goes_to_first_chunk():
    state = press(at(5), "g", "g")

    assert state.index == 0
    assert state.effects == ()


def test_single_g_waits_for_second_key():
    assert press(at(5), "g").index == 5


def test_g_followed_by_other_key_runs_that_key():
    assert press(at(1), "g", "j").index == 2


def test_capital_g_goes_to_last_chunk():
    state = press(at(0), "G")

    assert state.index == 5
    assert state.effects == ()


def test_unknown_key_is_a_no_op():
    state = press(at(2), "z")

    assert (state.index, state.message, state.quit) == (2, None, False)


def test_q_quits():
    assert press(at(2), "q").quit is True


# --- Command line (§8.2) --------------------------------------------------------------


def test_colon_opens_empty_command_line():
    assert press(at(0), ":").command == ""


def test_typing_in_command_line_does_not_navigate():
    state = press(at(0), ":", "j", "q")

    assert state.command == "jq"
    assert state.index == 0
    assert state.quit is False


def test_backspace_edits_command_line():
    assert press(at(0), ":", "a", "b", key.BACKSPACE).command == "a"


def test_backspace_on_empty_command_line_closes_it():
    assert press(at(0), ":", key.BACKSPACE).command is None


def test_escape_cancels_command_line():
    state = press(at(0), ":", "q", key.ESC)

    assert state.command is None
    assert state.quit is False


@pytest.mark.parametrize("enter", [key.ENTER, key.CR, key.LF])
def test_enter_runs_command_and_closes_line(enter):
    state = press(at(0), ":", "q", enter)

    assert state.quit is True
    assert state.command is None


def type_command(state, text):
    return press(state, ":", *text, key.ENTER)


def test_unknown_command_shows_error_and_keeps_state():
    state = type_command(at(2), "foo")

    assert state.command is None
    assert state.message.startswith("Unknown command")
    assert (state.index, state.quit, state.effects) == (2, False, ())


def test_invalid_command_value_shows_error():
    state = type_command(at(2), "set width=99")

    assert state.message is not None
    assert state.settings == W5
    assert state.effects == ()


def test_empty_command_closes_silently():
    state = type_command(at(2), "")

    assert (state.command, state.message, state.effects) == (None, None, ())


def test_message_is_cleared_by_next_key():
    assert press(type_command(at(2), "foo"), "j").message is None


# --- :set width (§5 re-chunk, position re-resolution) ---------------------------------


def test_set_width_rechunks_and_keeps_active_token():
    # W=5 chunk 2 starts at S2 token 5; at W=8 S2 is one chunk (index 1).
    state = type_command(at(2), "set width=8")

    assert state.settings == W8
    assert state.index == 1
    assert state.position == Position(2, 0)
    assert state.effects == (SaveSetting("chunk_width", "8"),)
    assert state.message == "width=8"


def test_set_width_back_and_forth():
    state = type_command(type_command(at(5), "set width=8"), "set width=5")

    assert state.index == 4  # S4 token 0 at W=5
    assert state.percent == pytest.approx(13 / 22 * 100)


def test_navigation_uses_new_width():
    state = press(type_command(at(1), "set width=8"), "j")

    assert state.index == 2
    assert state.position == Position(3, 0)
    assert state.effects == (Advance(sentence_id=2, chunk_words=9, direction=1),)


# --- :set theme / :goto / :q ----------------------------------------------------------


def test_set_theme():
    state = type_command(at(2), "set theme=light")

    assert state.settings == Settings(chunk_width=5, theme="light")
    assert state.index == 2
    assert state.effects == (SaveSetting("theme", "light"),)
    assert state.message == "theme=light"


@pytest.mark.parametrize(
    ("percent", "index"),
    [
        ("0", 0),
        ("50", 3),  # 11 words: chunk 3 starts at 11
        ("60", 4),  # 13.2 -> 13 (chunk 4)
        ("70", 4),  # 15.4: |13-15.4| < |18-15.4|
        ("100", 5),  # 22 -> 18 is nearest
    ],
)
def test_goto_jumps_to_chunk_nearest_in_words(percent, index):
    state = type_command(at(2), f"goto {percent}")

    assert state.index == index
    assert state.effects == ()


def test_colon_q_quits():
    assert type_command(at(2), "q").quit is True
