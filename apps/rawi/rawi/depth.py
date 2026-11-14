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


# --- layered parallax (v0.3, step 2): foreground cut out, scenery rebuilt behind it ---------

FRONT_MIN, FRONT_MAX = 0.03, 0.85  # outside these area fractions, no meaningful split
HOLE_GROW = 7  # px, the rebuilt area extends past the foreground's edge
BACK_RATIO = (
    0.3  # the scenery slides this fraction of the foreground's slide, the other way
)


def front_mask(depth: np.ndarray, still: np.ndarray) -> np.ndarray | None:
    """Foreground of a panel (uint8 0/1): depth above the Otsu threshold, balloons excluded.

    None when the split is not meaningful (almost nothing, or almost everything, in front).
    """
    d8 = (cv2.GaussianBlur(depth, (0, 0), 3) * 255).astype(np.uint8)
    _, front = cv2.threshold(d8, 0, 1, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    front = cv2.morphologyEx(front, cv2.MORPH_OPEN, np.ones((9, 9), np.uint8))
    front = (front & (1 - still)).astype(np.uint8)
    share = float(front.mean())
    return front if FRONT_MIN <= share <= FRONT_MAX else None


def _still_mask(panel: dict, shape) -> np.ndarray:
    """Balloons of the panel (uint8 0/1, panel coordinates): they never move."""
    still = np.zeros(shape[:2], np.uint8)
    for b in panel["bubbles"]:
        still |= bubble_mask(shape[:2], b, grow=6)
    return still[
        panel["y"] : panel["y"] + panel["h"], panel["x"] : panel["x"] + panel["w"]
    ]


def compute_layers(
    page: dict, inpainter, out_dir: str, img: np.ndarray | None = None
) -> int:
    """Fill ``panel["front"]`` and ``panel["back"]`` for panels that have a depth map.

    ``inpainter``: (image, mask) -> image (embedkit Inpainter). Files are cached in
    ``out_dir`` by a hash of the panel, its depth map, its balloons and the model.
    Returns how many panels were computed.
    """
    import json

    if img is None:
        img = cv2.imread(page["image"])
    os.makedirs(out_dir, exist_ok=True)
    model = getattr(
        getattr(inpainter, "manifest", None), "id", type(inpainter).__name__
    )
    computed = 0
    for panel in page["panels"]:
        panel["front"] = panel["back"] = None
        depth = load_depth(panel)
        crop = panel_crop(img, panel)
        if depth is None or crop.shape[:2] != depth.shape:
            continue
        balloons = json.dumps(
            [
                [b["x"], b["y"], b["w"], b["h"], b.get("polygon")]
                for b in panel["bubbles"]
            ]
        )
        key = hashlib.sha256(
            crop.tobytes()
            + str(panel["depth"]).encode()
            + balloons.encode()
            + model.encode()
        ).hexdigest()[:16]
        front_path = os.path.abspath(os.path.join(out_dir, f"avant-{key}.png"))
        back_path = os.path.abspath(os.path.join(out_dir, f"fond-{key}.png"))
        if not (os.path.isfile(front_path) and os.path.isfile(back_path)):
            front = front_mask(depth, _still_mask(panel, img.shape))
            if front is None:
                continue
            hole = cv2.dilate(
                front, np.ones((2 * HOLE_GROW + 1, 2 * HOLE_GROW + 1), np.uint8)
            )
            cv2.imwrite(back_path, inpainter(np.ascontiguousarray(crop), hole))
            cv2.imwrite(front_path, front * 255)
            computed += 1
        panel["front"], panel["back"] = front_path, back_path
    return computed


def load_layers(panel: dict) -> tuple[np.ndarray, np.ndarray] | None:
    """(rebuilt scenery BGR, foreground alpha float32 0..1) of a panel, or None."""
    front, back = panel.get("front"), panel.get("back")
    if not front or not back or not (os.path.isfile(front) and os.path.isfile(back)):
        return None
    mask, scenery = cv2.imread(front, cv2.IMREAD_GRAYSCALE), cv2.imread(back)
    if mask is None or scenery is None or mask.shape != scenery.shape[:2]:
        return None
    if mask.shape != (panel["h"], panel["w"]):
        mask = cv2.resize(
            mask, (panel["w"], panel["h"]), interpolation=cv2.INTER_NEAREST
        )
        scenery = cv2.resize(
            scenery, (panel["w"], panel["h"]), interpolation=cv2.INTER_LINEAR
        )
    alpha = cv2.GaussianBlur(mask.astype(np.float32) / 255.0, (0, 0), 1.5)
    return scenery, alpha


def _shift(image: np.ndarray, dx: float, dy: float) -> np.ndarray:
    m = np.array([[1, 0, dx], [0, 1, dy]], dtype=np.float32)
    return cv2.warpAffine(
        image,
        m,
        (image.shape[1], image.shape[0]),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_REPLICATE,
    )


def apply_layers(
    img: np.ndarray, panel: dict, layers: tuple[np.ndarray, np.ndarray], offset: float
) -> np.ndarray:
    """A copy of the page where the panel's foreground and scenery slid apart by ``offset``.

    The foreground slides by up to AMPLITUDE/2 of the panel width, the scenery BACK_RATIO of
    that the other way; balloons (taken from ``img``) stay where they are.
    """
    out = img.copy()
    scenery, alpha = layers
    h, w = alpha.shape
    x0, y0 = panel["x"], panel["y"]
    region = img[y0 : y0 + h, x0 : x0 + w]
    if region.shape[:2] != (h, w) or offset == 0:
        return out
    s = AMPLITUDE * w / 2 * offset
    back = _shift(scenery, -BACK_RATIO * s, -BACK_RATIO * s * VERTICAL).astype(
        np.float32
    )
    front = _shift(region, s, s * VERTICAL).astype(np.float32)
    a = _shift(alpha, s, s * VERTICAL)[..., None]
    composed = back * (1 - a) + front * a
    still = _still_mask(panel, img.shape).astype(bool)
    composed[still] = region[still]
    out[y0 : y0 + h, x0 : x0 + w] = composed.astype(np.uint8)
    return out
