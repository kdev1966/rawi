"""Rendu motion comic : caméra case par case, projecteur, « pop » des bulles.
Dépendances : numpy, OpenCV, FFmpeg (binaire)."""
import math, shutil, subprocess
import cv2
import numpy as np

FORMATS = {"9:16": (1080, 1920), "16:9": (1920, 1080), "1:1": (1080, 1080)}


def ease(t):  # ease-in-out cubique
    t = min(max(t, 0.0), 1.0)
    return 4 * t ** 3 if t < 0.5 else 1 - (-2 * t + 2) ** 3 / 2


def lerp(a, b, t):
    return tuple(x + (y - x) * t for x, y in zip(a, b))


def _background(img, W, H):
    h, w = img.shape[:2]
    s = max(W / w, H / h)
    bg = cv2.resize(img, (int(w * s) + 2, int(h * s) + 2))
    y0, x0 = (bg.shape[0] - H) // 2, (bg.shape[1] - W) // 2
    bg = bg[y0:y0 + H, x0:x0 + W]
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


def _bubble_pop(frame, img, M, b, t):
    """Petit rebond de la bulle (agrandissement 1 → 1.07 → 1)."""
    if not (0 <= t <= 0.45):
        return
    k = 1 + 0.07 * math.sin(math.pi * t / 0.45)
    x, y, w, h = b["x"], b["y"], b["w"], b["h"]
    crop = img[y:y + h, x:x + w]
    s = M[0, 0] * k
    cw, ch = max(int(w * s), 2), max(int(h * s), 2)
    crop = cv2.resize(crop, (cw, ch))
    cx = M[0, 0] * (x + w / 2) + M[0, 2]; cy = M[1, 1] * (y + h / 2) + M[1, 2]
    x0, y0 = int(cx - cw / 2), int(cy - ch / 2)
    H, W = frame.shape[:2]
    mask = np.zeros((ch, cw), np.float32)
    cv2.ellipse(mask, (cw // 2, ch // 2), (int(cw * 0.47), int(ch * 0.47)), 0, 0, 360, 1, -1)
    mask = cv2.GaussianBlur(mask, (0, 0), max(cw, ch) * 0.02 + 1)[..., None]
    fx0, fy0, fx1, fy1 = max(x0, 0), max(y0, 0), min(x0 + cw, W), min(y0 + ch, H)
    if fx1 <= fx0 or fy1 <= fy0:
        return
    c = crop[fy0 - y0:fy1 - y0, fx0 - x0:fx1 - x0].astype(np.float32)
    m = mask[fy0 - y0:fy1 - y0, fx0 - x0:fx1 - x0]
    roi = frame[fy0:fy1, fx0:fx1].astype(np.float32)
    frame[fy0:fy1, fx0:fx1] = (roi * (1 - m) + c * m).astype(np.uint8)


def frames(page, fmt="9:16", fps=30, scale=1.0):
    img = cv2.imread(page["image"])
    W, H = (int(v * scale) // 2 * 2 for v in FORMATS[fmt])
    bg = _background(img, W, H)
    shots, tr = build_shots(page)
    prev = None
    for i, shot in enumerate(shots):
        # 1) transition depuis le plan précédent
        if prev is not None:
            n = int(tr * fps)
            for f in range(n):
                t = ease((f + 1) / n)
                rect = lerp(prev["rect"], shot["rect"], t)
                M, _ = _matrix(rect, W, H, zoom=1.0 + 0.05 * (1 - t) * (prev["panel"] is not None))
                yield _compose(img, bg, M, W, H, None, 0.0)
        # 2) maintien avec léger zoom avant (Ken Burns) + projecteur + pop des bulles
        n = int(shot["hold"] * fps)
        p = shot["panel"]
        sgn = -1 if page.get("rtl") else 1
        bubbles = sorted(p["bubbles"], key=lambda b: (b["y"] // 60, sgn * b["x"])) if p else []
        for f in range(n):
            t = f / max(n - 1, 1)
            M, _ = _matrix(shot["rect"], W, H, zoom=1.0 + 0.05 * ease(t) * (p is not None))
            dim = min(f / (0.35 * fps), 1.0) * 0.6 if p else 0.0
            fr = _compose(img, bg, M, W, H, p, dim)
            sec = f / fps
            for k, b in enumerate(bubbles):
                _bubble_pop(fr, img, M, b, sec - 0.25 - k * 0.9)
            yield fr
        prev = shot


def _compose(img, bg, M, W, H, panel, dim):
    fr = bg.copy()
    cv2.warpAffine(img, M, (W, H), dst=fr, flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_TRANSPARENT)
    if panel is not None and dim > 0:
        x0 = int(M[0, 0] * panel["x"] + M[0, 2]); y0 = int(M[1, 1] * panel["y"] + M[1, 2])
        x1 = int(M[0, 0] * (panel["x"] + panel["w"]) + M[0, 2]); y1 = int(M[1, 1] * (panel["y"] + panel["h"]) + M[1, 2])
        keep = fr[max(y0, 0):max(y1, 0), max(x0, 0):max(x1, 0)].copy()
        fr = (fr * (1 - dim)).astype(np.uint8)
        fr[max(y0, 0):max(y1, 0), max(x0, 0):max(x1, 0)] = keep
    return fr


def _encoder(ffmpeg, crf):
    """Choisit le meilleur encodeur H.264 disponible (libx264, sinon matériel Mac, sinon OpenH264)."""
    try:
        enc = subprocess.run([ffmpeg, "-hide_banner", "-encoders"], capture_output=True, text=True).stdout
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
    cmd = [ffmpeg, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "bgr24",
           "-s", f"{W}x{H}", "-r", str(fps), "-i", "-"]
    if music:
        cmd += ["-i", music, "-shortest", "-c:a", "aac", "-b:a", "160k"]
    cmd += _encoder(ffmpeg, crf) + ["-pix_fmt", "yuv420p",
            "-movflags", "+faststart", out]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    count = 0
    for page in pages:
        for fr in frames(page, fmt, fps, scale):
            proc.stdin.write(fr.tobytes()); count += 1
    proc.stdin.close(); proc.wait()
    if proc.returncode:
        raise RuntimeError("Échec de l'encodage FFmpeg")
    return count / fps
