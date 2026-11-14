"""Reading time: how long each balloon and each panel stay on screen.

One place for the rule, shared by the analysis (panel durations), the text reading (which
refines them once the text is known) and the renderer (when each balloon appears), so the
video and its subtitles follow the same clock.
"""

from __future__ import annotations

# comfortable subtitle reading speed (Arabic is read a bit slower)
CHARS_PER_SECOND = 14.0
# s, shortest time a balloon stays the newest one on screen
READ_MIN = 1.2
# dark pixels read per second, when the text is unknown (v0.1 rule)
INK_PER_SECOND = 2600.0
# s into the panel before the first balloon appears
FIRST_BUBBLE = 0.25
# s after the last balloon's reading time before the camera moves on
READ_TAIL = 0.4
# s, bounds of a panel's duration
PANEL_MIN, PANEL_MAX = 2.2, 12.0
# s, closest two balloons may appear when a panel is too short for its text
GAP_MIN = 0.3


def bubble_read_time(bubble: dict) -> float:
    """Seconds needed to read one balloon: from its text, or from its ink when unread."""
    text = "".join((bubble.get("text") or "").split())
    if text:
        return max(READ_MIN, len(text) / CHARS_PER_SECOND)
    return max(READ_MIN, float(bubble.get("text_px", 0)) / INK_PER_SECOND)


def panel_duration(bubbles: list[dict]) -> float:
    """Seconds a panel stays on screen: the reading time of all its balloons."""
    if not bubbles:
        return PANEL_MIN
    total = FIRST_BUBBLE + sum(bubble_read_time(b) for b in bubbles) + READ_TAIL
    return round(min(max(total, PANEL_MIN), PANEL_MAX), 2)


def bubble_starts(bubbles: list[dict], hold: float) -> list[float]:
    """Seconds into a panel's hold at which each balloon (in reading order) appears.

    Each balloon waits for the previous one to be read; when the hold is too short (a
    duration set by hand, or capped), the gaps shrink proportionally, down to GAP_MIN.
    """
    if not bubbles:
        return []
    gaps = [bubble_read_time(b) for b in bubbles[:-1]]
    room = hold - FIRST_BUBBLE - bubble_read_time(bubbles[-1]) * 0.5
    if gaps and sum(gaps) > room:
        factor = max(room, 0.0) / sum(gaps)
        gaps = [max(g * factor, GAP_MIN) for g in gaps]
    starts = [FIRST_BUBBLE]
    for g in gaps:
        starts.append(starts[-1] + g)
    return starts
