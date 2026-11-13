"""Golden tests: panel detection and reading order on the 8 Qahwati pages (local only).

Expected panels are ground truth, not the current output: pages with a known detection
error are strict xfails, so the test turns red the day the error is fixed (remove the
"known_issue" then).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from rawi.analyze import analyze

HERE = Path(__file__).parent
QAHWATI = HERE / "fixtures" / "qahwati"
EXPECTED = json.loads(
    (HERE / "golden" / "qahwati_expected.json").read_text(encoding="utf-8")
)
MIN_IOU = 0.7


def iou(a: list[int], b: list[int]) -> float:
    ax0, ay0, aw, ah = a
    bx0, by0, bw, bh = b
    ix = max(0, min(ax0 + aw, bx0 + bw) - max(ax0, bx0))
    iy = max(0, min(ay0 + ah, by0 + bh) - max(ay0, by0))
    inter = ix * iy
    return inter / (aw * ah + bw * bh - inter)


def _cases():
    for name, spec in EXPECTED["pages"].items():
        marks = (
            [pytest.mark.xfail(strict=True, reason=spec["known_issue"])]
            if "known_issue" in spec
            else []
        )
        yield pytest.param(
            name, spec["boxes"], id=name.removesuffix(".jpg"), marks=marks
        )


@pytest.mark.skipif(
    not QAHWATI.is_dir(), reason="planches Qahwati absentes (privées, hors git)"
)
@pytest.mark.parametrize(("name", "expected"), list(_cases()))
def test_panels_and_order(name, expected):
    page = analyze(str(QAHWATI / name), rtl=EXPECTED["rtl"])
    found = [[p["x"], p["y"], p["w"], p["h"]] for p in page["panels"]]
    assert len(found) == len(expected), (
        f"{len(found)} cases trouvées, {len(expected)} attendues"
    )
    for k, (f, e) in enumerate(zip(found, expected, strict=True), 1):
        assert iou(f, e) >= MIN_IOU, (
            f"case {k} : {f} au lieu de {e} (IoU {iou(f, e):.2f})"
        )


def test_iou():
    assert iou([0, 0, 10, 10], [0, 0, 10, 10]) == 1.0
    assert iou([0, 0, 10, 10], [20, 20, 5, 5]) == 0.0
    assert iou([0, 0, 10, 10], [5, 0, 10, 10]) == pytest.approx(50 / 150)
