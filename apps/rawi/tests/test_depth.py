"""Tests for depth maps and parallax (rawi.depth) with a fake depth estimator."""

from __future__ import annotations

import cv2
import numpy as np
from rawi import depth
from rawi.render import bubble_timeline, frames


class FakeDepth:
    """Depth = horizontal gradient: the right side of a panel is closest. Counts its calls."""

    def __init__(self):
        self.calls = 0

    def __call__(self, image):
        self.calls += 1
        h, w = image.shape[:2]
        return np.repeat(np.linspace(0.0, 1.0, w, dtype=np.float32)[None], h, axis=0)


def textured_page(tmp_path):
    rng = np.random.default_rng(0)
    img = rng.integers(0, 255, (400, 300, 3), dtype=np.uint8)
    path = tmp_path / "p.png"
    cv2.imwrite(str(path), img)
    panel = {
        "id": 1,
        "x": 20,
        "y": 20,
        "w": 260,
        "h": 360,
        "duration": 2.5,
        "bubbles": [],
        "depth": None,
    }
    return {
        "image": str(path),
        "width": 300,
        "height": 400,
        "rtl": False,
        "panels": [panel],
    }, img


def test_compute_depths_caches_by_panel_content(tmp_path):
    page, _ = textured_page(tmp_path)
    est = FakeDepth()
    assert depth.compute_depths(page, est, str(tmp_path / "calques")) == 1
    path = page["panels"][0]["depth"]
    assert (
        path.endswith(".png")
        and cv2.imread(path, cv2.IMREAD_UNCHANGED).dtype == np.uint16
    )
    assert depth.compute_depths(page, est, str(tmp_path / "calques")) == 0  # cached
    assert est.calls == 1


def test_load_depth_resizes_and_tolerates_missing(tmp_path):
    page, _ = textured_page(tmp_path)
    depth.compute_depths(page, FakeDepth(), str(tmp_path / "calques"))
    panel = page["panels"][0]
    d = depth.load_depth(panel)
    assert d.shape == (360, 260) and d[:, -1].mean() > 0.95 and d[:, 0].mean() < 0.05
    assert depth.load_depth({**panel, "depth": None}) is None
    assert depth.load_depth({**panel, "depth": str(tmp_path / "absent.png")}) is None


def test_closer_pixels_slide_more_and_balloons_stay_still():
    panel = {"x": 0, "y": 0, "w": 200, "h": 100}
    d = np.repeat(np.linspace(0, 1, 200, dtype=np.float32)[None], 100, axis=0)
    balloon = {
        "x": 140,
        "y": 30,
        "w": 40,
        "h": 40,
        "polygon": [[140, 30], [180, 30], [180, 70], [140, 70]],
    }
    dx, dy = depth.parallax_maps(panel, d, [balloon], (100, 200, 3))
    assert abs(dx[50, 100]) < abs(
        dx[50, 20]
    )  # middle depth hardly moves, the far edge does
    assert np.sign(dx[50, 20]) == -np.sign(
        dx[10, 190]
    )  # near and far slide opposite ways
    assert abs(dx[50, 160]) < 0.05 * abs(dx[10, 190])  # inside the balloon: still
    assert np.allclose(dy, dx * depth.VERTICAL)


def test_apply_parallax_moves_only_the_panel(tmp_path):
    page, img = textured_page(tmp_path)
    panel = page["panels"][0]
    d = FakeDepth()(np.zeros((panel["h"], panel["w"], 3), np.uint8))
    dx, dy = depth.parallax_maps(panel, d, [], img.shape)
    assert np.array_equal(depth.apply_parallax(img, panel, dx, dy, 0.0), img)
    moved = depth.apply_parallax(img, panel, dx, dy, 1.0)
    assert not np.array_equal(moved[20:380, 20:280], img[20:380, 20:280])
    assert np.array_equal(moved[:20], img[:20]) and np.array_equal(
        moved[:, :20], img[:, :20]
    )  # outside


def test_frames_with_depth_keep_their_count_and_differ(tmp_path):
    page, _ = textured_page(tmp_path)
    flat = list(frames(page, fmt="1:1", fps=10, scale=0.3))
    depth.compute_depths(page, FakeDepth(), str(tmp_path / "calques"))
    deep = list(frames(page, fmt="1:1", fps=10, scale=0.3))
    duration, _ = bubble_timeline(page, fps=10)
    assert len(flat) == len(deep) == round(duration * 10)
    assert any(not np.array_equal(a, b) for a, b in zip(flat, deep, strict=True))
