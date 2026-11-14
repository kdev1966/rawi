"""Tests for subtitles (rawi.subtitles) and the bubble timeline they follow."""

from __future__ import annotations

import json
import shutil
import subprocess

import cv2
import numpy as np
import pytest
from rawi import subtitles
from rawi.__main__ import main
from rawi.render import bubble_timeline, can_burn_subtitles, frames


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("مريم: قداش عندكم؟", "قداش عندكم؟"),
        ("بوحميد؛ باهي", "باهي"),  # colon read as the Arabic semicolon by the OCR
        ("Bob : hello there", "hello there"),
        ("منتصر! عشرة آلاف", "منتصر! عشرة آلاف"),  # a vocative stays
        ("Ratio 3:1 today", "Ratio 3:1 today"),  # no name at the start
        ("مريم:", "مريم:"),  # nothing after the name: keep the text
        ("مريم:\nقداش عندكم", "قداش عندكم"),  # name alone on the first line
    ],
)
def test_strip_speaker(text, expected):
    assert subtitles.strip_speaker(text) == expected


def test_known_name_without_colon_is_dropped_only_when_known():
    known = {"مريم"}
    assert (
        subtitles.strip_speaker("مريم\nقداش عندكم", known) == "قداش عندكم"
    )  # colon lost by the OCR
    assert subtitles.strip_speaker("وبعد؟\nشنوة", known) == "وبعد؟ شنوة"  # not a name
    assert (
        subtitles.strip_speaker("مريم قداش عندكم", known) == "مريم قداش عندكم"
    )  # same line: keep


def test_speaker_names_from_the_project():
    page = {
        "panels": [
            {
                "bubbles": [
                    {"text": "مريم: مرحبا"},
                    {"text": "Bob : hi"},
                    {"text": "منتصر! لا"},
                ]
            }
        ]
    }
    assert subtitles.speaker_names([page]) == {"مريم", "Bob"}


def test_repeated_one_word_first_line_is_a_name():
    texts = ["مريم\nقداش عندكم", "مريم.\nتوفى الفلوس", "وبعد؟\nشنوة يصير"]
    page = {"panels": [{"bubbles": [{"text": t} for t in texts]}]}
    names = subtitles.speaker_names([page])
    assert names == {"مريم"}  # twice at the head of a balloon; "وبعد؟" only once
    assert subtitles.strip_speaker(texts[1], names) == "توفى الفلوس"


def test_srt_format_and_right_to_left_mark():
    srt = subtitles.to_srt([(0.5, 2.25, "مرحبا Cash"), (3661.0, 3662.5, "Hello")])
    blocks = srt.split("\n\n")
    assert blocks[0].splitlines() == [
        "1",
        "00:00:00,500 --> 00:00:02,250",
        subtitles.RLM + "مرحبا Cash",
    ]
    assert blocks[1].splitlines()[1] == "01:01:01,000 --> 01:01:02,500"
    assert not blocks[1].splitlines()[2].startswith(subtitles.RLM)


def test_filter_path_escapes_special_characters():
    assert subtitles.filter_path("/a b/c:d,e'f.srt") == "/a b/c\\:d\\,e\\'f.srt"


def page_with_two_balloons(tmp_path):
    img = np.full((800, 600, 3), (60, 120, 190), np.uint8)
    path = tmp_path / "p.png"
    cv2.imwrite(str(path), img)
    b1 = {
        "id": "b1",
        "x": 50,
        "y": 50,
        "w": 100,
        "h": 60,
        "order": 1,
        "polygon": None,
        "text": "مريم: صباح الخير",
    }
    b2 = {
        "id": "b2",
        "x": 300,
        "y": 50,
        "w": 100,
        "h": 60,
        "order": 2,
        "polygon": None,
        "text": "Bonjour",
    }
    b3 = {
        "id": "b3",
        "x": 50,
        "y": 500,
        "w": 100,
        "h": 60,
        "order": 1,
        "polygon": None,
        "text": "",
    }
    return {
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
                "h": 400,
                "duration": 4.0,
                "bubbles": [b1, b2],
            },
            {
                "id": 2,
                "x": 0,
                "y": 400,
                "w": 600,
                "h": 400,
                "duration": 3.0,
                "bubbles": [b3],
            },
        ],
    }


