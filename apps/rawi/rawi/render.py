"""Rendu motion comic : caméra case par case, projecteur, bulles qui apparaissent à la lecture.
Dépendances : numpy, OpenCV, FFmpeg (binaire)."""

import shutil
import subprocess

import cv2
import numpy as np

from .layers import build_layers
from .project import bubble_reading_order

FORMATS = {"9:16": (1080, 1920), "16:9": (1920, 1080), "1:1": (1080, 1080)}


def ease(t):  # ease-in-out cubique
    t = min(max(t, 0.0), 1.0)
    return 4 * t**3 if t < 0.5 else 1 - (-2 * t + 2) ** 3 / 2


def lerp(a, b, t):
    return tuple(x + (y - x) * t for x, y in zip(a, b, strict=True))


def _background(img, W, H):
    h, w = img.shape[:2]
    s = max(W / w, H / h)
    bg = cv2.resize(img, (int(w * s) + 2, int(h * s) + 2))
    y0, x0 = (bg.shape[0] - H) // 2, (bg.shape[1] - W) // 2
    bg = bg[y0 : y0 + H, x0 : x0 + W]
    bg = cv2.GaussianBlur(bg, (0, 0), 35)
    return (bg * 0.35).astype(np.uint8)


def build_shots(page, transition=0.7, intro=2.0, outro=1.8):
    """Liste de plans : (rect caméra [cx, cy, w, h], durée, case active)."""
    W, H = page["width"], page["height"]
    full = (W / 2, H / 2, W, H)
    shots = [{"rect": full, "hold": intro, "panel": None}]
    for p in page["panels"]:
        # cadre caméra minimum (évite les zooms extrêmes sur les cases étroites)
        rw, rh = max(p["w"], 0.5 * W), max(p["h"], 0.2 * H)
        cx = min(max(p["x"] + p["w"] / 2, rw / 2), W - rw / 2)
        cy = min(max(p["y"] + p["h"] / 2, rh / 2), H - rh / 2)
        r = (cx, cy, rw, rh)
        shots.append({"rect": r, "hold": float(p.get("duration", 3)), "panel": p})
    shots.append({"rect": full, "hold": outro, "panel": None})
    return shots, transition


def _matrix(rect, W, H, zoom=1.0, margin=0.92):
    cx, cy, rw, rh = rect
    s = min(W * margin / rw, H * margin / rh) * zoom
    return np.float32([[s, 0, W / 2 - s * cx], [0, s, H / 2 - s * cy]]), s


POP = 0.45  # s, duration of a bubble's appearance
FIRST_BUBBLE = 0.25  # s into the panel before the first bubble appears
BUBBLE_GAP = 0.9  # s between bubbles, shortened when the panel is short
READ_TAIL = 1.2  # s left after the last bubble appears


def _ease_out_back(t):
    c = 1.7
    t = min(max(t, 0.0), 1.0) - 1
    return 1 + (c + 1) * t**3 + c * t**2


def _draw_popping(frame, sprite, M, t):
    """Draw a bubble appearing: scale 0.85 -> 1.0 with a slight overshoot, fading in."""
    k = 0.85 + 0.15 * _ease_out_back(t)
    fade = min(t / 0.3, 1.0)
    h, w = sprite.alpha.shape
    s = M[0, 0] * k
    cw, ch = max(int(w * s), 2), max(int(h * s), 2)
    img = cv2.resize(sprite.image, (cw, ch), interpolation=cv2.INTER_LINEAR)
    alpha = (
        cv2.resize(sprite.alpha, (cw, ch), interpolation=cv2.INTER_LINEAR)[..., None]
        * fade
    )
    cx = M[0, 0] * (sprite.x + w / 2) + M[0, 2]
    cy = M[1, 1] * (sprite.y + h / 2) + M[1, 2]
    x0, y0 = int(cx - cw / 2), int(cy - ch / 2)
    H, W = frame.shape[:2]
    fx0, fy0, fx1, fy1 = max(x0, 0), max(y0, 0), min(x0 + cw, W), min(y0 + ch, H)
    if fx1 <= fx0 or fy1 <= fy0:
        return
    c = img[fy0 - y0 : fy1 - y0, fx0 - x0 : fx1 - x0].astype(np.float32)
    a = alpha[fy0 - y0 : fy1 - y0, fx0 - x0 : fx1 - x0]
    roi = frame[fy0:fy1, fx0:fx1].astype(np.float32)
    frame[fy0:fy1, fx0:fx1] = (roi * (1 - a) + c * a).astype(np.uint8)


def bubble_schedule(n, hold):
    """Seconds into a panel's hold at which each of its ``n`` bubbles starts to appear."""
    if n == 0:
        return []
    gap = min(BUBBLE_GAP, max((hold - FIRST_BUBBLE - READ_TAIL) / n, 0.3))
    return [FIRST_BUBBLE + k * gap for k in range(n)]


