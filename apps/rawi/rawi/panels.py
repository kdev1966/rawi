"""Panel detection, v0.2 method (level 0, OpenCV/NumPy only).

Gutters are the union of two cues, then panels are what remains:

1. the v0.1 gutters (long white strips crossing the page), passed in by the caller;
2. "paper" gutters at any angle: pixels of the page's paper colour (estimated on the whole
   page, so cream or yellowed paper works) connected to the page border, extended from their
   dead ends straight on, only through bright areas (a speech balloon over a gutter).

Panels are the connected components of the rest after a morphological opening, which cuts
thin bridges (balloon tails, outlines). Small mostly-white or hollow fragments are dropped.
Work is done at WORK_SIDE px on the longest side: below ~1500 px thin gutters vanish.
Measured (python -m rawi.evaluate): Qahwati 89 % recall / 82 % precision, Goldorak (1979
scan) 86 % / 90 %; v0.1 gave 93/91 and 39/74.
"""

from __future__ import annotations

import math

import cv2
import numpy as np

WORK_SIDE = 2000  # px, longest side of the working image
PAPER_TOL = 40.0  # Lab distance to the paper colour
BORDER_MARGIN = (
    0.02  # a gutter must reach this close to the page edge (fraction of the short side)
)
BRIGHT_L = 200  # Lab L above which a pixel counts as bright (balloon interior)
BRIGHT_FRAC = 0.6  # an extension must cross at least this fraction of bright pixels
DEAD_END_MIN = (
    0.04  # a gutter branch must run straight this long (fraction of the long side)
)
EXTENSION_MAX = 0.6  # longest extension (fraction of the long side)
OPENING = 0.012  # opening kernel (fraction of the long side)
MIN_AREA = 0.012  # smallest panel (fraction of the page area)
MIN_SIDE = 0.05  # thinnest panel (fraction of the short side)
FRAGMENT_AREA = 0.03  # below this area, a component may be a stray fragment…
FRAGMENT_FILL = 0.45  # …dropped if it fills less than this of its box (hollow)…
FRAGMENT_WHITE = 0.6  # …or if more than this of it is bright (a lone balloon)

_NEIGHBOURS = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]


def paper_colour(lab: np.ndarray) -> np.ndarray:
    """The page's paper colour (Lab): the lightest frequent low-chroma colour.

    Paper is uniform, so it forms a sharp histogram peak even when it covers little of the
    page (thin gutters, narrow margins). Flat-coloured panels form peaks too, so among the
    frequent peaks the lightest one wins: paper is the lightest thing on a printed page
    (balloon interiors are paper as well).
    """
    light = lab[..., 0].astype(np.int32)
    chroma = np.hypot(lab[..., 1] - 128.0, lab[..., 2] - 128.0)
    candidates = lab[(chroma < 30) & (light > 150)].astype(np.int32)
    if len(candidates) < 500:
        return np.array([250.0, 128.0, 128.0])
    bins = candidates // 6
    keys = (bins[:, 0] << 16) | (bins[:, 1] << 8) | bins[:, 2]
    values, counts = np.unique(keys, return_counts=True)
    frequent = counts >= max(0.002 * lab.shape[0] * lab.shape[1], 0.1 * counts.max())
    mode = values[frequent][np.argmax(values[frequent] >> 16)]  # lightest frequent peak
    peak = np.array([(mode >> 16) & 0xFF, (mode >> 8) & 0xFF, mode & 0xFF]) * 6 + 3
    near = candidates[np.abs(candidates - peak).max(axis=1) <= 9]
    return np.median(near, axis=0)


def paper_mask(lab: np.ndarray, tol: float = PAPER_TOL) -> np.ndarray:
    """Pixels close to the paper colour."""
    ref = paper_colour(lab)
    dist = np.sqrt(((lab.astype(np.float32) - ref) ** 2).sum(axis=2))
    return (dist < tol).astype(np.uint8)


def border_connected(mask: np.ndarray, margin: int) -> np.ndarray:
    """Components of ``mask`` that come within ``margin`` px of the image edge."""
    h, w = mask.shape
    n, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    x, y, bw, bh = stats[:, 0], stats[:, 1], stats[:, 2], stats[:, 3]
    keep = (
        (x <= margin) | (y <= margin) | (x + bw >= w - margin) | (y + bh >= h - margin)
    )
    keep[0] = False
    return keep[labels].astype(np.uint8)


def thin(mask: np.ndarray) -> np.ndarray:
    """Zhang-Suen thinning in NumPy (same result on every platform, no OpenCV contrib)."""
    img = np.pad((mask > 0).astype(np.uint8), 1)
    changed = True
    while changed:
        changed = False
        for step in (0, 1):
            p = [
                np.roll(img, (-dy, -dx), (0, 1))
                for dy, dx in (
                    (-1, 0),
                    (-1, 1),
                    (0, 1),
                    (1, 1),
                    (1, 0),
                    (1, -1),
                    (0, -1),
                    (-1, -1),
                )
            ]
            neighbours = sum(p)
            transitions = sum(
                ((p[i] == 0) & (p[(i + 1) % 8] == 1)).astype(np.uint8) for i in range(8)
            )
            if step == 0:
                cond = (p[0] * p[2] * p[4] == 0) & (p[2] * p[4] * p[6] == 0)
            else:
                cond = (p[0] * p[2] * p[6] == 0) & (p[0] * p[4] * p[6] == 0)
            remove = (
                (img == 1)
                & (neighbours >= 2)
                & (neighbours <= 6)
                & (transitions == 1)
                & cond
            )
            if remove.any():
                img[remove] = 0
                changed = True
    return img[1:-1, 1:-1]


