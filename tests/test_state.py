import pytest
from helpers import make_sentence, mini_book
from readchar import key

from kert.common.model import Block
from kert.reader.config import Settings
from kert.reader.state import (
    Advance,
    Book,
    Checkpoint,
    SaveSetting,
    handle_key,
    initial_state,
    recap_start,
    start_session,
)
from kert.reader.store import Position
from kert.reader.tempo import LogRow

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


# --- Block and book jumps (logged per §17.4) -----------------------------------------

# mini_book at W=5: (sentence_id, words) of each chunk, see helpers.mini_book.
CHUNKS = [(1, 2), (2, 5), (2, 4), (3, 2), (4, 5), (4, 4)]


def left(index, direction, kind):
    """The advance_log effect for leaving chunk `index`."""
    sentence_id, words = CHUNKS[index]
    return Advance(sentence_id, words, direction, kind)


@pytest.mark.parametrize(("start", "index"), [(1, 4), (2, 4), (3, 4), (0, 1)])
def test_next_block_goes_to_its_first_chunk(start, index):
    state = press(at(start), "J")

    assert state.index == index
    assert state.effects == (left(start, 1, "block"),)


def test_next_block_in_last_block_is_a_no_op():
    state = press(at(4), "J")

    assert state.index == 4
    assert state.effects == ()


@pytest.mark.parametrize(("start", "index"), [(5, 1), (4, 1), (2, 0), (3, 0)])
def test_previous_block_goes_to_its_first_chunk(start, index):
    state = press(at(start), "K")

    assert state.index == index
    assert state.effects == (left(start, -1, "block"),)


def test_previous_block_in_first_block_is_a_no_op():
    state = press(at(0), "K")

    assert state.index == 0
    assert state.effects == ()


def test_gg_goes_to_first_chunk():
    state = press(at(5), "g", "g")

    assert state.index == 0
    assert state.effects == (left(5, -1, "jump"),)


def test_jump_to_the_active_chunk_is_not_logged():
    assert press(at(0), "g", "g").effects == ()
    assert press(at(5), "G").effects == ()


def test_single_g_waits_for_second_key():
    assert press(at(5), "g").index == 5


def test_g_followed_by_other_key_runs_that_key():
    assert press(at(1), "g", "j").index == 2


def test_capital_g_goes_to_last_chunk():
    state = press(at(0), "G")

    assert state.index == 5
    assert state.effects == (left(0, 1, "jump"),)


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
    assert state.effects == (left(2, 1 if index > 2 else -1, "jump"),)


def test_colon_q_quits():
    assert type_command(at(2), "q").quit is True


# --- Headings and code are single stops (§14.3, §14.7) --------------------------------


def test_heading_and_code_are_one_stop_each_at_any_width():
    from kert.common.model import Sentence
    from kert.common.text import whitespace_tokens

    long_heading = " ".join(["слово"] * 20)
    code = "\n".join(f"line_{i} = {i}" for i in range(15))
    book = Book(
        blocks=(Block(1, "heading", chapter=1), Block(2, "code", chapter=1)),
        sentences=(
            Sentence(1, 1, 0, long_heading, whitespace_tokens(long_heading), ()),
            Sentence(2, 2, 0, code, whitespace_tokens(code), ()),
        ),
        word_count=35,
    )
    state = initial_state(book, W5, Position(1, 0))

    assert [(s.sentence_id, s.start_token) for s in state.chunks.spans] == [
        (1, 0),
        (2, 0),
    ]
    assert press(state, "j").index == 1
    assert press(state, "J").index == 1


# --- R1 cheap regressions (§17.3) -----------------------------------------------------


@pytest.mark.parametrize(
    ("start", "index"),
    [
        (2, 1),  # mid-sentence: back to the unit starting the sentence
        (1, 0),  # at a sentence start: the previous sentence's start
        (3, 1),
        (4, 3),  # crosses the block boundary
    ],
)
def test_open_paren_goes_back_by_sentence(start, index):
    state = press(at(start), "(")

    assert state.index == index
    assert state.effects == (left(start, -1, "sentence"),)


