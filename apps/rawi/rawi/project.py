"""projet.json: versioned schema, migrations, load and save.

Version history:
- 1 (v0.1): pages > panels > bubbles; a bubble is a box {x, y, w, h, text_px}.
- 2 (M0): every bubble gets a stable id, an explicit reading order and text fields ready
  for OCR and translation (PRD §6.4). The renderer follows ``order``.
"""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Callable

CURRENT_VERSION = 2
BUBBLE_ROW_PX = 60  # bubbles whose tops are within the same 60 px band read as one row


class ProjectError(ValueError):
    """Unreadable or unsupported project file; the message is in French."""


def bubble_reading_order(bubbles: list[dict], rtl: bool) -> list[dict]:
    """v0.1 rule: rows of 60 px from top to bottom, then left→right (or right→left)."""
    sgn = -1 if rtl else 1
    return sorted(bubbles, key=lambda b: (b["y"] // BUBBLE_ROW_PX, sgn * b["x"]))


def _upgrade_bubble(b: dict, bubble_id: str, order: int) -> None:
    b.setdefault("id", bubble_id)
    b.setdefault("order", order)
    # "ocr" or "manual" once text exists; manual text is never overwritten
    b.setdefault("source", None)
    b.setdefault("text", "")
    b.setdefault("segments", [])  # [{text, script, direction}]
    b.setdefault("lang", [])
    b.setdefault("confidence", None)
    b.setdefault("translations", {})  # language -> text


def upgrade_page(page: dict, page_number: int) -> dict:
    """Give every bubble of a page the version-2 fields (in place, idempotent)."""
    rtl = bool(page.get("rtl", False))
    for c, panel in enumerate(page.get("panels", []), 1):
        ordered = bubble_reading_order(panel.get("bubbles", []), rtl)
        for k, b in enumerate(ordered, 1):
            _upgrade_bubble(b, f"p{page_number:02d}-c{c:02d}-b{k:02d}", k)
    return page


def _v1_to_v2(data: dict) -> dict:
    for n, page in enumerate(data.get("pages", []), 1):
        upgrade_page(page, n)
    data["version"] = 2
    return data


MIGRATIONS: dict[int, Callable[[dict], dict]] = {1: _v1_to_v2}


def migrate(data: dict) -> dict:
    """Bring a project dict up to CURRENT_VERSION (in place)."""
    if not isinstance(data, dict) or "pages" not in data:
        raise ProjectError(
            "Ce fichier n'est pas un projet Rawi (champ « pages » absent)."
        )
    version = data.get("version")
    if not isinstance(version, int) or version < 1:
        raise ProjectError(f"Version de projet invalide : {version!r}.")
    if version > CURRENT_VERSION:
        raise ProjectError(
            f"Ce projet a été créé par une version plus récente de Rawi (format {version}, "
            f"cette version lit jusqu'au format {CURRENT_VERSION}). Mettez Rawi à jour."
        )
    while data["version"] < CURRENT_VERSION:
        data = MIGRATIONS[data["version"]](data)
    return data


def new_project(pages: list[dict], rtl: bool) -> dict:
    for n, page in enumerate(pages, 1):
        upgrade_page(page, n)
    return {"version": CURRENT_VERSION, "rtl": rtl, "pages": pages}


def load(path: str | os.PathLike) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        raise ProjectError(f"Projet introuvable : {path}") from None
    except json.JSONDecodeError as exc:
        raise ProjectError(
            f"{path} n'est pas un JSON valide (ligne {exc.lineno}, colonne {exc.colno})."
        ) from None
    old = data.get("version") if isinstance(data, dict) else None
    data = migrate(data)
    if old != data["version"]:
        print(
            f"Projet au format {old} converti au format {data['version']} (en mémoire).",
            file=sys.stderr,
        )
    return data


def save(project: dict, path: str | os.PathLike) -> None:
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(project, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)
