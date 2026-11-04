"""Reading tempo and active time from advance_log rows (spec §17.6)."""

import pytest

from kert.reader.tempo import LogRow, active_seconds, tempo_wps


def steps(dwells, words=4, start=1000.0, mode="chunk"):
    """Forward chunk steps: one row at `start`, then one after each dwell."""
    rows, ts = [LogRow(start, words, 1, "step", mode)], start
    for dwell in dwells:
        ts += dwell
        rows.append(LogRow(ts, words, 1, "step", mode))
    return rows


def test_median_words_per_second():
    # 30 dwells of 2 s for 4-word chunks -> 2 words per second.
    assert tempo_wps(steps([2.0] * 30), "chunk") == pytest.approx(2.0)


def test_median_resists_outliers():
    rows = steps([2.0] * 20 + [0.5] * 5 + [40.0] * 6)

    assert tempo_wps(rows, "chunk") == pytest.approx(2.0)


def test_fewer_than_30_samples_is_none():
    assert tempo_wps(steps([2.0] * 29), "chunk") is None
    assert tempo_wps([], "chunk") is None


def test_idle_and_skip_through_dwells_are_discarded():
    # 30 good dwells plus idle (> 60 s) and skip-through (< 0.15 s) ones.
    rows = steps([2.0] * 15 + [61.0, 0.1] + [2.0] * 15)

    assert tempo_wps(rows, "chunk") == pytest.approx(2.0)
    assert tempo_wps(steps([2.0] * 28 + [61.0, 0.1]), "chunk") is None


def test_only_forward_steps_in_the_current_mode_count():
    rows = steps([2.0] * 30)
    noise = [
        LogRow(1001.0, 50, -1, "step", "chunk"),
        LogRow(1003.0, 50, 1, "block", "chunk"),
        LogRow(1005.0, 50, 0, "peek", "chunk"),
        LogRow(1007.0, 50, 1, "step", "paragraph"),
    ]
    mixed = sorted(rows + noise, key=lambda row: row.ts)

    assert tempo_wps(mixed, "chunk") == pytest.approx(2.0)
    assert tempo_wps(mixed, "paragraph") is None


def test_only_the_last_200_qualifying_rows_count():
    # 100 slow dwells (1 wps) then 199 fast ones (4 wps): the last 200 rows
    # span 199 dwells, all fast.
    rows = steps([4.0] * 100 + [1.0] * 199)

    assert tempo_wps(rows, "chunk") == pytest.approx(4.0)


def test_active_seconds_sum_kept_dwells_after_arming():
    rows = steps([2.0, 2.0, 61.0, 2.0, 0.1, 3.0])  # ts 1000, 1002, 1004, 1065, ...

    assert active_seconds(rows, "chunk", since=1003.0) == pytest.approx(2.0 + 2.0 + 3.0)
    assert active_seconds(rows, "chunk", since=0.0) == pytest.approx(9.0)
    assert active_seconds(rows, "paragraph", since=0.0) == 0.0
