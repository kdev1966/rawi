"""Tests for balloon text reading (rawi.text) without an OCR model (fake recogniser)."""

from __future__ import annotations

import cv2
import numpy as np
from rawi import text


def balloon_page(lines=("ONE", "TWO", "THREE")):
    img = np.full((500, 600, 3), (60, 120, 190), np.uint8)
    cv2.ellipse(img, (300, 250), (250, 180), 0, 0, 360, (255, 255, 255), -1)
    cv2.ellipse(img, (300, 250), (250, 180), 0, 0, 360, (0, 0, 0), 4)
    for k, word in enumerate(lines):
        cv2.putText(
            img, word, (220, 170 + 70 * k), cv2.FONT_HERSHEY_SIMPLEX, 1.4, (0, 0, 0), 3
        )
    poly = cv2.ellipse2Poly((300, 250), (244, 174), 0, 0, 360, 5).tolist()
    bubble = {"id": "b", "x": 56, "y": 76, "w": 488, "h": 348, "polygon": poly}
    return img, bubble


class FakeRecognizer:
    """Records the line images it receives and answers line 1, line 2…"""

    def __init__(self):
        self.lines = []

    def __call__(self, line):
        self.lines.append(line)
        return f"ligne{len(self.lines)}", 0.9


def test_ink_image_is_black_text_on_white():
    img, b = balloon_page()
    clean = text.ink_image(img, b)
    assert clean is not None and clean.ndim == 2
    assert (clean < 100).mean() > 0.01  # the letters
    assert np.median(clean) == 255  # white background, no artwork, no outline


def test_split_lines_finds_each_line():
    img, b = balloon_page()
    ink = (text.ink_image(img, b) < 160).astype(np.uint8)
    assert len(text.split_lines(ink)) == 3


def test_diacritic_band_joins_its_line():
    ink = np.zeros((200, 300), np.uint8)
    ink[60:100, 20:280] = 1  # a line of text
    ink[40:46, 100:110] = 1  # a lone dot above it
    ink[140:180, 20:280] = 1  # a second line
    lines = text.split_lines(ink)
    assert len(lines) == 2 and lines[0][0] <= 40


def test_read_bubble_reads_lines_top_to_bottom():
    img, b = balloon_page()
    rec = FakeRecognizer()
    reading, conf = text.read_bubble(img, b, rec)
    assert reading == "ligne1\nligne2\nligne3" and conf == 0.9  # one line per text line
    assert all(line.dtype == np.uint8 and line.ndim == 2 for line in rec.lines)


def test_segments_split_scripts_and_directions():
    segs = text.segments("مرحبا! عندي 3 Rendez-vous اليوم")
    assert [s["script"] for s in segs] == ["arabic", "latin", "arabic"]
    assert [s["direction"] for s in segs] == ["rtl", "ltr", "rtl"]
    assert segs[1]["text"].startswith("Rendez-vous")
    assert text.segments("Are you profitable?") == [
        {"text": "Are you profitable?", "script": "latin", "direction": "ltr"}
    ]


def test_read_page_fills_fields_and_respects_manual_text(tmp_path):
    img, b = balloon_page()
    path = tmp_path / "p.png"
    cv2.imwrite(str(path), img)
    manual = {**b, "id": "m", "text": "écrit à la main", "source": "manual"}
    page = {"image": str(path), "panels": [{"bubbles": [dict(b), manual]}]}
    assert text.read_page(page, FakeRecognizer()) == 1
    read, kept = page["panels"][0]["bubbles"]
    assert (
        read["source"] == "ocr"
        and read["text"].startswith("ligne")
        and read["lang"] == ["und-Latn"]
    )
    assert read["segments"][0]["direction"] == "ltr" and read["confidence"] == 0.9
    assert kept["text"] == "écrit à la main" and kept["source"] == "manual"


def test_empty_balloon_gives_no_text(tmp_path):
    img, b = balloon_page(lines=())
    assert text.read_bubble(img, b, FakeRecognizer()) == ("", 0.0)
