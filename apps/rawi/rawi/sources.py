"""Turn user inputs (images and PDF files) into a list of page image paths."""

from __future__ import annotations

import glob
import hashlib
import os
from collections.abc import Iterable

import cv2
import numpy as np

PDF_EXT = ".pdf"
DEFAULT_DPI = 300
MAX_SIDE = (
    3000  # px, longest side of a rendered page (keeps analysis time and RAM bounded)
)


class InputError(ValueError):
    """Invalid user input (page selection, unreadable PDF); the message is in French."""


def parse_pages(spec: str | None, count: int) -> list[int]:
    """Parse a 1-based page selection like "3-10,12" into 0-based indices."""
    if not spec:
        return list(range(count))
    selected: list[int] = []
    for part in spec.replace(" ", "").split(","):
        if not part:
            continue
        first, _, last = part.partition("-")
        try:
            start = int(first)
            end = int(last) if last else start
        except ValueError:
            raise InputError(
                f"Sélection de pages invalide : « {part} » (exemple : 3-10,12)"
            ) from None
        if start < 1 or end < start:
            raise InputError(
                f"Sélection de pages invalide : « {part} » (exemple : 3-10,12)"
            )
        if start > count:
            raise InputError(
                f"Page {start} demandée, mais le PDF n'a que {count} pages"
            )
        selected += [i for i in range(start - 1, min(end, count)) if i not in selected]
    return selected


def _file_hash(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _image_geometry(obj) -> tuple[tuple[float, float, float, float], tuple[int, int]]:
    """(bounds on the page in points, size in pixels) of a PDF image object.

    pypdfium2 5.x renamed get_pos() to get_bounds() and get_size() to get_px_size();
    both generations are supported (conda-forge ships 4.x for Python 3.11).
    """
    if hasattr(obj, "get_bounds"):
        return obj.get_bounds(), obj.get_px_size()
    return obj.get_pos(), obj.get_size()


def _render_scale(page, dpi: int | None) -> float:
    """Scale (pixels per PDF point) for one page.

    Without an explicit dpi, a page dominated by one image (a scan) is rendered at that
    image's native resolution, so its pixels are kept; other pages use DEFAULT_DPI.
    The longest side is capped at MAX_SIDE.
    """
    import pypdfium2.raw as pdfium_c

    width_pt, height_pt = page.get_size()
    scale = (dpi or DEFAULT_DPI) / 72
    if dpi is None:
        page_area = width_pt * height_pt
        for obj in page.get_objects(filter=[pdfium_c.FPDF_PAGEOBJ_IMAGE]):
            (left, bottom, right, top), (px_w, _) = _image_geometry(obj)
            if (right - left) * (top - bottom) >= 0.8 * page_area:
                scale = px_w / max(right - left, 1e-6)
                break
    # pypdfium2 sizes the bitmap with math.ceil(size_pt * scale): without this tiny margin,
    # float error turns 1499.0000001 into 1500 px and stretches a scan by one row.
    return min(scale, MAX_SIDE / max(width_pt, height_pt)) * (1 - 1e-6)


def render_pdf_page(page, dpi: int | None = None) -> np.ndarray:
    """Render one pypdfium2 page to an HxWx3 uint8 BGR image."""
    bitmap = page.render(scale=_render_scale(page, dpi))
    img = bitmap.to_numpy()
    mode = bitmap.mode
    if mode in ("BGRA", "BGRX"):
        img = img[:, :, :3]
    elif mode in ("RGBA", "RGBX"):
        img = cv2.cvtColor(img[:, :, :3], cv2.COLOR_RGB2BGR)
    elif mode == "RGB":
        img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
    elif mode == "L":
        img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    return np.ascontiguousarray(img)


def pdf_to_images(
    path: str, out_dir: str, pages: str | None = None, dpi: int | None = None
) -> list[str]:
    """Render the selected pages of a PDF to PNG files and return their paths.

    Files go to ``out_dir/<name>-<hash8>/`` and are reused while the PDF and the dpi stay the same.
    """
    import pypdfium2 as pdfium

    stem = os.path.splitext(os.path.basename(path))[0]
    tag = f"{stem}-{_file_hash(path)[:8]}" + (f"-{dpi}dpi" if dpi else "")
    folder = os.path.join(out_dir, tag)
    os.makedirs(folder, exist_ok=True)

    try:
        pdf = pdfium.PdfDocument(path)
    except pdfium.PdfiumError as exc:
        raise InputError(f"Impossible d'ouvrir le PDF « {path} » : {exc}") from None
    try:
        indices = parse_pages(pages, len(pdf))
        outputs = []
        for n, index in enumerate(indices, 1):
            target = os.path.join(folder, f"p{index + 1:03d}.png")
            if os.path.exists(target):
                status = "déjà extraite"
            else:
                page = pdf[index]
                try:
                    img = render_pdf_page(page, dpi)
                finally:
                    page.close()
                tmp = target + ".tmp.png"
                cv2.imwrite(tmp, img)
                os.replace(tmp, target)  # never leave a half-written page in the cache
                status = f"{img.shape[1]}×{img.shape[0]} px"
            print(
                f"  {os.path.basename(path)} page {index + 1} ({n}/{len(indices)}) : {status}"
            )
            outputs.append(target)
        return outputs
    finally:
        pdf.close()


def expand_inputs(
    patterns: Iterable[str],
    pages_dir: str = "pages",
    pages: str | None = None,
    dpi: int | None = None,
) -> list[str]:
    """Expand globs; images are kept as is, PDF files are replaced by their rendered pages."""
    out: list[str] = []
    for pattern in patterns:
        for path in sorted(glob.glob(pattern)) or [pattern]:
            if path.lower().endswith(PDF_EXT):
                out += pdf_to_images(path, pages_dir, pages=pages, dpi=dpi)
            else:
                out.append(path)
    return out
