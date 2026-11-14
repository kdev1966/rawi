"""Depth maps of the panels, for parallax (v0.3, step 1).

Each panel gets a relative depth map (1 = closest), computed once by embedkit's
DepthEstimator and cached as a 16-bit PNG whose name holds a hash of the panel's pixels:
an unchanged panel is never recomputed. The renderer then slides every pixel in
proportion to its depth while the camera holds on the panel (``parallax_maps``), with the
balloons kept still so their text does not wobble.
"""

from __future__ import annotations

import hashlib
import os

import cv2
import numpy as np

from .layers import bubble_mask

# peak-to-peak slide of the closest pixels, fraction of the panel width
# (measured: 0.025 is barely visible, 0.08 starts to stretch shapes)
AMPLITUDE = 0.06
# vertical slide relative to the horizontal one
VERTICAL = 0.3
# depth smoothing radius, fraction of the panel's long side (avoids tearing)
SMOOTH = 0.012


def panel_crop(img: np.ndarray, panel: dict) -> np.ndarray:
    h, w = img.shape[:2]
    x0, y0 = max(panel["x"], 0), max(panel["y"], 0)
    x1, y1 = min(panel["x"] + panel["w"], w), min(panel["y"] + panel["h"], h)
    return img[y0:y1, x0:x1]


def compute_depths(
    page: dict, estimator, out_dir: str, img: np.ndarray | None = None
) -> int:
    """Fill ``panel["depth"]`` for every panel of the page; returns how many were computed.

    ``estimator``: image -> HxW float32 in [0, 1] (embedkit DepthEstimator). Maps are cached
    in ``out_dir`` by a hash of the panel's pixels and of the estimator's model.
    """
    if img is None:
        img = cv2.imread(page["image"])
    os.makedirs(out_dir, exist_ok=True)
    model = getattr(
        getattr(estimator, "manifest", None), "id", type(estimator).__name__
    )
    computed = 0
    for panel in page["panels"]:
        crop = panel_crop(img, panel)
        if crop.size == 0:
            continue
        key = hashlib.sha256(
            crop.tobytes() + str(crop.shape).encode() + model.encode()
        ).hexdigest()[:16]
        path = os.path.abspath(os.path.join(out_dir, f"profondeur-{key}.png"))
        if not os.path.isfile(path):
            depth = np.clip(estimator(np.ascontiguousarray(crop)), 0.0, 1.0)
            cv2.imwrite(path, (depth * 65535).astype(np.uint16))
            computed += 1
        panel["depth"] = path
    return computed


def load_depth(panel: dict) -> np.ndarray | None:
    """The panel's depth map resized to the panel (float32, 1 = closest), or None."""
    path = panel.get("depth")
    if not path or not os.path.isfile(path):
        return None
    raw = cv2.imread(path, cv2.IMREAD_UNCHANGED)
    if raw is None:
        return None
    depth = raw.astype(np.float32) / (65535.0 if raw.dtype == np.uint16 else 255.0)
    if depth.ndim == 3:
        depth = depth[..., 0]
    return cv2.resize(depth, (panel["w"], panel["h"]), interpolation=cv2.INTER_LINEAR)


def parallax_maps(
    panel: dict, depth: np.ndarray, bubbles: list[dict], page_shape
) -> tuple[np.ndarray, np.ndarray]:
    """(dx, dy) per pixel of the panel for a unit camera offset; balloons get no slide.

    Pixels closer than the panel's mean depth slide one way, farther ones the other way, so
    the panel keeps its place while its planes separate.
    """
    h, w = depth.shape
    k = max(1.0, SMOOTH * max(h, w))
    d = cv2.GaussianBlur(depth, (0, 0), k)
    centred = d - float(d.mean())
    still = np.zeros(page_shape[:2], np.uint8)
    for b in bubbles:
        still |= bubble_mask(page_shape[:2], b, grow=4)
    keep: np.ndarray = 1.0 - cv2.GaussianBlur(still.astype(np.float32), (0, 0), 3)
    keep = keep[panel["y"] : panel["y"] + h, panel["x"] : panel["x"] + w]
    if keep.shape != centred.shape:  # panel touching the page edge
        keep = cv2.resize(keep, (w, h), interpolation=cv2.INTER_LINEAR)
    dx = centred * keep * (AMPLITUDE * w / 2)
    return dx.astype(np.float32), (dx * VERTICAL).astype(np.float32)


def apply_parallax(
    img: np.ndarray, panel: dict, dx: np.ndarray, dy: np.ndarray, offset: float
) -> np.ndarray:
    """A copy of the page where the panel's pixels slid by ``offset`` (-1 … 1) x (dx, dy)."""
    out = img.copy()
    h, w = dx.shape
    x0, y0 = panel["x"], panel["y"]
    region = img[y0 : y0 + h, x0 : x0 + w]
    if region.shape[:2] != (h, w) or offset == 0:
        return out
    gx, gy = np.meshgrid(np.arange(w, dtype=np.float32), np.arange(h, dtype=np.float32))
    map_x = np.clip(gx - dx * offset, 0, w - 1)
    map_y = np.clip(gy - dy * offset, 0, h - 1)
    out[y0 : y0 + h, x0 : x0 + w] = cv2.remap(
        region, map_x, map_y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE
    )
    return out