def dead_ends(
    skeleton: np.ndarray, min_len: int
) -> list[tuple[int, int, float, float]]:
    """Skeleton end points whose branch runs at least ``min_len`` px without a junction.

    Returns (x, y, ux, uy): the end point and the unit direction pointing out of the branch.
    Short spurs and ends next to a junction are ignored: extending them would cut panels.
    """
    h, w = skeleton.shape
    count = (
        cv2.filter2D(
            skeleton, -1, np.ones((3, 3), np.float32), borderType=cv2.BORDER_CONSTANT
        )
        - skeleton
    )
    out = []
    for y, x in np.argwhere((skeleton == 1) & (count == 1)):
        path = [(int(y), int(x))]
        prev = None
        cy, cx = int(y), int(x)
        while len(path) < min_len:
            nxt = [
                (cy + dy, cx + dx)
                for dy, dx in _NEIGHBOURS
                if 0 <= cy + dy < h
                and 0 <= cx + dx < w
                and skeleton[cy + dy, cx + dx]
                and (cy + dy, cx + dx) != prev
                and (cy + dy, cx + dx) not in path[-3:]
            ]
            if len(nxt) != 1:
                break
            prev = (cy, cx)
            cy, cx = nxt[0]
            path.append((cy, cx))
        if len(path) < min_len:
            continue
        dy, dx = y - path[-1][0], x - path[-1][1]
        norm = math.hypot(dx, dy)
        out.append((int(x), int(y), dx / norm, dy / norm))
    return out


def extend_dead_ends(
    gutter: np.ndarray, bright: np.ndarray, min_len: int, max_len: int
) -> np.ndarray:
    """Prolong gutter dead ends straight on, at any angle, through bright areas only."""
    h, w = gutter.shape
    out = gutter.copy()
    for x, y, ux, uy in dead_ends(thin(gutter), min_len):
        px, py = float(x), float(y)
        steps = 0
        while (
            0 <= int(px) < w
            and 0 <= int(py) < h
            and gutter[int(py), int(px)]
            and steps < 30
        ):
            px, py, steps = px + ux, py + uy, steps + 1  # leave the gutter first
        start = (int(px), int(py))
        length, reached = 0, False
        while length < max_len:
            ix, iy = int(round(px)), int(round(py))
            if not (0 <= ix < w and 0 <= iy < h) or gutter[iy, ix]:
                reached = True  # another gutter or the page edge
                break
            px, py, length = px + ux, py + uy, length + 1
        if not reached or length < 2:
            continue
        probe = np.zeros_like(gutter)
        cv2.line(probe, start, (int(px), int(py)), (1,), 1)
        if float((probe & bright).sum()) / max(int(probe.sum()), 1) >= BRIGHT_FRAC:
            cv2.line(out, start, (int(px), int(py)), (1,), 3)
    return out


def detect(img: np.ndarray, v01_gutter: np.ndarray) -> list[dict]:
    """Panel boxes {x, y, w, h} in ``img`` pixels (unordered).

    ``v01_gutter`` is the v0.1 gutter mask at full resolution (rawi.analyze computes it).
    """
    full_h, full_w = img.shape[:2]
    scale = WORK_SIDE / max(full_h, full_w)
    size = (round(full_w * scale), round(full_h * scale))
    small = cv2.resize(
        img, size, interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR
    )
    h, w = small.shape[:2]
    lab = cv2.cvtColor(small, cv2.COLOR_BGR2LAB).astype(np.int16)

    paper = cv2.morphologyEx(paper_mask(lab), cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
    gutter = border_connected(paper, max(3, int(BORDER_MARGIN * min(h, w))))
    bright = cv2.dilate(
        (lab[..., 0] > BRIGHT_L).astype(np.uint8), np.ones((5, 5), np.uint8)
    )
    gutter = extend_dead_ends(
        gutter, bright, int(DEAD_END_MIN * max(h, w)), int(EXTENSION_MAX * max(h, w))
    )
    gutter |= cv2.resize(
        v01_gutter.astype(np.uint8), size, interpolation=cv2.INTER_NEAREST
    )

    k = max(3, int(OPENING * max(h, w)))
    content = cv2.morphologyEx(
        1 - gutter, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
    )
    n, labels, stats, _ = cv2.connectedComponentsWithStats(content, connectivity=8)
    panels = []
    for i in range(1, n):
        x, y, bw, bh, area = (int(v) for v in stats[i])
        if area < MIN_AREA * h * w or min(bw, bh) < MIN_SIDE * min(h, w):
            continue
        if area < FRAGMENT_AREA * h * w:
            inside = labels[y : y + bh, x : x + bw] == i
            hollow = area / (bw * bh) < FRAGMENT_FILL
            balloon = (
                float(np.mean(lab[y : y + bh, x : x + bw, 0][inside] > BRIGHT_L))
                > FRAGMENT_WHITE
            )
            if hollow or balloon:
                continue
        x0, y0 = int(x / scale), int(y / scale)
        x1, y1 = min(int((x + bw) / scale), full_w), min(int((y + bh) / scale), full_h)
        panels.append({"x": x0, "y": y0, "w": x1 - x0, "h": y1 - y0})
    return panels
