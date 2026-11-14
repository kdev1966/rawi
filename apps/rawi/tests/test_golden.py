"""Golden tests on the private pages (local only; skipped where the pages are absent).

- Qahwati, page by page, with the v0.1 detection (kept as --detection v01).
- Floors on recall and precision for both detections on Qahwati and Goldorak: any change
  that lowers a score fails here (raise the floors when a change improves them).

Expected panels are ground truth, not the current output: pages with a known detection
error are strict xfails, so the test turns red the day the error is fixed (remove the
"known_issue" then).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from rawi import evaluate as ev
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
    page = analyze(str(QAHWATI / name), rtl=EXPECTED["rtl"], detection="v01")
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


# (set, detection) -> (recall, precision) measured on 2026-11-14 with rawi.evaluate
FLOORS = {
    ("qahwati", "v01"): (0.93, 0.91),
    ("goldorak", "v01"): (0.39, 0.74),
    ("qahwati", "nouvelle"): (0.91, 0.85),
    ("goldorak", "nouvelle"): (0.85, 0.90),
    ("qahwati_bubbles", "nouvelle"): (0.89, 0.91),
}


@pytest.mark.parametrize(("name", "detection"), list(FLOORS), ids=lambda v: str(v))
def test_detection_scores_do_not_regress(name, detection):
    scores = ev.evaluate(
        name, detector=lambda p, rtl=False: analyze(p, rtl=rtl, detection=detection)
    )
    if scores is None:
        pytest.skip(f"planches {name} absentes (privées, hors git)")
    t = ev.totals(scores)
    recall, precision = FLOORS[(name, detection)]
    assert t["recall"] >= recall - 0.005, f"rappel {t['recall']:.1%} < {recall:.0%}"
    assert t["precision"] >= precision - 0.005, (
        f"précision {t['precision']:.1%} < {precision:.0%}"
    )
