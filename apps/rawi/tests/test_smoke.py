"""Smoke test: analyse + render a synthetic page in preview mode (runs in CI)."""

from __future__ import annotations

import json
import shutil
import subprocess

import cv2
import pytest
from rawi.__main__ import main

FFMPEG = shutil.which("ffmpeg")
FFPROBE = shutil.which("ffprobe")


@pytest.mark.skipif(not (FFMPEG and FFPROBE), reason="FFmpeg absent")
def test_auto_preview_renders_a_video(tmp_path, monkeypatch, comic_page):
    monkeypatch.chdir(tmp_path)
    cv2.imwrite("page.png", comic_page(600, 800))
    assert main(["auto", "page.png", "--apercu", "--fps", "10"]) in (None, 0)

    projet = json.loads((tmp_path / "projet.json").read_text(encoding="utf-8"))
    panels = projet["pages"][0]["panels"]
    assert len(panels) == 4
    video = tmp_path / "videos" / "episode_01_9x16.mp4"
    assert video.is_file()

    probe = subprocess.run(
        [
            FFPROBE,
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height:format=duration",
            "-of",
            "json",
            str(video),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    info = json.loads(probe.stdout)
    stream = info["streams"][0]
    assert (stream["width"], stream["height"]) == (540, 960)  # 9:16 at half resolution
    expected = sum(p["duration"] for p in panels)
    assert float(info["format"]["duration"]) >= expected  # every panel is shown
