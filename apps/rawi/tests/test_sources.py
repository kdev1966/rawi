"""Tests for PDF and image inputs (rawi.sources)."""

from __future__ import annotations

import json
import os
from pathlib import Path

import cv2
import numpy as np
import pypdfium2 as pdfium
import pytest

from rawi import sources
from rawi.__main__ import main

QAHWATI = Path(__file__).parent / "fixtures" / "qahwati"


def comic_page(w: int = 1200, h: int = 1600) -> np.ndarray:
    """Synthetic BGR page: white background, 2x2 framed panels with some drawing."""
    img = np.full((h, w, 3), 255, np.uint8)
    margin, gutter = 40, 40
    pw, ph = (w - 2 * margin - gutter) // 2, (h - 2 * margin - gutter) // 2
    rng = np.random.default_rng(0)
    for row in range(2):
        for col in range(2):
            x, y = margin + col * (pw + gutter), margin + row * (ph + gutter)
            cv2.rectangle(img, (x, y), (x + pw, y + ph), (0, 0, 0), 6)
            for _ in range(12):
                c = tuple(int(v) for v in rng.integers(0, 200, 3))
                p = (
                    int(x + rng.integers(20, pw - 20)),
                    int(y + rng.integers(20, ph - 20)),
                )
                cv2.circle(img, p, int(rng.integers(10, 60)), c, -1)
    return img


def make_scan_pdf(
    path: Path, pages: list[np.ndarray | Path], page_pt: tuple[float, float]
) -> None:
    """PDF where each page is one JPEG image covering the whole page (like a scan).

    A Path is embedded as is (original JPEG bytes); an array is first encoded to JPEG.
    """
    pdf = pdfium.PdfDocument.new()
    for i, img in enumerate(pages):
        if isinstance(img, Path):
            jpg = img
        else:
            jpg = path.with_name(f"{path.stem}_{i}.jpg")
            cv2.imwrite(str(jpg), img, [cv2.IMWRITE_JPEG_QUALITY, 95])
        page = pdf.new_page(*page_pt)
        obj = pdfium.PdfImage.new(pdf)
        obj.load_jpeg(str(jpg), pages=[page])
        obj.set_matrix(pdfium.PdfMatrix().scale(*page_pt))
        page.insert_obj(obj)
        page.gen_content()
    pdf.save(str(path))
    pdf.close()


def make_blank_pdf(path: Path, page_pt: tuple[float, float], count: int = 1) -> None:
    pdf = pdfium.PdfDocument.new()
    for _ in range(count):
        pdf.new_page(*page_pt)
    pdf.save(str(path))
    pdf.close()


# --- page selection -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("spec", "expected"),
    [
        (None, [0, 1, 2, 3, 4]),
        ("2", [1]),
        ("2-4", [1, 2, 3]),
        ("1,3-4", [0, 2, 3]),
        ("4-9", [3, 4]),
        ("2,2", [1]),
    ],
)
def test_parse_pages(spec, expected):
    assert sources.parse_pages(spec, 5) == expected


@pytest.mark.parametrize("spec", ["0", "3-2", "a", "6", "2-x"])
def test_parse_pages_errors(spec):
    with pytest.raises(sources.InputError):
        sources.parse_pages(spec, 5)


# --- rendering ----------------------------------------------------------------------


def test_scan_rendered_at_native_resolution(tmp_path):
    page = comic_page(900, 1200)
    pdf = tmp_path / "scan.pdf"
    make_scan_pdf(pdf, [page], (540, 720))  # 900 px on 540 pt -> 120 dpi
    [out] = sources.pdf_to_images(str(pdf), str(tmp_path / "pages"))
    img = cv2.imread(out)
    assert img.shape == (1200, 900, 3)  # exact size: no extra row from rounding
    assert (
        float(np.abs(img.astype(int) - page.astype(int)).mean()) < 3.0
    )  # JPEG noise only