def test_open_paren_at_book_start_is_a_no_op():
    state = press(at(0), "(")

    assert state.index == 0
    assert state.effects == ()


@pytest.mark.parametrize(("start", "index"), [(0, 1), (1, 3), (2, 3), (3, 4)])
def test_close_paren_goes_to_the_next_sentence(start, index):
    state = press(at(start), ")")

    assert state.index == index
    assert state.effects == (left(start, 1, "sentence"),)


@pytest.mark.parametrize("start", [4, 5])
def test_close_paren_in_the_last_sentence_is_a_no_op(start):
    state = press(at(start), ")")

    assert state.index == start
    assert state.effects == ()


def test_peek_shows_the_previous_unit_without_moving():
    state = press(at(2), "p")

    assert state.peek is True
    assert state.index == 2
    assert state.position == at(2).position
    assert state.effects == (Advance(2, 5, 0, "peek"),)


@pytest.mark.parametrize("k", ["j", "b", "J", ":", "q", "p", "x"])
def test_any_key_leaves_peek_and_is_consumed(k):
    state = press(at(2), "p", k)

    assert state.peek is False
    assert state.index == 2
    assert state.command is None
    assert state.quit is False
    assert state.effects == ()


def test_peek_at_the_first_unit_is_a_no_op():
    state = press(at(0), "p")

    assert state.peek is False
    assert state.effects == ()


def test_peek_is_not_entered_from_the_command_line():
    state = press(at(2), ":", "p")

    assert state.peek is False
    assert state.command == "p"


# --- Reading modes (§17.2) ------------------------------------------------------------

SENTENCE = Settings(chunk_width=5, theme="dark", mode="sentence")
PARAGRAPH = Settings(chunk_width=5, theme="dark", mode="paragraph")


def in_mode(settings, position):
    return initial_state(mini_book(), settings, position)


def test_mode_defaults_to_chunk():
    assert W5.mode == "chunk"


def test_sentence_mode_units_are_whole_sentences():
    # mini_book: S1 (2 words) | S2 (9) S3 (2) | S4 (9)
    state = in_mode(SENTENCE, Position(2, 0))

    assert state.index == 1
    assert state.percent == pytest.approx(2 / 22 * 100)
    state = press(state, "j")
    assert state.position == Position(3, 0)
    assert state.effects == (Advance(2, 9, 1, "step"),)
    assert state.percent == pytest.approx(11 / 22 * 100)


def test_paragraph_mode_units_are_whole_blocks():
    state = in_mode(PARAGRAPH, Position(2, 0))

    state = press(state, "j")
    assert state.position == Position(4, 0)
    assert state.effects == (Advance(2, 11, 1, "step"),)  # block 2 = S2 + S3
    assert state.percent == pytest.approx(13 / 22 * 100)
    assert press(state, "j").effects == ()  # last unit


@pytest.mark.parametrize(
    ("position", "resolved"),
    [(Position(3, 0), Position(2, 0)), (Position(2, 7), Position(2, 0))],
)
def test_paragraph_mode_resolves_inside_a_block_to_its_start(position, resolved):
    assert in_mode(PARAGRAPH, position).position == resolved


def test_sentence_mode_resolves_mid_sentence_to_its_start():
    assert in_mode(SENTENCE, Position(2, 5)).position == Position(2, 0)


def test_paragraph_mode_regressions_move_by_block():
    state = in_mode(PARAGRAPH, Position(4, 0))

    assert press(state, "(").position == Position(2, 0)
    assert press(state, "(").effects == (Advance(4, 9, -1, "sentence"),)
    assert press(in_mode(PARAGRAPH, Position(1, 0)), ")").position == Position(2, 0)


def test_paragraph_mode_peek_is_the_previous_block():
    state = press(in_mode(PARAGRAPH, Position(4, 0)), "p")

    assert state.peek is True
    assert state.effects == (Advance(2, 11, 0, "peek"),)