def frames(page, fmt="9:16", fps=30, scale=1.0):
    """Yield the frames of one page: overview, panel by panel, final overview.

    The page is shown without its bubbles; each bubble appears in reading order while the
    camera holds on its panel, then stays visible.
    """
    img = cv2.imread(page["image"])
    W, H = (int(v * scale) // 2 * 2 for v in FORMATS[fmt])
    bg = _background(img, W, H)
    rtl = page.get("rtl", False)
    all_bubbles = [
        {**b, "id": b.get("id") or f"b{i}-{k}"}
        for i, p in enumerate(page["panels"])
        for k, b in enumerate(p["bubbles"])
    ]
    layers = build_layers(img, all_bubbles)
    ids_by_panel = {}
    for i, p in enumerate(page["panels"]):
        ids_by_panel[i] = [
            b.get("id") or f"b{i}-{p['bubbles'].index(b)}"
            for b in _ordered_bubbles(p["bubbles"], rtl)
        ]
    shown: set[str] = set()
    cached = {"key": None, "img": None}

    def current():
        key = frozenset(shown)
        if cached["key"] != key:
            cached["key"], cached["img"] = key, layers.with_bubbles(shown)
        return cached["img"]

    shots, tr = build_shots(page)
    prev = None
    for shot in shots:
        # 1) transition from the previous shot
        if prev is not None:
            n = int(tr * fps)
            for f in range(n):
                t = ease((f + 1) / n)
                rect = lerp(prev["rect"], shot["rect"], t)
                M, _ = _matrix(
                    rect, W, H, zoom=1.0 + 0.05 * (1 - t) * (prev["panel"] is not None)
                )
                yield _compose(current(), bg, M, W, H, None, 0.0)
        # 2) hold: slight zoom in (Ken Burns), spotlight, bubbles appearing
        n = int(shot["hold"] * fps)
        p = shot["panel"]
        ids = ids_by_panel[page["panels"].index(p)] if p is not None else []
        starts = bubble_schedule(len(ids), shot["hold"])
        if p is None and prev is not None:
            shown.update(layers.sprites)  # final overview: the complete page
        for f in range(n):
            t = f / max(n - 1, 1)
            sec = f / fps
            M, _ = _matrix(
                shot["rect"], W, H, zoom=1.0 + 0.05 * ease(t) * (p is not None)
            )
            for bubble_id, start in zip(ids, starts, strict=True):
                if sec >= start + POP:
                    shown.add(bubble_id)
            dim = min(f / (0.35 * fps), 1.0) * 0.6 if p else 0.0
            fr = _compose(current(), bg, M, W, H, p, dim)
            for bubble_id, start in zip(ids, starts, strict=True):
                if start <= sec < start + POP and bubble_id in layers.sprites:
                    _draw_popping(fr, layers.sprites[bubble_id], M, (sec - start) / POP)
            yield fr
        shown.update(i for i in ids if i in layers.sprites)
        prev = shot


def _ordered_bubbles(bubbles, rtl):
    """Bubbles in reading order: the project's explicit ``order`` (v2), else the v0.1 rule."""
    if bubbles and all("order" in b for b in bubbles):
        return sorted(bubbles, key=lambda b: b["order"])
    return bubble_reading_order(bubbles, rtl)


def _compose(img, bg, M, W, H, panel, dim):
    fr = bg.copy()
    cv2.warpAffine(
        img,
        M,
        (W, H),
        dst=fr,
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_TRANSPARENT,
    )
    if panel is not None and dim > 0:
        x0 = int(M[0, 0] * panel["x"] + M[0, 2])
        y0 = int(M[1, 1] * panel["y"] + M[1, 2])
        x1 = int(M[0, 0] * (panel["x"] + panel["w"]) + M[0, 2])
        y1 = int(M[1, 1] * (panel["y"] + panel["h"]) + M[1, 2])
        keep = fr[max(y0, 0) : max(y1, 0), max(x0, 0) : max(x1, 0)].copy()
        fr = (fr * (1 - dim)).astype(np.uint8)
        fr[max(y0, 0) : max(y1, 0), max(x0, 0) : max(x1, 0)] = keep
    return fr


def _encoder(ffmpeg, crf):
    """Choisit le meilleur encodeur H.264 disponible (libx264, sinon matériel Mac, sinon OpenH264)."""
    try:
        enc = subprocess.run(
            [ffmpeg, "-hide_banner", "-encoders"], capture_output=True, text=True
        ).stdout
    except OSError:
        enc = ""
    if "libx264" in enc:
        return ["-c:v", "libx264", "-preset", "medium", "-crf", str(crf)]
    if "h264_videotoolbox" in enc:
        return ["-c:v", "h264_videotoolbox", "-b:v", "10M"]
    if "libopenh264" in enc:
        return ["-c:v", "libopenh264", "-b:v", "10M"]
    return ["-c:v", "mpeg4", "-q:v", "3"]


def render(pages, out, fmt="9:16", fps=30, scale=1.0, music=None, crf=20):
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("FFmpeg introuvable : installez-le (voir README).")
    W, H = (int(v * scale) // 2 * 2 for v in FORMATS[fmt])
    cmd = [
        ffmpeg,
        "-y",
        "-loglevel",
        "error",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "bgr24",
        "-s",
        f"{W}x{H}",
        "-r",
        str(fps),
        "-i",
        "-",
    ]
    if music:
        cmd += ["-i", music, "-shortest", "-c:a", "aac", "-b:a", "160k"]
    cmd += _encoder(ffmpeg, crf) + [
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        out,
    ]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    count = 0
    for page in pages:
        for fr in frames(page, fmt, fps, scale):
            proc.stdin.write(fr.tobytes())
            count += 1
    proc.stdin.close()
    proc.wait()
    if proc.returncode:
        raise RuntimeError("Échec de l'encodage FFmpeg")
    return count / fps
