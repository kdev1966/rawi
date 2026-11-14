"""Page layers for live bubbles: the page without its bubbles, and one cut-out per bubble.

Level 0 (PRD v0.2): the area under a bubble is filled with a soft average of the colours
around it (normalised convolution). cv2.inpaint (Telea) was tried first: it smears the border
colours into radial streaks, far more visible than a soft blur. A bubble is
cut along its outline (project format 3) grown by OUTLINE to include the black stroke, or
along an ellipse inside its box when the outline is unknown (migrated projects).
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

OUTLINE = 0.006  # outline growth, fraction of the page's long side (black stroke + anti-aliasing)
FEATHER = 1.5  # px, soft edge of the cut-outs
FILL_SIGMA = 0.027  # blur radius of the fill, fraction of the page's long side
FILL_WORK = 400  # px, long side of the reduced copy the fill is computed on


def bubble_mask(shape: tuple[int, int], bubble: dict, grow: int) -> np.ndarray:
    """uint8 mask (0/1) of one bubble, grown by ``grow`` px."""
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


def soft_fill(img: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Replace masked pixels by a blurred average of the unmasked pixels around them.

    The fill is very smooth, so it is computed on a copy reduced to FILL_WORK px and enlarged:
    the same look for a fraction of the cost (large Gaussian blurs at full size took seconds).
    """
    h, w = mask.shape
    f = min(1.0, FILL_WORK / max(h, w))
    small = (max(1, round(w * f)), max(1, round(h * f)))
    known = cv2.resize(
        (1 - mask).astype(np.float32), small, interpolation=cv2.INTER_AREA
    )
    acc = cv2.resize(
        img.astype(np.float32) * (1 - mask)[..., None],
        small,
        interpolation=cv2.INTER_AREA,
    )
    fill = np.zeros_like(acc)
    todo = np.ones(known.shape, bool)
    sigma = FILL_SIGMA * max(small)
    for _ in range(3):  # widen the blur where the masked area is too large
        num = cv2.GaussianBlur(acc, (0, 0), sigma)
        den = cv2.GaussianBlur(known, (0, 0), sigma)
        ok = todo & (den > 0.05)
        fill[ok] = num[ok] / den[ok][:, None]
        todo &= ~ok
        sigma *= 3
    if todo.any():
        fill[todo] = acc.sum(axis=(0, 1)) / max(float(known.sum()), 1.0)
    fill = cv2.resize(fill, (w, h), interpolation=cv2.INTER_LINEAR)
    if f < 1:  # smooth the enlargement steps
        fill = cv2.GaussianBlur(fill, (0, 0), 1 / f)
    a = cv2.GaussianBlur(mask.astype(np.float32), (0, 0), 3)[..., None]
    return (img * (1 - a) + fill * a).astype(np.uint8)


@dataclass
class Sprite:
    """A bubble cut out of the page: BGR crop, alpha (float32 0..1) and its box in the page."""

    bubble_id: str
    x: int
    y: int
    image: np.ndarray
    alpha: np.ndarray


@dataclass
class PageLayers:
    base: np.ndarray  # the page with every bubble erased
    sprites: dict[str, Sprite]

    def with_bubbles(self, ids: set[str]) -> np.ndarray:
        """The base page with the given bubbles pasted back in place."""
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
    """Erase ``bubbles`` from ``img`` and cut each one out. Bubbles need a unique ``id``."""
    h, w = img.shape[:2]
    grow = max(2, round(OUTLINE * max(h, w)))
    union = np.zeros((h, w), np.uint8)
    sprites = {}
    for b in bubbles:
        mask = bubble_mask((h, w), b, grow)
        union |= mask
        ys, xs = np.nonzero(mask)
        if len(xs) == 0:
            continue
        x0, x1, y0, y1 = xs.min(), xs.max() + 1, ys.min(), ys.max() + 1
        alpha = cv2.GaussianBlur(mask[y0:y1, x0:x1].astype(np.float32), (0, 0), FEATHER)
        sprites[b["id"]] = Sprite(
            b["id"], int(x0), int(y0), img[y0:y1, x0:x1].copy(), alpha
        )
    base = soft_fill(img, union) if union.any() else img.copy()
    return PageLayers(base, sprites)
