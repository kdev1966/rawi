import sys
from p3_gutters_any_angle import *  # noqa: F403
import cv2, numpy as np
from rawi import analyze as v01
from rawi.evaluate import evaluate, totals

def detect4(path, rtl=False, old_ext=True, filt=True):
    full = cv2.imread(path); H, W = full.shape[:2]; s = WORK / max(H, W)
    img = cv2.resize(full, (int(W*s), int(H*s)), interpolation=cv2.INTER_AREA); h, w = img.shape[:2]
    white = v01._white_mask(full); go = v01._gutter_mask(white)
    if old_ext: go = v01._extend_gutters(go, white)
    g = cv2.resize(go, (w, h), interpolation=cv2.INTER_NEAREST)
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB).astype(np.int16)
    paper = cv2.morphologyEx(paper_mask(lab), cv2.MORPH_OPEN, np.ones((2,2),np.uint8))
    n, labels, st, _ = cv2.connectedComponentsWithStats(paper, 8); m = max(3, int(0.02*min(h,w)))
    gn = np.zeros_like(paper)
    for i in range(1, n):
        x, y, bw, bh, a = st[i]
        if x <= m or y <= m or x+bw >= w-m or y+bh >= h-m: gn[labels == i] = 1
    bright = cv2.dilate((lab[...,0] > 200).astype(np.uint8), np.ones((5,5),np.uint8))
    g |= extend(gn, bright, thin(gn), int(0.04*max(h,w)), int(0.6*max(h,w)))
    content = 1 - g; k = max(3, int(0.012*max(h,w)))
    content = cv2.morphologyEx(content, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(k,k)))
    n, labels, st, _ = cv2.connectedComponentsWithStats(content, 8); panels=[]
    for i in range(1, n):
        x, y, bw, bh, a = st[i]
        if a < 0.012*h*w or min(bw,bh) < 0.05*min(h,w): continue
        if filt and a < 0.03*h*w:
            comp = labels[y:y+bh, x:x+bw] == i
            if a / (bw*bh) < 0.45 or np.mean(lab[y:y+bh, x:x+bw, 0][comp] > 200) > 0.6: continue
        panels.append({"x":int(x/s),"y":int(y/s),"w":int(bw/s),"h":int(bh/s)})
    return {"panels": _reading_order(panels, rtl)}

if __name__ == "__main__":
    for label, kw in [("A union, old ext", dict(filt=False)), ("B union, old no-ext", dict(old_ext=False, filt=False)), ("C = B + filter", dict(old_ext=False)), ("D = A + filter", {})]:
        res=[]
        for name in ("qahwati","goldorak"):
            sc=evaluate(name, detector=lambda p, rtl=False: detect4(p, rtl, **kw)); t=totals(sc)
            res.append(f"{name[:4]} R={t['recall']:.0%} P={t['precision']:.0%} O={t['order']:.0%} [" + " ".join(f"{x.matched_required}/{x.required}+{x.extra}" for x in sc) + "]")
        print(f"{label:22}", " | ".join(res))
