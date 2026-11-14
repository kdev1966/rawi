"""Reading the text of speech balloons (OCR), stored per balloon (PRD §6.4).

For each balloon: its ink (letters on the balloon's paper, see rawi.layers) is put in black
on white, cut into lines (classical: bands of ink, diacritic-only bands joined to the nearest
line), and each line is read by embedkit's TextRecognizer. The text is then split into
Arabic and Latin segments, each with its writing direction.

A balloon whose text was typed by the user (``source == "manual"``) is never overwritten.
"""

from __future__ import annotations

import re

import cv2
import numpy as np

from .layers import bubble_ink, bubble_mask

LINE_REL = 0.08  # a text row holds at least this fraction of the busiest row's ink
MERGE_REL = 0.15  # a band with less ink than this fraction of the richest one is a diacritic band
PAD = 8  # px of white around each line given to the recogniser
MIN_CONFIDENCE = (
    0.5  # lines read with less confidence are dropped: no text beats wrong text
)

_ARABIC = re.compile("[؀-ۿݐ-ݿﭐ-﷿ﹰ-﻿]")
_LATIN = re.compile("[A-Za-zÀ-ɏ]")


def ink_image(img: np.ndarray, bubble: dict) -> np.ndarray | None:
    """The balloon's text in black on white (grey uint8, cropped to the balloon), or None."""
    h, w = img.shape[:2]
    inside = bubble_mask((h, w), bubble)
    ys, xs = np.nonzero(inside)
    if len(xs) == 0:
        return None
    x0, x1, y0, y1 = xs.min(), xs.max() + 1, ys.min(), ys.max() + 1
    crop = img[y0:y1, x0:x1]
    ink, _ = bubble_ink(crop, inside[y0:y1, x0:x1])
    if not ink.any():
        return None
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    out = np.full_like(gray, 255)
    out[ink > 0] = gray[ink > 0]
    return out


def split_lines(ink: np.ndarray) -> list[tuple[int, int]]:
    """Row bands (top, bottom) of the text lines in a 0/1 ink mask."""
    profile = ink.sum(axis=1).astype(float)
    if profile.max() == 0:
        return []
    rows = profile > LINE_REL * profile.max()
    bands: list[list[int]] = []
    start = None
    for i, on in enumerate(rows):
        if on and start is None:
            start = i
        elif not on and start is not None:
            bands.append([start, i])
            start = None
    if start is not None:
        bands.append([start, len(rows)])
    if len(bands) > 1:  # diacritic-only bands join the nearest real line
        richest = max(profile[a:b].sum() for a, b in bands)
        kept = [r for r in bands if profile[r[0] : r[1]].sum() >= MERGE_REL * richest]
        for r in bands:
            if r in kept:
                continue
            near = min(kept, key=lambda k: min(abs(k[0] - r[1]), abs(r[0] - k[1])))
            near[0], near[1] = min(near[0], r[0]), max(near[1], r[1])
        bands = sorted(kept)
    lines = []  # grow each band to the middle of the neighbouring gaps
    for k, (a, b) in enumerate(bands):
        top = (bands[k - 1][1] + a) // 2 if k else max(0, a - (b - a) // 2)
        bottom = (
            (b + bands[k + 1][0]) // 2
            if k + 1 < len(bands)
            else min(len(rows), b + (b - a) // 2)
        )
        lines.append((top, bottom))
    return lines


def segments(text: str) -> list[dict]:
    """Split text into Arabic / Latin runs; digits, spaces and punctuation stay in the run."""
    out: list[dict] = []
    for ch in text:
        script = (
            "arabic" if _ARABIC.match(ch) else "latin" if _LATIN.match(ch) else None
        )
        if out and (script is None or script == out[-1]["script"]):
            out[-1]["text"] += ch
        elif script is None:
            out.append({"text": ch, "script": "other"})
        else:
            if out and out[-1]["script"] == "other":
                out[-1]["script"] = script
                out[-1]["text"] += ch
            else:
                out.append({"text": ch, "script": script})
    result = []
    for seg in out:
        t = seg["text"].strip()
        if t:
            direction = "rtl" if seg["script"] == "arabic" else "ltr"
            result.append({"text": t, "script": seg["script"], "direction": direction})
    return result


def read_bubble(img: np.ndarray, bubble: dict, recognizer) -> tuple[str, float]:
    """(text, mean line confidence) of one balloon; ("", 0.0) when nothing can be read."""
    clean = ink_image(img, bubble)
    if clean is None:
        return "", 0.0
    ink = (clean < 160).astype(np.uint8)
    texts, confs = [], []
    for top, bottom in split_lines(ink):
        band = clean[top:bottom]
        cols = np.nonzero((band < 160).sum(axis=0))[0]
        if len(cols) == 0 or bottom - top < 6:
            continue
        band = band[:, max(0, cols[0] - 4) : cols[-1] + 5]
        band = cv2.copyMakeBorder(
            band, PAD, PAD, PAD, PAD, cv2.BORDER_CONSTANT, value=(255,)
        )
        text, conf = recognizer(band)
        if text and conf >= MIN_CONFIDENCE:
            texts.append(text)
            confs.append(conf)
    return " ".join(texts), (float(np.mean(confs)) if confs else 0.0)


def read_page(page: dict, recognizer, img: np.ndarray | None = None) -> int:
    """Fill the text fields of every balloon of a page; returns how many were read."""
    if img is None:
        img = cv2.imread(page["image"])
    count = 0
    for panel in page["panels"]:
        for b in panel["bubbles"]:
            if b.get("source") == "manual":
                continue
            text, conf = read_bubble(img, b, recognizer)
            segs = segments(text)
            scripts = {s["script"] for s in segs}
            b.update(
                text=text,
                segments=segs,
                lang=[
                    tag
                    for script, tag in (("arabic", "ar"), ("latin", "und-Latn"))
                    if script in scripts
                ],
                confidence=round(conf, 3) if text else None,
                source="ocr" if text else None,
            )
            count += bool(text)
    return count
