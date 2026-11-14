"""Measure panel detection against hand-written ground truth (development tool).

    python -m rawi.evaluate qahwati goldorak qahwati_bubbles qahwati_text [--controle dossier]

Ground truth lives in tests/golden/<set>_expected.json, or next to the private pages in
tests/fixtures/<folder>/<set>_expected.json when it reproduces their content (the text of
the balloons). Page images are local fixtures (tests/fixtures/<set>/, or the "fixtures"
folder named in the truth file), never in git.
A truth file measures panels by default, or bubbles with "what": "bubbles". Matching is
greedy on IoU >= MIN_IOU (or the file's "min_iou"); optional
truth panels (unframed decorations, titles) are neither required nor counted as extra.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import re
import sys
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from itertools import pairwise
from pathlib import Path

import cv2

from .analyze import analyze
from .sources import pdf_to_images

TESTS = Path(__file__).resolve().parents[1] / "tests"
MIN_IOU = 0.6
Box = list[int]


def truth_path(name: str) -> Path | None:
    """The truth file of a set: public (tests/golden) or private (next to the pages)."""
    public = TESTS / "golden" / f"{name}_expected.json"
    if public.is_file():
        return public
    private = sorted((TESTS / "fixtures").glob(f"*/{name}_expected.json"))
    return private[0] if private else None


def iou(a: Box, b: Box) -> float:
    ix = max(0, min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0]))
    iy = max(0, min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = a[2] * a[3] + b[2] * b[3] - inter
    return inter / union if union else 0.0


@dataclass
class PageScore:
    page: str
    required: int
    found: int
    matched_required: int
    extra: int  # found panels matching nothing
    order_pairs: int
    order_ok: int
    pairs: list[tuple[int, int]] = field(
        default_factory=list
    )  # (found index, truth index)

    @property
    def recall(self) -> float:
        return self.matched_required / self.required if self.required else 1.0

    @property
    def precision(self) -> float:
        counted = self.found - (
            len(self.pairs) - self.matched_required
        )  # optional matches are neutral
        return (counted - self.extra) / counted if counted else 1.0

    @property
    def order(self) -> float:
        return self.order_ok / self.order_pairs if self.order_pairs else 1.0


def score_page(
    page: str, found: list[Box], truth: list[dict], min_iou: float = MIN_IOU
) -> PageScore:
    candidates = sorted(
        (
            (iou(f, t["box"]), i, j)
            for i, f in enumerate(found)
            for j, t in enumerate(truth)
        ),
        reverse=True,
    )
    used_f, used_t, pairs = set(), set(), []
    for value, i, j in candidates:
        if value < min_iou:
            break
        if i not in used_f and j not in used_t:
            used_f.add(i)
            used_t.add(j)
            pairs.append((i, j))
    pairs.sort()
    truth_order = [j for _, j in pairs]
    ok = sum(1 for a, b in pairwise(truth_order) if a < b)
    return PageScore(
        page=page,
        required=sum(1 for t in truth if not t.get("optional")),
        found=len(found),
        matched_required=sum(1 for _, j in pairs if not truth[j].get("optional")),
        extra=len(found) - len(pairs),
        order_pairs=max(len(pairs) - 1, 0),
        order_ok=ok,
        pairs=pairs,
    )


def load_truth(name: str) -> dict:
    data = json.loads(
        (TESTS / "golden" / f"{name}_expected.json").read_text(encoding="utf-8")
    )
    pages = {}
    for key, spec in data["pages"].items():
        panels = spec.get("panels") or [{"box": b} for b in spec["boxes"]]
        pages[key] = panels
    return {
        "rtl": data.get("rtl", False),
        "source": data.get("source"),
        "fixtures": data.get("fixtures", name),
        "what": data.get("what", "panels"),
        "min_iou": data.get("min_iou", MIN_IOU),
        "pages": pages,
    }


def page_images(name: str, truth: dict) -> dict[str, Path] | None:
    """Map truth page keys to local image files; None if the private fixtures are absent."""
    folder = TESTS / "fixtures" / truth["fixtures"]
    if not folder.is_dir():
        return None
    if truth["source"]:  # a PDF: pages "1", "2"... rendered into the fixture cache
        pdf = folder / truth["source"]
        if not pdf.is_file():
            return None
        with contextlib.redirect_stdout(io.StringIO()):
            files = pdf_to_images(str(pdf), str(folder / "pages"))
        return {
            str(k): Path(f) for k, f in enumerate(files, 1) if str(k) in truth["pages"]
        }
    return {k: folder / k for k in truth["pages"] if (folder / k).is_file()}


def draw(
    image_path: Path, found: list[Box], truth: list[dict], score: PageScore, out: Path
) -> None:
    img = cv2.imread(str(image_path))
    matched_t = {j for _, j in score.pairs}
    for j, t in enumerate(truth):
        x, y, w, h = t["box"]
        color = (
            (0, 170, 0)
            if j in matched_t
            else (0, 200, 255)
            if t.get("optional")
            else (0, 120, 0)
        )
        cv2.rectangle(
            img, (x, y), (x + w, y + h), color, 10 if j not in matched_t else 5
        )
        cv2.putText(
            img, f"V{j + 1}", (x + 15, y + 70), cv2.FONT_HERSHEY_SIMPLEX, 2.2, color, 6
        )
    matched_f = {i for i, _ in score.pairs}
    for i, (x, y, w, h) in enumerate(found):
        color = (0, 0, 230) if i in matched_f else (230, 0, 230)
        cv2.rectangle(img, (x + 8, y + 8), (x + w - 8, y + h - 8), color, 4)
        cv2.putText(
            img,
            f"T{i + 1}",
            (x + w - 140, y + h - 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            2.2,
            color,
            6,
        )
    out.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out), img, [cv2.IMWRITE_JPEG_QUALITY, 85])


def evaluate(
    name: str, controle: Path | None = None, detector=analyze
) -> list[PageScore] | None:
    truth = load_truth(name)
    images = page_images(name, truth)
    if images is None:
        return None
    scores = []
    for key, path in images.items():
        page = detector(str(path), rtl=truth["rtl"])
        items = page["panels"]
        if truth["what"] == "bubbles":
            items = [b for p in page["panels"] for b in p["bubbles"]]
        found = [[p["x"], p["y"], p["w"], p["h"]] for p in items]
        s = score_page(key, found, truth["pages"][key], truth["min_iou"])
        scores.append(s)
        if controle:
            draw(
                path,
                found,
                truth["pages"][key],
                s,
                controle / name / f"{Path(key).stem}.jpg",
            )
    return scores


def totals(scores: list[PageScore]) -> dict[str, float]:
    req = sum(s.required for s in scores)
    counted = sum(s.found - (len(s.pairs) - s.matched_required) for s in scores)
    pairs = sum(s.order_pairs for s in scores)
    return {
        "recall": sum(s.matched_required for s in scores) / req if req else 1.0,
        "precision": (counted - sum(s.extra for s in scores)) / counted
        if counted
        else 1.0,
        "order": sum(s.order_ok for s in scores) / pairs if pairs else 1.0,
    }


_TASHKEEL = re.compile("[\u064b-\u065f\u0670\u0640]")


def normalise_text(s: str) -> str:
    """Compare readings, not typography: no short vowels, punctuation or alef variants."""
    s = _TASHKEEL.sub("", unicodedata.normalize("NFKC", s))
    s = re.sub("[أإآٱ]", "ا", s).replace("ى", "ي").replace("ة", "ه")
    return " ".join(re.sub(r"[^\w\s%]", " ", s).lower().split())


def _levenshtein(a: str, b: str) -> int:
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def text_scores(reference: str, reading: str) -> tuple[float, float]:
    """(character error rate, fraction of the reference words found) after normalisation."""
    r, h = normalise_text(reference), normalise_text(reading)
    cer = min(_levenshtein(r, h) / max(len(r), 1), 1.0)
    rw, hw = Counter(r.split()), Counter(h.split())
    return cer, sum((rw & hw).values()) / max(sum(rw.values()), 1)


def evaluate_text(name: str, page_reader) -> dict | None:
    """Read every page with ``page_reader(path) -> page`` and compare balloon texts.

    A reference balloon matched to no detected balloon counts as fully wrong (CER 1).
    Returns None when the (private) truth file or the pages are absent.
    """
    path = truth_path(name)
    if path is None:
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    folder = TESTS / "fixtures" / data.get("fixtures", name)
    if not folder.is_dir():
        return None
    cers, words, rows = [], [], []
    for page_name, refs in data["pages"].items():
        page = page_reader(str(folder / page_name))
        found = [b for p in page["panels"] for b in p["bubbles"]]
        for ref in refs:
            best = max(
                found,
                key=lambda b: iou([b["x"], b["y"], b["w"], b["h"]], ref["box"]),
                default=None,
            )
            matched = (
                best is not None
                and iou([best["x"], best["y"], best["w"], best["h"]], ref["box"]) >= 0.5
            )
            reading = best.get("text", "") if matched and best is not None else ""
            cer, w = text_scores(ref["text"], reading) if matched else (1.0, 0.0)
            cers.append(cer)
            words.append(w)
            rows.append((page_name, ref["text"], reading, cer))
    return {
        "cer": sum(cers) / len(cers),
        "words": sum(words) / len(words),
        "rows": rows,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="python -m rawi.evaluate", description="Mesurer la détection des cases."
    )
    ap.add_argument("sets", nargs="+", help="jeux de vérité : qahwati, goldorak…")
    ap.add_argument(
        "--controle",
        type=Path,
        help="dossier où dessiner vérité (vert) et trouvé (rouge)",
    )
    a = ap.parse_args(argv)
    for name in a.sets:
        if name.endswith("_text"):
            from embedkit.tasks import TextRecognizer

            from .analyze import analyze
            from .text import read_page

            rec = TextRecognizer.load()

            def reader(path, rec=rec):
                page = analyze(path)
                read_page(page, rec)
                return page

            res = evaluate_text(name, reader)
            if res is None:
                print(f"{name} : planches absentes (fixtures locales), ignoré.")
                continue
            print(
                f"\n== {name} ==  erreurs par caractère {res['cer']:.1%}, mots retrouvés {res['words']:.1%}"
            )
            continue
        scores = evaluate(name, a.controle)
        if scores is None:
            print(f"{name} : planches absentes (fixtures locales), ignoré.")
            continue
        print(f"\n== {name} ==")
        print(
            "page        cases vraies  trouvées  justes  en trop   rappel  précision  ordre"
        )
        for s in scores:
            print(
                f"{s.page:<12}{s.required:>12}{s.found:>10}{s.matched_required:>8}{s.extra:>9}"
                f"{s.recall:>9.0%}{s.precision:>11.0%}{s.order:>7.0%}"
            )
        t = totals(scores)
        print(
            f"{'TOTAL':<12}{'':>39}{t['recall']:>9.0%}{t['precision']:>11.0%}{t['order']:>7.0%}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
