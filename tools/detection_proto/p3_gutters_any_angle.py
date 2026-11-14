"""Prototype 3: global paper colour, border-connected gutters, dead-end extension at any angle."""
import math, sys
import cv2
import numpy as np
from rawi.analyze import _reading_order
from rawi.evaluate import evaluate, totals

TOL = float(sys.argv[1]) if len(sys.argv) > 1 else 40
BRIGHT = float(sys.argv[2]) if len(sys.argv) > 2 else 0.6
WORK = 2000

def paper_mask(lab):
    L, a, b = lab[..., 0], lab[..., 1] - 128, lab[..., 2] - 128
    chroma = np.sqrt(a.astype(np.int32) ** 2 + b.astype(np.int32) ** 2)
    cand = (chroma < 25) & (L >= np.percentile(L, 75))
    ref = np.median(lab[cand], axis=0) if cand.sum() > 500 else np.array([250, 128, 128])
    return (np.sqrt(((lab - ref) ** 2).sum(axis=2)) < TOL).astype(np.uint8)

def thin(mask):
    """Zhang-Suen thinning (NumPy)."""
    img = (mask > 0).astype(np.uint8)
    img = np.pad(img, 1)
    changed = True
    while changed:
        changed = False
        for step in (0, 1):
            P = [np.roll(np.roll(img, -dy, 0), -dx, 1) for dy, dx in ((-1,0),(-1,1),(0,1),(1,1),(1,0),(1,-1),(0,-1),(-1,-1))]
            B = sum(P)
            A = sum(((P[i] == 0) & (P[(i + 1) % 8] == 1)).astype(np.uint8) for i in range(8))
            if step == 0:
                c = (P[0] * P[2] * P[4] == 0) & (P[2] * P[4] * P[6] == 0)
            else:
                c = (P[0] * P[2] * P[6] == 0) & (P[0] * P[4] * P[6] == 0)
            rm = (img == 1) & (B >= 2) & (B <= 6) & (A == 1) & c
            if rm.any():
                img[rm] = 0
                changed = True
    return img[1:-1, 1:-1]

NB = [(-1,-1),(-1,0),(-1,1),(0,-1),(0,1),(1,-1),(1,0),(1,1)]

def endpoints_with_direction(skel, min_len):
    h, w = skel.shape
    k = np.ones((3, 3), np.uint8)
    nb = cv2.filter2D(skel, -1, k) - skel
    ends = np.argwhere((skel == 1) & (nb == 1))
    out = []
    for y, x in ends:
        path = [(y, x)]; prev = None; cy, cx = y, x
        while len(path) < min_len:
            nxt = [(cy+dy, cx+dx) for dy, dx in NB if 0 <= cy+dy < h and 0 <= cx+dx < w and skel[cy+dy, cx+dx] and (cy+dy, cx+dx) != prev and (cy+dy, cx+dx) not in path[-3:]]
            if len(nxt) != 1:
                break
            prev = (cy, cx); cy, cx = nxt[0]; path.append((cy, cx))
        if len(path) < min_len:
            continue  # short spur or junction close by: not a gutter dead end
        dy, dx = y - path[-1][0], x - path[-1][1]
        n = math.hypot(dx, dy)
        out.append((x, y, dx / n, dy / n))
    return out

def extend(gutter, bright, skel, min_len, max_len):
    h, w = gutter.shape
    out = gutter.copy()
    for x, y, ux, uy in endpoints_with_direction(skel, min_len):
        px, py = float(x), float(y)
        # leave the gutter
        steps = 0
        while 0 <= int(px) < w and 0 <= int(py) < h and gutter[int(py), int(px)] and steps < 30:
            px += ux; py += uy; steps += 1
        start = (int(px), int(py)); n = 0; hit = False
        while n < max_len:
            ix, iy = int(round(px)), int(round(py))
            if not (0 <= ix < w and 0 <= iy < h) or gutter[iy, ix]:
                hit = True; break
            px += ux; py += uy; n += 1
        if not hit or n < 2:
            continue
        probe = np.zeros_like(gutter); cv2.line(probe, start, (int(px), int(py)), 1, 1)
        frac = float((probe & bright).sum()) / max(int(probe.sum()), 1)
        if frac >= BRIGHT:
            cv2.line(out, start, (int(px), int(py)), 1, 3)
    return out

def detect(path, rtl=False):
    full = cv2.imread(path)
    H, W = full.shape[:2]
    s = WORK / max(H, W)
    img = cv2.resize(full, (int(W * s), int(H * s)), interpolation=cv2.INTER_AREA)
    h, w = img.shape[:2]
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB).astype(np.int16)
    paper = cv2.morphologyEx(paper_mask(lab), cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
    n, labels, st, _ = cv2.connectedComponentsWithStats(paper, 8)
    m = max(3, int(0.02 * min(h, w)))
    gutter = np.zeros_like(paper)
    for i in range(1, n):
        x, y, bw, bh, a = st[i]
        if x <= m or y <= m or x + bw >= w - m or y + bh >= h - m:
            gutter[labels == i] = 1
    bright = cv2.dilate((lab[..., 0] > 200).astype(np.uint8), np.ones((5, 5), np.uint8))
    skel = thin(gutter)
    gutter = extend(gutter, bright, skel, min_len=int(0.04 * max(h, w)), max_len=int(0.6 * max(h, w)))
    content = 1 - gutter
    k = max(3, int(0.012 * max(h, w)))
    content = cv2.morphologyEx(content, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k)))
    n, labels, st, _ = cv2.connectedComponentsWithStats(content, 8)
    panels = []
    for i in range(1, n):
        x, y, bw, bh, a = st[i]
        if a < 0.012 * h * w or min(bw, bh) < 0.05 * min(h, w):
            continue
        panels.append({"x": int(x / s), "y": int(y / s), "w": int(bw / s), "h": int(bh / s)})
    return {"panels": _reading_order(panels, rtl)}

if __name__ == "__main__":
    for name in ("qahwati", "goldorak"):
        sc = evaluate(name, detector=detect)
        t = totals(sc)
        per = " ".join(f"{x.page[:9]}:{x.matched_required}/{x.required}+{x.extra}" for x in sc)
        print(f"{name:9} R={t['recall']:.0%} P={t['precision']:.0%} O={t['order']:.0%} | {per}")
