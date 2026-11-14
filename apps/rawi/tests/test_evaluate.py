"""Tests for the detection scoring tool (rawi.evaluate)."""

from __future__ import annotations

import pytest
from rawi.evaluate import iou, load_truth, score_page, totals

TRUTH = [
    {"box": [0, 0, 100, 100]},
    {"box": [100, 0, 100, 100]},
    {"box": [0, 100, 200, 100]},
    {"box": [0, 200, 200, 50], "optional": True},
]


def test_iou():
    assert iou([0, 0, 10, 10], [0, 0, 10, 10]) == 1.0
    assert iou([0, 0, 10, 10], [20, 20, 5, 5]) == 0.0
    assert iou([0, 0, 10, 10], [5, 0, 10, 10]) == pytest.approx(50 / 150)


def test_perfect_page():
    s = score_page("p", [t["box"] for t in TRUTH[:3]], TRUTH)
    assert (s.recall, s.precision, s.order) == (1.0, 1.0, 1.0)


def test_merged_panels_and_extra():
    # first two panels merged into one box, plus one bogus box
    found = [[0, 0, 200, 100], [0, 100, 200, 100], [500, 500, 10, 10]]
    s = score_page("p", found, TRUTH)
    assert s.matched_required == 1 and s.extra == 2
    assert s.recall == pytest.approx(1 / 3) and s.precision == pytest.approx(1 / 3)


def test_optional_panel_is_neutral():
    found = [t["box"] for t in TRUTH]  # also finds the optional one
    s = score_page("p", found, TRUTH)
    assert s.recall == 1.0 and s.precision == 1.0


def test_order():
    found = [TRUTH[1]["box"], TRUTH[0]["box"], TRUTH[2]["box"]]  # first two swapped
    s = score_page("p", found, TRUTH)
    assert s.order == pytest.approx(1 / 2)
    t = totals([s, score_page("q", [b["box"] for b in TRUTH[:3]], TRUTH)])
    assert t["recall"] == 1.0 and t["order"] == pytest.approx(3 / 4)


@pytest.mark.parametrize("name", ["qahwati", "goldorak"])
def test_truth_files_are_valid(name):
    truth = load_truth(name)
    for panels in truth["pages"].values():
        for p in panels:
            x, y, w, h = p["box"]
            assert w > 0 and h > 0 and x >= 0 and y >= 0
