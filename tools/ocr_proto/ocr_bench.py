"""OCR bench on the 46 Qahwati balloons (reference crops), engine-agnostic."""

import json
import re
import subprocess
import sys
import tempfile
import time
import unicodedata
from collections import Counter
from pathlib import Path

import cv2
import numpy as np

ROOT = Path("/Users/kdev66/Desktop/Tools/film/rawi/apps/rawi/tests")
TRUTH = json.loads((ROOT / "fixtures/qahwati/qahwati_text_expected.json").read_text(encoding="utf-8"))

TASHKEEL = re.compile("[ً-ٰٟـ]")


def normalise(s: str) -> str:
    s = unicodedata.normalize("NFKC", s)
    s = TASHKEEL.sub("", s)
    s = re.sub("[أإآٱ]", "ا", s).replace("ى", "ي").replace("ة", "ه")
    s = re.sub(r"[^\w\s%]", " ", s).lower()
    s = s.replace("ـ", "")
    return " ".join(s.split())


def lev(a: str, b: str) -> int:
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def score(ref: str, hyp: str) -> tuple[float, float]:
    r, h = normalise(ref), normalise(hyp)
    cer = lev(r, h) / max(len(r), 1)
    rw, hw = Counter(r.split()), Counter(h.split())
    words = sum((rw & hw).values()) / max(sum(rw.values()), 1)
    return cer, words


def crops():
    for page, items in TRUTH["pages"].items():
        img = cv2.imread(str(ROOT / "fixtures" / TRUTH["fixtures"] / page))
        for k, it in enumerate(items):
            x, y, w, h = it["box"]
            yield f"{page[:-4]}#{k}", img[y : y + h, x : x + w], it["text"]