def test_paragraph_mode_goto_is_word_based():
    # unit starts at 0, 2, 13 words: 50% = 11 is nearest to 13.
    state = type_command(in_mode(PARAGRAPH, Position(1, 0)), "goto 50")

    assert state.position == Position(4, 0)


@pytest.mark.parametrize(
    ("start", "mode", "position"),
    [
        (2, "sentence", Position(2, 0)),  # S2 tok 5 -> sentence S2
        (3, "paragraph", Position(2, 0)),  # S3 -> block 2
        (5, "paragraph", Position(4, 0)),
    ],
)
def test_set_mode_reassembles_and_keeps_the_place(start, mode, position):
    state = type_command(at(start), f"set mode={mode}")

    assert state.settings.mode == mode
    assert state.position == position
    assert state.message == f"mode={mode}"
    assert state.effects == (SaveSetting("mode", mode),)


def test_set_mode_back_to_chunk_returns_to_the_chunk_of_the_unit_start():
    state = type_command(at(2), "set mode=sentence")

    assert type_command(state, "set mode=chunk").index == 1


def test_set_unknown_mode_is_an_error():
    state = type_command(at(2), "set mode=plain")

    assert state.settings.mode == "chunk"
    assert state.message.startswith("mode must be one of")


def test_width_is_stored_in_other_modes_and_used_back_in_chunk_mode():
    state = type_command(in_mode(SENTENCE, Position(2, 0)), "set width=8")

    assert state.settings.chunk_width == 8
    assert state.position == Position(2, 0)
    assert type_command(state, "set mode=chunk").chunks.spans == at(1, W8).chunks.spans


# --- R5 session goal (§17.6) ----------------------------------------------------------
# mini_book at W=5: words before each chunk 0, 2, 7, 11, 13, 18.

REACHED = "goal reached — :goal again"


def press_at(state, now, *keys):
    from dataclasses import replace

    return press(replace(state, now=now), *keys)


def test_goal_in_words_is_reached_by_reading_from_the_arming_place():
    state = type_command(at(0), "goal 5w")
    assert state.message == "goal 5w"
    assert state.goal is not None

    state = press(state, "j")  # 2 words read
    assert state.message is None
    state = press(state, "j")  # 7 words read
    assert state.message == REACHED
    assert state.goal is None


def test_goal_again_rearms_from_the_current_place():
    state = press(type_command(at(0), "goal 5w"), "j", "j")
    state = type_command(state, "goal again")
    assert state.message == "goal 5w"

    assert press(state, "j").message is None  # 11 - 7 = 4
    assert press(state, "j", "j").message == REACHED  # 13 - 7 = 6


def test_goal_again_without_a_previous_goal():
    state = type_command(at(0), "goal again")

    assert state.goal is None
    assert state.message == "no goal to re-arm"


def test_goal_off_clears_the_goal():
    state = type_command(type_command(at(0), "goal 5w"), "goal off")

    assert state.goal is None
    assert state.message == "goal off"
    assert press(state, "j", "j").message is None


@pytest.mark.parametrize(
    "text", ["goal", "goal 0w", "goal 5x", "goal 601m", "goal 100001w", "goal 1.5m"]
)
def test_bad_goal_is_a_usage_error(text):
    state = type_command(at(0), text)

    assert state.goal is None
    assert state.message.startswith("Usage: :goal")


def test_moves_are_kept_as_log_rows_with_the_clock():
    state = press_at(at(0), 5.0, "j")

    assert state.log[-1] == LogRow(5.0, 2, 1, "step", "chunk")


def test_goal_in_minutes_counts_active_reading_time():
    state = type_command(press_at(at(0), 100.0), "goal 1m")
    state = press_at(state, 100.0, "j")  # first row: no dwell yet
    state = press_at(state, 130.0, "j")  # 30 s
    assert state.message is None
    state = press_at(state, 161.0, "j")  # 61 s
    assert state.message == REACHED


def test_idle_time_does_not_count_toward_a_minutes_goal():
    state = type_command(press_at(at(0), 100.0), "goal 1m")
    state = press_at(state, 100.0, "j")
    state = press_at(state, 200.0, "j")  # 100 s: idle, discarded

    assert state.message is None
    assert state.goal is not None


