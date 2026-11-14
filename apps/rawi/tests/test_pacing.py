"""Tests for reading time (rawi.pacing)."""

from __future__ import annotations

import pytest
from rawi import pacing


def test_read_time_from_text_or_ink():
    assert pacing.bubble_read_time({"text": "x" * 28}) == pytest.approx(2.0)
    assert (
        pacing.bubble_read_time({"text": "ok"}) == pacing.READ_MIN
    )  # short text: minimum
    assert pacing.bubble_read_time({"text": "", "text_px": 7800}) == pytest.approx(3.0)
    assert pacing.bubble_read_time({}) == pacing.READ_MIN


def test_panel_duration_sums_the_balloons_within_bounds():
    two = [{"text": "x" * 28}, {"text": "y" * 42}]
    assert pacing.panel_duration(two) == pytest.approx(
        pacing.FIRST_BUBBLE + 2.0 + 3.0 + pacing.READ_TAIL
    )
    assert pacing.panel_duration([]) == pacing.PANEL_MIN
    assert pacing.panel_duration([{"text": "z" * 1000}]) == pacing.PANEL_MAX


def test_each_balloon_waits_for_the_previous_one():
    bubbles = [{"text": "x" * 28}, {"text": "y" * 14}, {"text": "z"}]
    hold = pacing.panel_duration(bubbles)
    starts = pacing.bubble_starts(bubbles, hold)
    assert starts == pytest.approx([0.25, 2.25, 3.45])
    assert starts[-1] < hold


def test_short_hold_compresses_gaps():
    bubbles = [{"text": "x" * 70}] * 4  # 5 s each
    starts = pacing.bubble_starts(bubbles, 4.0)
    assert len(starts) == 4 and starts == sorted(starts)
    assert all(
        b - a >= pacing.GAP_MIN - 1e-9 for a, b in zip(starts, starts[1:], strict=False)
    )
    assert pacing.bubble_starts([], 3.0) == []
