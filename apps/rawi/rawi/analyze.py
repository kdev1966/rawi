"""Analyse d'une planche : cases, ordre de lecture, bulles.
Dépendances : numpy + OpenCV uniquement (tourne sur CPU, Mac Intel OK)."""

import math

import cv2
import numpy as np

from . import panels as panel_detection

DETECTIONS = ("nouvelle", "v01")  # nouvelle = v0.2 method (rawi.panels), v01 = original


def _white_mask(img):
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    return ((hsv[..., 2] > 215) & (hsv[..., 1] < 45)).astype(np.uint8)


def _gutter_mask(white, span=0.4):
    """Gouttières = zones blanches qui touchent le bord de la page et la traversent largement."""
    h, w = white.shape
    n, lab, st, _ = cv2.connectedComponentsWithStats(white, 8)
    g = np.zeros_like(white)
    for i in range(1, n):
        x, y, bw, bh, _a = st[i]
        touches = x <= 3 or y <= 3 or x + bw >= w - 3 or y + bh >= h - 3
        if touches and (bw > span * w or bh > span * h):
            g[lab == i] = 1
    return g


def _extend_gutters(g, white):
    """Prolonge les gouttières interrompues (bulle qui déborde sur la gouttière)."""
    h, w = g.shape
    blobs = cv2.morphologyEx(g, cv2.MORPH_OPEN, np.ones((21, 21), np.uint8))
    thin = cv2.subtract(g, blobs)
    edges = cv2.Canny(thin * 255, 50, 150)
    lines = cv2.HoughLinesP(edges, 1, np.pi / 360, 40, minLineLength=50, maxLineGap=4)
    out = g.copy()
    white_d = cv2.dilate(white, np.ones((7, 7), np.uint8))
    if lines is None:
        return out
    max_gap = int(0.6 * max(h, w))
    for x1, y1, x2, y2 in lines.reshape(-1, 4).tolist():
        dx, dy = x2 - x1, y2 - y1
        L = math.hypot(dx, dy)
        ang = abs(math.degrees(math.atan2(dy, dx))) % 180
        if not (ang < 20 or ang > 160 or 70 < ang < 110):
            continue  # on ne garde que les gouttières ~horizontales / ~verticales
        ux, uy = dx / L, dy / L
        for sx, sy, sgn in ((x2, y2, 1), (x1, y1, -1)):
            px, py = float(sx), float(sy)
            # sortir de la gouttière existante
            steps = 0
            while (
                0 <= int(px) < w
                and 0 <= int(py) < h
                and g[int(py), int(px)]
                and steps < 40
            ):
                px += sgn * ux
                py += sgn * uy
                steps += 1
            start = (int(px), int(py))
            gap = 0
            hit = False
            while gap < max_gap:
                ix, iy = int(round(px)), int(round(py))
                if not (0 <= ix < w and 0 <= iy < h):
                    hit = True
                    break
                if g[iy, ix]:
                    hit = True
                    break
                px += sgn * ux
                py += sgn * uy
                gap += 1
            if hit and gap > 2:
                end = (int(px), int(py))
                if gap > 25:
                    # n'accepter que si le prolongement passe surtout sous des bulles blanches
                    probe = np.zeros_like(g)
                    cv2.line(probe, start, end, 1, 1)
                    frac = float((probe & white_d).sum()) / max(int(probe.sum()), 1)
                    if frac < 0.6:
                        continue
                cv2.line(out, start, end, 1, 5)
    return out


def _merge_slivers(panels):
    """Fusionne les petits morceaux de case dont la boîte chevauche fortement une voisine."""

    def area(p):
        return p["w"] * p["h"]

    changed = True
    while changed:
        changed = False
        panels.sort(key=area)
        for i, a in enumerate(panels):
            for b in panels[i + 1 :]:
                ix = min(a["x"] + a["w"], b["x"] + b["w"]) - max(a["x"], b["x"])
                iy = min(a["y"] + a["h"], b["y"] + b["h"]) - max(a["y"], b["y"])
                if ix > 0 and iy > 0 and ix * iy > 0.45 * area(a):
                    x0, y0 = min(a["x"], b["x"]), min(a["y"], b["y"])
                    x1 = max(a["x"] + a["w"], b["x"] + b["w"])
                    y1 = max(a["y"] + a["h"], b["y"] + b["h"])
                    b.update(x=x0, y=y0, w=x1 - x0, h=y1 - y0)
                    panels.remove(a)
                    changed = True
                    break
            if changed:
                break
    return panels