def test_timeline_matches_rendered_frames(tmp_path):
    page = page_with_two_balloons(tmp_path)
    duration, events = bubble_timeline(page, fps=10)
    assert len(list(frames(page, fmt="1:1", fps=10, scale=0.2))) == round(duration * 10)
    (b1, s1, e1), (b2, s2, e2), (b3, s3, e3) = events
    assert b1["id"] == "b1" and s1 < e1 == s2 < e2 and e2 <= s3
    assert all(abs(t * 10 - round(t * 10)) < 1e-9 for t in (s1, s2, s3))  # on frames


def test_cues_strip_names_skip_empty_and_chain_pages(tmp_path):
    page = page_with_two_balloons(tmp_path)
    items = subtitles.cues([page, page], fps=10)
    assert [t for _, _, t in items] == [
        "صباح الخير",
        "Bonjour",
    ] * 2  # empty balloon skipped
    duration, _ = bubble_timeline(page, fps=10)
    assert items[2][0] == pytest.approx(items[0][0] + duration)  # second page offset
    kept = subtitles.cues([page], fps=10, keep_names=True)
    assert kept[0][2] == "مريم: صباح الخير"


@pytest.mark.skipif(
    not (shutil.which("ffmpeg") and shutil.which("ffprobe")), reason="FFmpeg absent"
)
@pytest.mark.skipif(
    not can_burn_subtitles(), reason="FFmpeg sans libass (filtre subtitles absent)"
)
def test_render_writes_srt_and_burns_subtitles(tmp_path, monkeypatch):
    page = page_with_two_balloons(tmp_path)
    proj = {"version": 3, "rtl": False, "pages": [page]}
    (tmp_path / "projet.json").write_text(
        json.dumps(proj, ensure_ascii=False), encoding="utf-8"
    )
    monkeypatch.chdir(tmp_path)
    assert main(
        [
            "rendre",
            "projet.json",
            "--apercu",
            "--fps",
            "10",
            "--sous-titres",
            "les-deux",
        ]
    ) in (None, 0)
    srt = (tmp_path / "videos" / "episode_01_9x16.srt").read_text(encoding="utf-8")
    assert "صباح الخير" in srt and "مريم" not in srt and "Bonjour" in srt
    video = tmp_path / "videos" / "episode_01_9x16.mp4"
    assert video.is_file()
    # burned: a frame while the first subtitle is on screen differs from the same video without
    assert main(
        [
            "rendre",
            "projet.json",
            "--apercu",
            "--fps",
            "10",
            "--sous-titres",
            "aucun",
            "--dossier",
            "plain",
        ]
    ) in (None, 0)
    start = (
        float(srt.splitlines()[1].split(" --> ")[0].replace(",", ".").split(":")[-1])
        + 0.2
    )

    def grab(path):
        raw = subprocess.run(
            [
                "ffmpeg",
                "-v",
                "error",
                "-ss",
                f"{start}",
                "-i",
                str(path),
                "-frames:v",
                "1",
                "-f",
                "rawvideo",
                "-pix_fmt",
                "gray",
                "-",
            ],
            capture_output=True,
            check=True,
        ).stdout
        return np.frombuffer(raw, np.uint8)

    assert (
        np.abs(
            grab(video).astype(int) - grab(tmp_path / "plain" / "episode_01_9x16.mp4")
        ).mean()
        > 0.5
    )


def test_burn_falls_back_to_srt_without_libass(tmp_path, monkeypatch, capsys):
    import rawi.__main__ as cli

    if not shutil.which("ffmpeg"):
        pytest.skip("FFmpeg absent")
    page = page_with_two_balloons(tmp_path)
    proj = {"version": 3, "rtl": False, "pages": [page]}
    (tmp_path / "projet.json").write_text(
        json.dumps(proj, ensure_ascii=False), encoding="utf-8"
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cli, "can_burn_subtitles", lambda: False)
    args = [
        "rendre",
        "projet.json",
        "--apercu",
        "--fps",
        "10",
        "--sous-titres",
        "incrustes",
    ]
    assert main(args) in (None, 0)
    assert "libass" in capsys.readouterr().err
    assert (tmp_path / "videos" / "episode_01_9x16.srt").is_file()
