"""Shared test helpers for rawi."""

from __future__ import annotations

import cv2
import numpy as np
import pytest


def _comic_page(w: int = 1200, h: int = 1600) -> np.ndarray:
    """Synthetic BGR page: white background, 2x2 framed panels with some drawing."""
    img = np.full((h, w, 3), 255, np.uint8)
    margin, gutter = 40, 40
    pw, ph = (w - 2 * margin - gutter) // 2, (h - 2 * margin - gutter) // 2
    rng = np.random.default_rng(0)
    for row in range(2):
        for col in range(2):
            x, y = margin + col * (pw + gutter), margin + row * (ph + gutter)
            cv2.rectangle(img, (x, y), (x + pw, y + ph), (0, 0, 0), 6)
            for _ in range(12):
                c = tuple(int(v) for v in rng.integers(0, 200, 3))
                p = (
                    int(x + rng.integers(20, pw - 20)),
                    int(y + rng.integers(20, ph - 20)),
                )
                cv2.circle(img, p, int(rng.integers(10, 60)), c, -1)
    return img


@pytest.fixture
def comic_page():
    """Function drawing a synthetic 2x2-panel page: comic_page(w, h) -> BGR uint8."""
    return _comic_page
