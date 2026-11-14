"""Tests for the v0.2 panel detection (rawi.panels) on synthetic pages (run in CI)."""

from __future__ import annotations

import cv2
import numpy as np
import pytest
from rawi import panels
from rawi.analyze import analyze
from rawi.evaluate import iou

W, H = 1200, 1600
PAPER_WHITE = (255, 255, 255)
PAPER_CREAM = (196, 228, 244)  # BGR of yellowed paper


def scribble(img, poly, seed):
    """Fill a panel polygon with colour and shapes, outlined in black."""
    rng = np.random.default_rng(seed)
    pts = np.array(poly, np.int32)
    cv2.fillPoly(img, [pts], tuple(int(v) for v in rng.integers(60, 200, 3)))
    x, y, w, h = cv2.boundingRect(pts)
    mask = np.zeros(img.shape[:2], np.uint8)
    cv2.fillPoly(mask, [pts], 1)
    layer = img.copy()
    for _ in range(25):
        c = (int(x + rng.integers(0, w)), int(y + rng.integers(0, h)))
        cv2.circle(
            layer,
            c,
            int(rng.integers(15, 70)),
            tuple(int(v) for v in rng.integers(0, 255, 3)),
            -1,
        )
    img[mask == 1] = layer[mask == 1]
    cv2.polylines(img, [pts], True, (0, 0, 0), 5)


def page(paper=PAPER_WHITE, balloon=False):
    """Two rows: a wide top panel, then two panels split by a slanted gutter."""
    img = np.full((H, W, 3), paper, np.uint8)
    top = [(40, 40), (W - 40, 40), (W - 40, 700), (40, 700)]
    left = [(40, 740), (660, 740), (560, H - 40), (40, H - 40)]  # slanted right edge
    right = [(700, 740), (W - 40, 740), (W - 40, H - 40), (600, H - 40)]
    for k, poly in enumerate((top, left, right)):
        scribble(img, poly, k)
    if balloon:  # a speech balloon sitting across the slanted gutter
        cv2.ellipse(img, (630, 1000), (170, 90), 0, 0, 360, (255, 255, 255), -1)
        cv2.ellipse(img, (630, 1000), (170, 90), 0, 0, 360, (0, 0, 0), 4)
        cv2.putText(
            img, "BLA BLA", (520, 1010), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 0), 3
        )
    truth = [cv2.boundingRect(np.array(p, np.int32)) for p in (top, left, right)]
    return img, [list(t) for t in truth]


def found_boxes(img, tmp_path, detection="nouvelle"):
    path = tmp_path / "page.png"
    cv2.imwrite(str(path), img)
    return [
        [p["x"], p["y"], p["w"], p["h"]]
        for p in analyze(str(path), detection=detection)["panels"]
    ]


def assert_matches(found, truth):
    assert len(found) == len(truth), f"{len(found)} cases trouvées : {found}"
    for f, t in zip(found, truth, strict=True):
        assert iou(f, t) > 0.8, (f, t)


@pytest.mark.parametrize("paper", [PAPER_WHITE, PAPER_CREAM], ids=["white", "cream"])
def test_slanted_gutter(tmp_path, paper):
    img, truth = page(paper)
    assert_matches(found_boxes(img, tmp_path), truth)


def test_balloon_over_slanted_gutter(tmp_path):
    img, truth = page(balloon=True)
    assert_matches(found_boxes(img, tmp_path), truth)


def test_v01_still_available(tmp_path):
    img, _ = page()
    assert found_boxes(img, tmp_path, detection="v01")  # runs and finds something


def test_unknown_detection(tmp_path):
    img, _ = page()
    cv2.imwrite(str(tmp_path / "p.png"), img)
    with pytest.raises(ValueError):
        analyze(str(tmp_path / "p.png"), detection="magic")


def test_thin_gives_one_pixel_lines():
    mask = np.zeros((60, 200), np.uint8)
    mask[25:36, 10:190] = 1  # an 11 px thick bar
    skel = panels.thin(mask)
    assert skel[:, 50:150].sum(axis=0).max() == 1  # one pixel per column in the middle
    assert 150 <= skel.sum() <= 185


def test_dead_ends_found_on_straight_branches_only():
    skel = np.zeros((200, 200), np.uint8)
    skel[100, 20:180] = 1  # a straight branch: two dead ends
    skel[30:34, 50] = 1  # a short spur: ignored
    ends = panels.dead_ends(skel, min_len=40)
    assert sorted((x, y) for x, y, _, _ in ends) == [(20, 100), (179, 100)]
    for x, _, ux, uy in ends:
        assert abs(uy) < 1e-6 and (ux < 0 if x == 20 else ux > 0)  # pointing outwards


def test_paper_mask_follows_paper_colour():
    for paper in (PAPER_WHITE, PAPER_CREAM):
        img, _ = page(paper)
        lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB).astype(np.int16)
        mask = panels.paper_mask(lab)
        assert mask[10, 10] == 1 and mask[720, 300] == 1  # margin and gutter are paper
        assert mask[:700, 40:-40][40:-40].mean() < 0.2  # the top panel is not
