"""Speech balloon detection on a whole page (level 0, OpenCV/NumPy only).

A balloon is a closed white area with dark text inside, black and white only. The search
runs on the whole page (a balloon may straddle two panels), then each balloon is attached
to the panel it overlaps most.

1. Candidates: white pixels, minus the thin gutter strips. Only the v0.1 gutters without
   their extensions are used: extensions are drawn precisely through balloons and would
   cut them in two. White blobs stuck to a gutter (a balloon touching it) are kept.
2. Each white shape is filled (text holes closed), then a morphological opening cuts the
   narrow necks joining a balloon to other white things (an apron, a sheet of paper).
3. A shape is a balloon if it is solid, holds 3 to 45 % of dark pixels (text) and almost no
   colourful pixels: white screens, charts and objects carry colour, balloons do not.

Measured on the 8 Qahwati pages (python -m rawi.evaluate qahwati_bubbles): 89 % of the
balloons found, 91 % of the detections right (v0.1 per-panel search: 85 % / 68 %).
"""

from __future__ import annotations

import cv2
import numpy as np

STRIP = 0.015  # gutter strips are thinner than this (fraction of the page's long side)
NECK = 0.018  # necks thinner than this are cut (fraction of the long side)
MIN_AREA = 0.004  # smallest balloon box (fraction of the page area)
MAX_AREA = 0.2  # largest balloon box
MIN_W, MIN_H = (
    0.03,
    0.02,
)  # smallest balloon width / height (fraction of page width / height)
SOLIDITY = 0.75  # area / convex hull area
TEXT_MIN, TEXT_MAX = 0.03, 0.45  # fraction of dark pixels inside (the text)
DARK = 100  # grey level below which a pixel is text
COLOURFUL_MAX = 0.06  # at most this fraction of colourful pixels inside
COLOURFUL_S, COLOURFUL_V = 90, 70  # HSV saturation and value of a colourful pixel


def component_outlines(mask: np.ndarray) -> list[np.ndarray]:
    """Outer contour of every connected component, in image coordinates.

    findContours(RETR_EXTERNAL) on the whole mask would miss shapes lying inside the holes
    of another shape, e.g. every balloon inside the white ring of the page margins.
    """
    n, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    outlines = []
    for i in range(1, n):
        x, y, w, h = (int(v) for v in stats[i, :4])
        crop = (labels[y : y + h, x : x + w] == i).astype(np.uint8)
        contours, _ = cv2.findContours(crop, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        outlines.append(max(contours, key=cv2.contourArea) + (x, y))
    return outlines


def candidates(white: np.ndarray, gutter: np.ndarray) -> np.ndarray:
    """Filled white shapes, gutter strips removed and narrow necks cut (uint8 0/1)."""
    h, w = white.shape
    k = max(5, int(STRIP * max(h, w)) | 1)
    blobs = cv2.morphologyEx(gutter, cv2.MORPH_OPEN, np.ones((k, k), np.uint8))
    strips = cv2.dilate(gutter & (1 - blobs), np.ones((3, 3), np.uint8))
    cand = cv2.morphologyEx(
        (white & (1 - strips)).astype(np.uint8),
        cv2.MORPH_CLOSE,
        np.ones((5, 5), np.uint8),
    )
    # Fill balloon-sized shapes only (closes the text holes). The big white network of page
    # margins and gutters must stay unfilled: the panels are holes in it.
    solid = cand.copy()
    small = [
        c
        for c in component_outlines(cand)
        if cv2.boundingRect(c)[2] * cv2.boundingRect(c)[3] <= MAX_AREA * h * w
    ]
    cv2.drawContours(solid, small, -1, (1,), -1)
    n = max(3, int(NECK * max(h, w)) | 1)
    return np.asarray(
        cv2.morphologyEx(
            solid, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (n, n))
        ),
        np.uint8,
    )


def detect(img: np.ndarray, white: np.ndarray, gutter: np.ndarray) -> list[dict]:
    """Balloons on the page: {x, y, w, h, text_px, polygon} in page pixels."""
    h, w = white.shape
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    colourful = (hsv[..., 1] > COLOURFUL_S) & (hsv[..., 2] > COLOURFUL_V)
    found = []
    for c in component_outlines(candidates(white, gutter)):
        bx, by, bw, bh = cv2.boundingRect(c)
        if not (
            MIN_AREA * h * w <= bw * bh <= MAX_AREA * h * w
            and bw >= MIN_W * w
            and bh >= MIN_H * h
        ):
            continue
        fill = np.zeros((bh, bw), np.uint8)
        cv2.drawContours(fill, [c - (bx, by)], -1, (1,), -1)
        inside = fill > 0
        area = int(inside.sum())
        solidity = area / max(cv2.contourArea(cv2.convexHull(c)), 1)
        dark = int(((gray[by : by + bh, bx : bx + bw] < DARK) & inside).sum())
        text = dark / max(area, 1)
        colour = float(colourful[by : by + bh, bx : bx + bw][inside].mean())
        if (
            solidity > SOLIDITY
            and TEXT_MIN < text < TEXT_MAX
            and colour < COLOURFUL_MAX
        ):
            outline = cv2.approxPolyDP(c, 1.5, True).reshape(-1, 2)
            found.append(
                {
                    "x": bx,
                    "y": by,
                    "w": bw,
                    "h": bh,
                    "text_px": dark,
                    "polygon": outline.astype(int).tolist(),
                }
            )
    return found


def assign(bubbles: list[dict], panels: list[dict]) -> None:
    """Append each balloon to the ``bubbles`` list of the panel it overlaps most."""
    for p in panels:
        p["bubbles"] = []
    if not panels:
        return
    for b in bubbles:

        def overlap(p: dict, b: dict = b) -> int:
            ix = min(b["x"] + b["w"], p["x"] + p["w"]) - max(b["x"], p["x"])
            iy = min(b["y"] + b["h"], p["y"] + p["h"]) - max(b["y"], p["y"])
            return max(ix, 0) * max(iy, 0)

        def distance(p: dict, b: dict = b) -> float:
            return float(
                np.hypot(
                    p["x"] + p["w"] / 2 - b["x"] - b["w"] / 2,
                    p["y"] + p["h"] / 2 - b["y"] - b["h"] / 2,
                )
            )

        best = max(panels, key=overlap)
        if overlap(best) == 0:
            best = min(panels, key=distance)
        best["bubbles"].append(b)
