"""Page layers for live bubbles: the page with empty bubbles, and the text of each bubble.

Level 0 (PRD principle 1: a balloon's interior is plain, fill it instead of running a model).
Inside each balloon, the "ink" is every pixel that differs clearly from the balloon's own
paper colour (letters, but also an emoji or a coloured word); ink touching the edge of the
interior is left alone so the black outline is never erased. The empty page repaints the ink
with the paper colour; each bubble's text is a cut-out pasted back when it is read.

Erasing whole balloons and rebuilding the artwork under them was tried first (cv2.inpaint,
then a soft blur): the blurred patches looked like damaged pictures. Empty balloons need no
invented artwork, and they are also what translation will need (new text in the balloon).
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

INK_DIST = (
    60.0  # Lab distance from the balloon's paper colour above which a pixel is ink
)
INK_GROW = 2  # px, ink mask growth (anti-aliased letter edges)
EDGE = 3  # px, ink touching this band along the interior's edge is the outline, kept
FEATHER = 0.8  # px, soft edge of the text cut-outs


def bubble_mask(shape: tuple[int, int], bubble: dict, grow: int = 0) -> np.ndarray:
    """uint8 mask (0/1) of a balloon's interior: its outline, or an ellipse in its box."""
    mask = np.zeros(shape, np.uint8)
    if bubble.get("polygon"):
        cv2.fillPoly(mask, [np.array(bubble["polygon"], np.int32)], (1,))
    else:
        x, y, w, h = bubble["x"], bubble["y"], bubble["w"], bubble["h"]
        cv2.ellipse(
            mask,
            (x + w // 2, y + h // 2),
            (int(w * 0.47), int(h * 0.47)),
            0,
            0,
            360,
            (1,),
            -1,
        )
    if grow <= 0:
        return mask
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * grow + 1, 2 * grow + 1))
    return np.asarray(cv2.dilate(mask, kernel), np.uint8)


def bubble_ink(crop: np.ndarray, inside: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """(ink mask 0/1, paper colour BGR) of a balloon, both for the crop of its box."""
    lab = cv2.cvtColor(crop, cv2.COLOR_BGR2LAB).astype(np.float32)
    pixels = lab[inside > 0]
    if len(pixels) == 0:
        return np.zeros_like(inside), np.array([255, 255, 255], np.uint8)
    light = pixels[:, 0] >= np.percentile(pixels[:, 0], 60)
    paper_lab = np.median(pixels[light], axis=0)
    ink = (
        (np.sqrt(((lab - paper_lab) ** 2).sum(axis=2)) > INK_DIST) & (inside > 0)
    ).astype(np.uint8)
    # outside the crop counts as empty, so the band also runs along the crop's sides
    kernel = np.ones((2 * EDGE + 1, 2 * EDGE + 1), np.uint8)
    eroded = cv2.erode(inside, kernel, borderType=cv2.BORDER_CONSTANT, borderValue=(0,))
    edge = inside & (1 - eroded)
    n, labels = cv2.connectedComponents(ink, connectivity=8)
    if n > 1:
        touching = np.unique(labels[(edge > 0) & (ink > 0)])
        ink[np.isin(labels, touching[touching > 0])] = 0
    ink = (
        cv2.dilate(ink, np.ones((2 * INK_GROW + 1, 2 * INK_GROW + 1), np.uint8))
        & inside
    )
    paper_bgr = cv2.cvtColor(
        paper_lab.reshape(1, 1, 3).astype(np.uint8), cv2.COLOR_LAB2BGR
    )[0, 0]
    return ink, paper_bgr


@dataclass
class Sprite:
    """A bubble's text cut out of the page: BGR crop, alpha (float32 0..1), top-left corner."""

    bubble_id: str
    x: int
    y: int
    image: np.ndarray
    alpha: np.ndarray


@dataclass
class PageLayers:
    base: np.ndarray  # the page with every balloon emptied
    sprites: dict[str, Sprite]

    def with_bubbles(self, ids: set[str]) -> np.ndarray:
        """The base page with the text of the given bubbles pasted back in place."""
        out = self.base.copy()
        for bubble_id in ids:
            s = self.sprites.get(bubble_id)
            if s is None:
                continue
            h, w = s.alpha.shape
            roi = out[s.y : s.y + h, s.x : s.x + w].astype(np.float32)
            a = s.alpha[..., None]
            out[s.y : s.y + h, s.x : s.x + w] = (roi * (1 - a) + s.image * a).astype(
                np.uint8
            )
        return out


def build_layers(img: np.ndarray, bubbles: list[dict]) -> PageLayers:
    """Empty every balloon of ``img`` and cut out its text. Bubbles need a unique ``id``."""
    h, w = img.shape[:2]
    base = img.copy()
    sprites = {}
    for b in bubbles:
        inside_full = bubble_mask((h, w), b)
        ys, xs = np.nonzero(inside_full)
        if len(xs) == 0:
            continue
        x0, x1, y0, y1 = (
            int(xs.min()),
            int(xs.max()) + 1,
            int(ys.min()),
            int(ys.max()) + 1,
        )
        crop = img[y0:y1, x0:x1]
        ink, paper = bubble_ink(crop, inside_full[y0:y1, x0:x1])
        if not ink.any():
            continue
        alpha = cv2.GaussianBlur(ink.astype(np.float32), (0, 0), FEATHER)
        region = base[y0:y1, x0:x1].astype(np.float32)
        a = alpha[..., None]
        base[y0:y1, x0:x1] = (region * (1 - a) + paper.astype(np.float32) * a).astype(
            np.uint8
        )
        sprites[b["id"]] = Sprite(b["id"], x0, y0, crop.copy(), alpha)
    return PageLayers(base, sprites)
