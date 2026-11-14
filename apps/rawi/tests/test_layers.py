"""Tests for live bubbles: page layers (rawi.layers) and the bubble schedule in the renderer."""

from __future__ import annotations

import numpy as np
import pytest
from rawi import layers
from rawi.render import POP, bubble_schedule, frames


def page_with_bubble(h=400, w=300):
    img = np.zeros((h, w, 3), np.uint8)
    img[:] = (40, 120, 200)  # flat artwork
    img[:, : w // 2] = (200, 60, 40)
    poly = [[100, 100], [200, 100], [200, 160], [100, 160]]
    img[100:160, 100:200] = 255  # white balloon interior
    img[125:135, 120:180] = 0  # "text"
    return img, {"id": "b1", "x": 100, "y": 100, "w": 100, "h": 60, "polygon": poly}


def test_bubble_mask_polygon_and_ellipse():
    _, b = page_with_bubble()
    m = layers.bubble_mask((400, 300), b, grow=0)
    assert (
        m[130, 150] == 1
        and m[50, 50] == 0
        and m.sum() == pytest.approx(101 * 61, rel=0.05)
    )
    ellipse = layers.bubble_mask((400, 300), {**b, "polygon": None}, grow=0)
    assert (
        ellipse[130, 150] == 1 and ellipse[101, 101] == 0
    )  # corner outside the ellipse
    assert layers.bubble_mask((400, 300), b, grow=5).sum() > m.sum()


def test_erased_page_has_no_bubble_left():
    img, b = page_with_bubble()
    pl = layers.build_layers(img, [b])
    inside = pl.base[110:150, 110:190]
    assert inside.min() > 30  # the black text is gone
    assert np.abs(inside.astype(int) - 255).mean() > 60  # and so is the white balloon
    assert np.array_equal(pl.base[300:, :], img[300:, :])  # far away: untouched


def test_pasting_back_restores_the_bubble():
    img, b = page_with_bubble()
    pl = layers.build_layers(img, [b])
    back = pl.with_bubbles({"b1"})
    assert np.abs(back[110:150, 110:190].astype(int) - img[110:150, 110:190]).max() <= 2
    assert np.array_equal(pl.with_bubbles(set()), pl.base)


def test_soft_fill_without_known_pixels_does_not_crash():
    img = np.full((50, 50, 3), 100, np.uint8)
    out = layers.soft_fill(img, np.ones((50, 50), np.uint8))
    assert out.shape == img.shape


@pytest.mark.parametrize(("n", "hold"), [(0, 3.0), (1, 2.2), (3, 7.5), (6, 3.0)])
def test_bubble_schedule_fits_the_hold(n, hold):
    starts = bubble_schedule(n, hold)
    assert len(starts) == n
    assert starts == sorted(starts)
    if n:
        assert starts[0] > 0 and starts[-1] + POP <= max(
            hold, starts[0] + (n - 1) * 0.3 + POP
        )


def test_bubbles_hidden_then_shown(tmp_path):
    import cv2

    img, _ = page_with_bubble()  # 400x300, balloon at x 100-200, y 100-160
    b = {
        "id": "b1",
        "x": 200,
        "y": 200,
        "w": 200,
        "h": 120,
        "polygon": [[200, 200], [400, 200], [400, 320], [200, 320]],
        "order": 1,
    }
    img = cv2.resize(img, (600, 800), interpolation=cv2.INTER_NEAREST)
    path = tmp_path / "p.png"
    cv2.imwrite(str(path), img)
    page = {
        "image": str(path),
        "width": 600,
        "height": 800,
        "rtl": False,
        "panels": [
            {
                "id": 1,
                "x": 0,
                "y": 0,
                "w": 600,
                "h": 800,
                "duration": 3.0,
                "bubbles": [b],
            }
        ],
    }
    out = list(frames(page, fmt="1:1", fps=10, scale=0.3))
    first, last = out[0], out[-1]
    # overview frame: the white balloon is not there; final overview: it is back
    assert (first > 245).all(axis=2).mean() < (last > 245).all(axis=2).mean()
