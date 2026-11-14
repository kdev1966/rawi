"""Subtitles from the balloons' text: .srt files, and the style used to burn them in.

Each balloon with text becomes one subtitle, shown from the moment its text appears in the
video until the next balloon of the panel appears (rawi.render.bubble_timeline, so the
subtitles follow the rendered frames exactly). The speaker's name printed at the start of a
balloon ("مريم: …") is removed by default: the balloon already shows who speaks.
"""

from __future__ import annotations

import os
import re

from .render import bubble_timeline

# a short name followed by a colon (the OCR sometimes reads it as the Arabic semicolon)
_SPEAKER = re.compile(r"^\s*([^\s:؛!?؟،,.]{1,24})\s*[:؛]\s*(?=\S)")
_ARABIC = re.compile("[\u0600-\u06ff\u0750-\u077f\ufb50-\ufdff\ufe70-\ufeff]")
_LETTER = re.compile(r"[^\W\d_]")
RLM = "\u200f"  # right-to-left mark: sets the base direction of an Arabic subtitle

# libass style for burned subtitles (sizes in libass script units, 288 = picture height)
BURN_STYLE = (
    "FontName=Arial,FontSize=13,Outline=2,Shadow=0,MarginV=24,MarginL=12,MarginR=12"
)


# a first line holding one word, maybe followed by what the OCR made of the colon
_NAME_LINE = re.compile(r"^\s*([^\s:؛!?؟،,.]{1,24})\s*[:؛.]?\s*$")


def speaker_names(pages: list[dict]) -> set[str]:
    """Speaker names of the project.

    A name is printed as "Name:" at the start of a balloon. The OCR often loses the colon,
    so a one-word first line that opens two balloons or more is a name too (a one-off first
    line such as "وبعد؟" is not).
    """
    names: set[str] = set()
    first_words: dict[str, int] = {}
    for page in pages:
        for panel in page["panels"]:
            for b in panel["bubbles"]:
                text = b.get("text") or ""
                m = _SPEAKER.match(text)
                if m:
                    names.add(m.group(1))
                lines = [line for line in text.split("\n") if line.strip()]
                first = _NAME_LINE.match(lines[0]) if len(lines) > 1 else None
                if first:
                    first_words[first.group(1)] = first_words.get(first.group(1), 0) + 1
    return names | {word for word, count in first_words.items() if count >= 2}


def strip_speaker(text: str, known: set[str] | frozenset[str] = frozenset()) -> str:
    """Remove the speaker's name from the start of a balloon's text.

    Removed: "Name:" (or "Name؛", as the OCR sometimes reads the colon), and a first line
    holding only a name known from other balloons ("Name:" seen elsewhere), even when the
    colon was not read. Kept: a vocative ("Name!") and a one-word first line that is not a
    known name ("وبعد؟").
    """
    lines = [line for line in text.split("\n") if line.strip()]
    if not lines:
        return ""
    joined = "\n".join(lines)
    stripped = _SPEAKER.sub("", joined, count=1)
    if stripped != joined:
        return " ".join(stripped.split())
    m = _NAME_LINE.match(lines[0])
    if len(lines) > 1 and m and m.group(1) in known:
        lines = lines[1:]
    return " ".join(" ".join(lines).split())


def cues(
    pages: list[dict],
    fps: int = 30,
    keep_names: bool = False,
    names: set[str] | None = None,
) -> list[tuple[float, float, str]]:
    """(start, end, text) of every subtitle of a video made of ``pages``, in order.

    ``names``: speaker names known in the whole project (default: found in ``pages``).
    """
    known = speaker_names(pages) if names is None else names
    out = []
    offset = 0.0
    for page in pages:
        duration, events = bubble_timeline(page, fps)
        for bubble, start, end in events:
            raw = bubble.get("text") or ""
            text = " ".join(raw.split()) if keep_names else strip_speaker(raw, known)
            if text:
                out.append((offset + start, offset + end, text))
        offset += duration
    return out


def _timestamp(seconds: float) -> str:
    ms = int(round(seconds * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def to_srt(items: list[tuple[float, float, str]]) -> str:
    blocks = []
    for k, (start, end, text) in enumerate(items, 1):
        first = _LETTER.search(text)
        if first and _ARABIC.match(first.group()):
            text = RLM + text  # Arabic-first subtitle: right-to-left base direction
        blocks.append(f"{k}\n{_timestamp(start)} --> {_timestamp(end)}\n{text}\n")
    return "\n".join(blocks)


def write_srt(path: str | os.PathLike, items: list[tuple[float, float, str]]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write(to_srt(items))


def filter_path(path: str | os.PathLike) -> str:
    """A path escaped for FFmpeg's ``subtitles=`` filter option."""
    return (
        str(path)
        .replace("\\", "\\\\")
        .replace(":", "\\:")
        .replace("'", "\\'")
        .replace(",", "\\,")
    )