def test_default_goal_is_armed_at_start():
    settings = Settings(chunk_width=5, theme="dark", default_goal="5w")
    state = initial_state(mini_book(), settings, Position(1, 0), now=50.0)

    assert state.goal is not None
    assert press(state, "j", "j").message == REACHED


# --- R3/R4 re-entry: recall prompt, rating, recap (§17.7) ---------------------------

HOUR = 3600.0


def reopened(index, gap, settings=W5, log_rows=1):
    """State on chunk `index` opened `gap` seconds after the last logged move."""
    book = mini_book()
    starts = [(1, 0), (2, 0), (2, 5), (3, 0), (4, 0), (4, 5)]
    log = tuple(LogRow(1000.0 - i, 2, 1, "step", "chunk") for i in range(log_rows))
    return start_session(
        initial_state(
            book, settings, Position(*starts[index]), now=1000.0 + gap, log=log
        )
    )


def open_checkpoint(rating, sentence_id=4):
    return Checkpoint(
        trigger="open",
        mode="chunk",
        span_start_sentence=sentence_id,
        span_end_sentence=sentence_id,
        span_words=0,
        recall_text=None,
        self_rating=rating,
    )


def test_long_gap_starts_with_the_recall_prompt():
    assert reopened(4, HOUR).overlay == "recall"


def test_recall_then_rating_then_recap():
    state = press(reopened(4, HOUR), "x")
    assert state.overlay == "rating"

    state = press(state, "y")
    assert state.effects == (open_checkpoint(2),)
    assert state.overlay == "recap"

    state = press(state, "j")
    assert state.overlay is None
    assert state.index == 4  # the key that dismisses the recap is consumed
    assert state.effects == ()


@pytest.mark.parametrize(("k", "rating"), [("p", 1), ("n", 0), (key.ESC, None)])
def test_rating_keys(k, rating):
    assert press(reopened(4, HOUR), "x", k).effects == (open_checkpoint(rating),)


def test_other_keys_keep_the_rating_prompt():
    state = press(reopened(4, HOUR), "x", "j", "q")

    assert state.overlay == "rating"
    assert state.index == 4
    assert state.quit is False
    assert state.effects == ()


def test_short_gap_goes_straight_to_the_recap():
    assert reopened(4, HOUR - 1).overlay == "recap"


def test_empty_log_has_no_gap_and_no_recall_prompt():
    assert reopened(4, HOUR, log_rows=0).overlay == "recap"


def test_book_start_has_no_recall_and_no_recap():
    assert reopened(0, HOUR).overlay is None


def test_recap_off_after_a_short_gap_reads_directly():
    settings = Settings(chunk_width=5, theme="dark", recap=False)

    assert reopened(4, 60.0, settings).overlay is None


def test_recall_off_skips_the_prompt():
    settings = Settings(chunk_width=5, theme="dark", recall=False)

    assert reopened(4, HOUR, settings).overlay == "recap"


def test_recall_without_recap_ends_in_reading():
    settings = Settings(chunk_width=5, theme="dark", recap=False)

    assert press(reopened(4, HOUR, settings), "x", "y").overlay is None


def test_recall_gap_is_a_setting():
    settings = Settings(chunk_width=5, theme="dark", recall_gap_minutes=5)

    assert reopened(4, 301.0, settings).overlay == "recall"
    assert reopened(4, 299.0, settings).overlay == "recap"


@pytest.mark.parametrize(
    ("index", "words", "start"),
    [
        (4, 10, 1),  # back 2 + 4 + 5 = 11 >= 10 words, across the block boundary
        (4, 1, 3),  # at least one whole unit
        (2, 40, 0),  # the book start bounds it
    ],
)
def test_recap_takes_whole_units_back_to_the_word_budget(index, words, start):
    settings = Settings(chunk_width=5, theme="dark", recap_words=words)

    assert recap_start(reopened(index, 0.0, settings)) == start


def test_no_recap_at_the_book_start():
    assert recap_start(reopened(0, 0.0)) is None