def tesseract(variant: str, psm: int, binarize: bool, scale: float):
    tessdata = f"/private/tmp/claude-502/-Users-kdev66-Desktop-Tools-film-rawi/513729cf-e3f9-43a5-9342-5d5bcb1bf968/scratchpad/tessdata/{variant}"

    def run(crop):
        g = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        if scale != 1:
            g = cv2.resize(g, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        if binarize:
            g = cv2.threshold(g, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
        with tempfile.NamedTemporaryFile(suffix=".png") as f:
            cv2.imwrite(f.name, g)
            out = subprocess.run(
                ["tesseract", f.name, "-", "-l", "ara+fra+eng", "--psm", str(psm), "--tessdata-dir", tessdata],
                capture_output=True, text=True,
            )
        return out.stdout.strip()

    return run


def bench(name, engine, show=0):
    cers, words, times, rows = [], [], [], []
    for key, crop, ref in crops():
        t = time.perf_counter()
        hyp = engine(crop)
        times.append(time.perf_counter() - t)
        c, w = score(ref, hyp)
        cers.append(c)
        words.append(w)
        rows.append((key, c, ref, hyp))
    print(f"{name:34} CER={np.mean(cers):.1%} (médiane {np.median(cers):.1%})  mots={np.mean(words):.1%}  {np.mean(times):.2f} s/bulle")
    for key, c, ref, hyp in sorted(rows, key=lambda r: -r[1])[:show]:
        print(f"   {key} CER={c:.0%}\n      réf : {ref}\n      lu  : {' / '.join(hyp.splitlines())}")


if __name__ == "__main__":
    for variant in ("best", "fast"):
        for psm in (6, 4):
            for binarize in (False, True):
                bench(f"tesseract {variant} psm{psm} bin={binarize}", tesseract(variant, psm, binarize, 2.0))


def clean_text_image(crop):
    """Black text on white: the balloon's ink only (largest bright region = the interior)."""
    sys.path.insert(0, "/Users/kdev66/Desktop/Tools/film/rawi/apps/rawi")
    from rawi.layers import bubble_ink

    g = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    bright = (g > 200).astype(np.uint8)
    bright = cv2.morphologyEx(bright, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    n, lab, st, _ = cv2.connectedComponentsWithStats(bright, connectivity=8)
    if n < 2:
        return crop
    i = 1 + int(np.argmax(st[1:, cv2.CC_STAT_AREA]))
    comp = (lab == i).astype(np.uint8)
    cs, _ = cv2.findContours(comp, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    interior = np.zeros_like(comp)
    cv2.drawContours(interior, cs, -1, 1, -1)
    ink, _ = bubble_ink(crop, interior)
    out = np.full_like(crop, 255)
    out[ink > 0] = crop[ink > 0]
    return out


def on_clean(engine):
    return lambda crop: engine(clean_text_image(crop))


# ---------------- PaddleOCR (ONNX) ----------------
PADDLE = "/private/tmp/claude-502/-Users-kdev66-Desktop-Tools-film-rawi/513729cf-e3f9-43a5-9342-5d5bcb1bf968/scratchpad/paddle"
_REC = {}
ARABIC_RE = re.compile("[؀-ۿ]")


def rec_model(lang):
    if lang not in _REC:
        import onnxruntime as ort

        chars = [l.rstrip("\n") for l in open(f"{PADDLE}/languages/{lang}/dict.txt", encoding="utf-8")]
        _REC[lang] = (ort.InferenceSession(f"{PADDLE}/languages/{lang}/rec.onnx", providers=["CPUExecutionProvider"]), ["<blank>"] + chars + [" "])
    return _REC[lang]


def recognise(img_gray, lang, reverse_arabic):
    sess, chars = rec_model(lang)
    h, w = img_gray.shape
    nw = max(16, int(round(w * 48 / h)))
    x = cv2.resize(img_gray, (nw, 48), interpolation=cv2.INTER_CUBIC).astype(np.float32) / 255.0
    x = (x - 0.5) / 0.5
    x = np.repeat(x[None, None], 3, axis=1)
    probs = sess.run(None, {"x": x})[0][0]
    idx = probs.argmax(axis=1)
    out, confs, prev = [], [], -1
    for t, i in enumerate(idx):
        if i != prev and i != 0:
            out.append(chars[i] if i < len(chars) else "")
            confs.append(float(probs[t, i]))
        prev = i
    text = "".join(out)
    if lang == "arabic" and reverse_arabic:
        text = pred_reverse(text)
    return text.strip(), (float(np.mean(confs)) if confs else 0.0)


LATIN_RUN = re.compile(r"[a-zA-Z0-9 :*./%+,'’\-]")


def pred_reverse(text):
    """PaddleOCR's rule: reverse the order of runs, keep Latin/digit runs forward."""
    runs, cur = [], ""
    for ch in text:
        if LATIN_RUN.match(ch):
            cur += ch
        else:
            if cur:
                runs.append(cur); cur = ""
            runs.append(ch)
    if cur:
        runs.append(cur)
    return "".join(reversed(runs))


MERGE_REL = 0.25


def split_lines(ink, rel=0.08):
    """Text lines: row bands where the ink is above rel x the busiest row."""
    prof = ink.sum(axis=1).astype(float)
    if prof.max() == 0:
        return []
    on = prof > rel * prof.max()
    lines, start = [], None
    for i, v in enumerate(on):
        if v and start is None:
            start = i
        if not v and start is not None:
            lines.append([start, i]); start = None
    if start is not None:
        lines.append([start, len(on)])
    # thin bands (dots, diacritics alone) join the nearest real line
    def ink_of(r):
        return prof[r[0]:r[1]].sum()
    if len(lines) > 1:
        big = max(ink_of(r) for r in lines)
        kept = [r for r in lines if ink_of(r) >= MERGE_REL * big]
        for r in lines:
            if r in kept:
                continue
            near = min(kept, key=lambda k: min(abs(k[0] - r[1]), abs(r[0] - k[1])))
            near[0], near[1] = min(near[0], r[0]), max(near[1], r[1])
        lines = sorted(kept)
    # grow each band to the neighbouring gaps' middle so diacritics stay with their line
    out = []
    for k, (y0, y1) in enumerate(lines):
        top = (lines[k - 1][1] + y0) // 2 if k else max(0, y0 - (y1 - y0) // 2)
        bottom = (y1 + lines[k + 1][0]) // 2 if k + 1 < len(lines) else min(len(on), y1 + (y1 - y0) // 2)
        out.append([top, bottom])
    return out


def split_runs(profile, min_gap):
    """[(start, end)] of runs where profile > 0, merging gaps shorter than min_gap."""
    on = profile > 0
    runs, start = [], None
    for i, v in enumerate(on):
        if v and start is None:
            start = i
        if not v and start is not None:
            runs.append([start, i]); start = None
    if start is not None:
        runs.append([start, len(on)])
    merged = []
    for r in runs:
        if merged and r[0] - merged[-1][1] < min_gap:
            merged[-1][1] = r[1]
        else:
            merged.append(r)
    return merged


def paddle(mode="line_ar", reverse_arabic=True):
    def run(crop):
        clean = cv2.cvtColor(clean_text_image(crop), cv2.COLOR_BGR2GRAY)
        ink = (clean < 160).astype(np.uint8)
        lines = split_lines(ink)
        out_lines = []
        for y0, y1 in lines:
            if y1 - y0 < 8:
                continue
            band = clean[y0:y1]
            cols = (band < 160).sum(axis=0)
            xs = np.nonzero(cols)[0]
            if len(xs) == 0:
                continue
            band = band[:, max(0, xs[0] - 6) : xs[-1] + 7]
            band = cv2.copyMakeBorder(band, 6, 6, 10, 10, cv2.BORDER_CONSTANT, value=255)
            if mode == "line_ar":
                out_lines.append(recognise(band, "arabic", reverse_arabic)[0])
            elif mode == "line_best":
                a = recognise(band, "arabic", reverse_arabic); l = recognise(band, "latin", reverse_arabic)
                out_lines.append(a[0] if a[1] >= l[1] else l[0])
            else:  # words
                lh = y1 - y0
                wcols = ((band < 160).sum(axis=0) > 0).astype(int)
                words = split_runs(wcols, max(4, int(0.3 * lh)))
                items = []
                for x0, x1 in words:
                    wimg = cv2.copyMakeBorder(band[:, max(0, x0 - 3) : x1 + 3], 0, 0, 8, 8, cv2.BORDER_CONSTANT, value=255)
                    a = recognise(wimg, "arabic", reverse_arabic); l = recognise(wimg, "latin", reverse_arabic)
                    items.append(a[0] if a[1] >= l[1] else l[0])
                arabic = sum(1 for t in items if ARABIC_RE.search(t)) >= len(items) / 2
                out_lines.append(" ".join(reversed(items) if arabic else items))
        return "\n".join(out_lines)

    return run
