"""Tests for speech balloon detection (rawi.bubbles) on synthetic pages (run in CI)."""

from __future__ import annotations

import cv2
import numpy as np
from rawi import bubbles
from rawi.analyze import _gutter_mask, _white_mask, analyze
from rawi.evaluate import iou


def balloon(img, centre, axes, text=True):
    cv2.ellipse(img, centre, axes, 0, 0, 360, (255, 255, 255), -1)
    cv2.ellipse(img, centre, axes, 0, 0, 360, (0, 0, 0), 4)
    if text:
        x, y = centre
        for k in range(3):
            cv2.putText(
                img,
                "BLA BLA",
                (x - axes[0] + 30, y - 25 + 28 * k),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                (0, 0, 0),
                2,
            )
    return [centre[0] - axes[0], centre[1] - axes[1], 2 * axes[0], 2 * axes[1]]


def base_page(w=1000, h=1400):
    img = np.full((h, w, 3), 255, np.uint8)
    for x0, x1 in (
        (30, 485),
        (515, w - 30),
    ):  # two panels side by side, coloured artwork
        cv2.rectangle(img, (x0, 30), (x1, h - 30), (60, 120, 190), -1)
        cv2.rectangle(img, (x0, 30), (x1, h - 30), (0, 0, 0), 5)
    return img


def detect(img):
    white = _white_mask(img)
    return [
        [b["x"], b["y"], b["w"], b["h"]]
        for b in bubbles.detect(img, white, _gutter_mask(white))
    ]


def best_iou(box, found):
    return max((iou(box, f) for f in found), default=0.0)


def test_balloon_found_and_outlined():
    img = base_page()
    truth = balloon(img, (250, 300), (170, 100))
    found = detect(img)
    assert best_iou(truth, found) > 0.7
    white = _white_mask(img)
    (b,) = [
        b
        for b in bubbles.detect(img, white, _gutter_mask(white))
        if iou([b["x"], b["y"], b["w"], b["h"]], truth) > 0.7
    ]
    assert len(b["polygon"]) > 8  # a real outline, not a box


def test_balloon_across_two_panels_is_not_cut():
    img = base_page()
    truth = balloon(img, (500, 700), (190, 100))  # straddles the vertical gutter
    found = detect(img)
    assert best_iou(truth, found) > 0.7
    assert (
        sum(1 for f in found if iou(f, truth) > 0.1) == 1
    )  # one balloon, not two halves


def test_colourful_white_screen_is_not_a_balloon():
    img = base_page()
    cv2.rectangle(img, (600, 200), (900, 420), (255, 255, 255), -1)  # a white screen…
    for k, colour in enumerate(((60, 200, 60), (200, 120, 40), (40, 40, 220))):
        cv2.rectangle(
            img, (630 + 90 * k, 330 - 40 * k), (690 + 90 * k, 400), colour, -1
        )  # …with a bar chart
    cv2.putText(img, "Churn", (630, 240), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 0), 2)
    assert best_iou([600, 200, 300, 220], detect(img)) < 0.3


def test_balloon_touching_a_white_object_is_found():
    img = base_page()
    truth = balloon(img, (250, 900), (170, 100))  # bottom of the balloon at y = 1000
    cv2.rectangle(
        img, (150, 1030), (420, 1300), (255, 255, 255), -1
    )  # a blank white sheet
    cv2.rectangle(img, (150, 1030), (420, 1300), (0, 0, 0), 3)
    cv2.line(
        img, (250, 985), (250, 1045), (255, 255, 255), 10
    )  # 10 px neck through both outlines
    assert best_iou(truth, detect(img)) > 0.6


def test_assign_to_the_panel_overlapped_most():
    panels = [
        {"x": 0, "y": 0, "w": 500, "h": 500},
        {"x": 500, "y": 0, "w": 500, "h": 500},
    ]
    b1 = {"x": 400, "y": 100, "w": 300, "h": 100}  # mostly in the right panel
    b2 = {"x": 2000, "y": 2000, "w": 10, "h": 10}  # outside every panel: nearest
    bubbles.assign([b1, b2], panels)
    assert panels[1]["bubbles"] == [b1, b2] or (
        b1 in panels[1]["bubbles"] and b2 in panels[1]["bubbles"]
    )
    assert panels[0]["bubbles"] == []


def test_analyze_attaches_balloons_to_panels(tmp_path):
    img = base_page()
    balloon(img, (250, 300), (170, 100))
    cv2.imwrite(str(tmp_path / "p.png"), img)
    page = analyze(str(tmp_path / "p.png"))
    assert sum(len(p["bubbles"]) for p in page["panels"]) == 1