def _reading_order(panels, rtl=False):
    """Regroupe les cases en rangées puis trie (droite → gauche si rtl)."""
    rows = []
    for p in sorted(panels, key=lambda p: p["y"]):
        cy0, cy1 = p["y"], p["y"] + p["h"]
        for row in rows:
            ry0, ry1 = row["y0"], row["y1"]
            overlap = min(cy1, ry1) - max(cy0, ry0)
            if overlap > 0.5 * min(cy1 - cy0, ry1 - ry0):
                row["items"].append(p)
                row["y0"] = min(ry0, cy0)
                row["y1"] = max(ry1, cy1)
                break
        else:
            rows.append({"y0": cy0, "y1": cy1, "items": [p]})
    ordered = []
    for row in sorted(rows, key=lambda r: r["y0"]):
        ordered += sorted(row["items"], key=lambda p: p["x"] + p["w"] / 2, reverse=rtl)
    return ordered


def _bubbles(img, white, gutter, panel):
    """Bulles = zones blanches fermées contenant du texte sombre."""
    H, W = white.shape
    x, y, w, h = panel["x"], panel["y"], panel["w"], panel["h"]
    sub = (white[y : y + h, x : x + w] & (1 - gutter[y : y + h, x : x + w])).astype(
        np.uint8
    )
    sub = cv2.morphologyEx(sub, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    gray = cv2.cvtColor(img[y : y + h, x : x + w], cv2.COLOR_BGR2GRAY)
    cnts, _ = cv2.findContours(sub, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    res = []
    for c in cnts:
        bx, by, bw, bh = cv2.boundingRect(c)
        if bw * bh < 0.004 * H * W or bw < 40 or bh < 30:
            continue
        fill = np.zeros_like(sub)
        cv2.drawContours(fill, [c], -1, 1, -1)
        area = int(fill.sum())
        solidity = area / max(cv2.contourArea(cv2.convexHull(c)), 1)
        dark = int(((gray < 100) & (fill > 0)).sum())
        ratio = dark / max(area, 1)
        if solidity > 0.75 and 0.03 < ratio < 0.45:
            res.append({"x": x + bx, "y": y + by, "w": bw, "h": bh, "text_px": dark})
    return res


def reading_time(bubbles):
    """Durée d'affichage d'une case (s) estimée d'après la quantité de texte."""
    text = sum(b["text_px"] for b in bubbles)
    return round(min(max(1.8 + text / 2600.0, 2.2), 7.5), 2)


def _panels_v01(gutter, min_panel):
    H, W = gutter.shape
    gd = cv2.dilate(gutter, np.ones((3, 3), np.uint8))
    n, lab, st, _ = cv2.connectedComponentsWithStats((1 - gd).astype(np.uint8), 4)
    panels = []
    for i in range(1, n):
        x, y, w, h, a = (int(v) for v in st[i])
        if a > min_panel * H * W:
            panels.append({"x": x, "y": y, "w": w, "h": h})
    return _merge_slivers(panels)


def analyze(path, rtl=False, min_panel=0.015, detection="nouvelle"):
    if detection not in DETECTIONS:
        raise ValueError(f"detection must be one of {DETECTIONS}")
    img = cv2.imread(path)
    if img is None:
        raise FileNotFoundError(path)
    H, W = img.shape[:2]
    white = _white_mask(img)
    gutter = _extend_gutters(_gutter_mask(white), white)
    if detection == "v01":
        panels = _panels_v01(gutter, min_panel)
    else:
        panels = panel_detection.detect(img, gutter)
    if not panels:  # page sans gouttière : une seule case
        panels = [{"x": 0, "y": 0, "w": W, "h": H}]
    panels = _reading_order(panels, rtl)
    for i, p in enumerate(panels):
        p["id"] = i + 1
        p["bubbles"] = _bubbles(img, white, gutter, p)
        p["duration"] = reading_time(p["bubbles"])
    return {"image": path, "width": W, "height": H, "rtl": rtl, "panels": panels}


def draw_debug(project, out_path):
    img = cv2.imread(project["image"])
    for p in project["panels"]:
        cv2.rectangle(
            img, (p["x"], p["y"]), (p["x"] + p["w"], p["y"] + p["h"]), (0, 0, 255), 4
        )
        for b in p["bubbles"]:
            cv2.rectangle(
                img,
                (b["x"], b["y"]),
                (b["x"] + b["w"], b["y"] + b["h"]),
                (255, 140, 0),
                3,
            )
        c = (p["x"] + 30, p["y"] + 55)
        cv2.circle(img, (c[0] + 12, c[1] - 15), 34, (0, 0, 255), -1)
        cv2.putText(
            img,
            str(p["id"]),
            (c[0] - 5, c[1]),
            cv2.FONT_HERSHEY_SIMPLEX,
            1.4,
            (255, 255, 255),
            4,
        )
    cv2.imwrite(out_path, img)