def test_digital_page_uses_default_dpi(tmp_path):
    pdf = tmp_path / "digital.pdf"
    make_blank_pdf(pdf, (144, 72))  # 2 x 1 inch
    [out] = sources.pdf_to_images(str(pdf), str(tmp_path / "pages"))
    assert cv2.imread(out).shape[:2] == (300, 600)


def test_explicit_dpi_and_size_cap(tmp_path):
    pdf = tmp_path / "big.pdf"
    make_blank_pdf(pdf, (1440, 720))  # 20 x 10 inch
    [out] = sources.pdf_to_images(str(pdf), str(tmp_path / "pages"), dpi=72)
    assert cv2.imread(out).shape[:2] == (720, 1440)
    [out] = sources.pdf_to_images(
        str(pdf), str(tmp_path / "pages")
    )  # 300 dpi would be 6000 px
    assert max(cv2.imread(out).shape[:2]) == sources.MAX_SIDE


def test_page_selection_and_cache(tmp_path):
    pdf = tmp_path / "album.pdf"
    make_blank_pdf(pdf, (72, 72), count=5)
    outs = sources.pdf_to_images(str(pdf), str(tmp_path / "pages"), pages="2,4-5")
    assert [os.path.basename(p) for p in outs] == ["p002.png", "p004.png", "p005.png"]
    mtimes = [os.path.getmtime(p) for p in outs]
    again = sources.pdf_to_images(str(pdf), str(tmp_path / "pages"), pages="2,4-5")
    assert again == outs and [os.path.getmtime(p) for p in again] == mtimes
    assert not list((tmp_path / "pages").rglob("*.tmp.png"))


def test_unreadable_pdf(tmp_path):
    bad = tmp_path / "bad.pdf"
    bad.write_bytes(b"not a pdf")
    with pytest.raises(sources.InputError):
        sources.pdf_to_images(str(bad), str(tmp_path / "pages"))


def test_expand_inputs_mixes_images_and_pdfs(tmp_path):
    img = tmp_path / "a.png"
    cv2.imwrite(str(img), comic_page(300, 400))
    pdf = tmp_path / "b.pdf"
    make_blank_pdf(pdf, (72, 72), count=2)
    outs = sources.expand_inputs([str(img), str(pdf)], str(tmp_path / "pages"))
    assert outs[0] == str(img) and len(outs) == 3


# --- end to end ---------------------------------------------------------------------


def test_cli_analyser_on_pdf(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    make_scan_pdf(tmp_path / "album.pdf", [comic_page(), comic_page()], (600, 800))
    assert main(["analyser", "album.pdf", "--pages", "2"]) in (None, 0)
    projet = json.loads((tmp_path / "projet.json").read_text(encoding="utf-8"))
    assert len(projet["pages"]) == 1
    assert len(projet["pages"][0]["panels"]) == 4


def test_cli_reports_bad_page_selection(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    make_blank_pdf(tmp_path / "album.pdf", (72, 72))
    assert main(["analyser", "album.pdf", "--pages", "3"]) == 2
    assert "Erreur" in capsys.readouterr().err


@pytest.mark.skipif(
    not QAHWATI.is_dir(), reason="planches Qahwati absentes (privées, hors git)"
)
@pytest.mark.parametrize("n", range(1, 9))
def test_qahwati_scan_pdf_is_lossless(tmp_path, n):
    """A Qahwati page embedded in a PDF (original JPEG bytes) comes back pixel-identical."""
    from rawi.analyze import analyze

    src = QAHWATI / f"planche{n}.jpg"
    page = cv2.imread(str(src))
    h, w = page.shape[:2]
    make_scan_pdf(tmp_path / "q.pdf", [src], (w * 72 / 150, h * 72 / 150))
    [out] = sources.pdf_to_images(str(tmp_path / "q.pdf"), str(tmp_path / "pages"))
    assert np.array_equal(cv2.imread(out), page)
    boxes = lambda p: [(c["x"], c["y"], c["w"], c["h"]) for c in p["panels"]]  # noqa: E731
    assert boxes(analyze(out)) == boxes(analyze(str(src)))
