"""Tests for projet.json versions and migrations (rawi.project)."""

from __future__ import annotations

import copy
import json

import pytest
from rawi import project
from rawi.__main__ import main
from rawi.render import _ordered_bubbles

V1 = {
    "version": 1,
    "rtl": True,
    "pages": [
        {
            "image": "page.png",
            "width": 1000,
            "height": 1400,
            "rtl": True,
            "panels": [
                {
                    "id": 1,
                    "x": 0,
                    "y": 0,
                    "w": 1000,
                    "h": 700,
                    "duration": 4.0,
                    "bubbles": [
                        {
                            "x": 100,
                            "y": 130,
                            "w": 200,
                            "h": 90,
                            "text_px": 900,
                        },  # row 2
                        {
                            "x": 50,
                            "y": 20,
                            "w": 200,
                            "h": 90,
                            "text_px": 800,
                        },  # row 0, left
                        {
                            "x": 600,
                            "y": 10,
                            "w": 200,
                            "h": 90,
                            "text_px": 700,
                        },  # row 0, right
                    ],
                },
                {
                    "id": 2,
                    "x": 0,
                    "y": 700,
                    "w": 1000,
                    "h": 700,
                    "duration": 3.0,
                    "bubbles": [],
                },
            ],
        }
    ],
}


def test_migrate_v1_to_v2():
    data = project.migrate(copy.deepcopy(V1))
    assert data["version"] == project.CURRENT_VERSION == 2
    bubbles = data["pages"][0]["panels"][0]["bubbles"]
    # right-to-left page: in the top row the right bubble comes first
    by_order = sorted(bubbles, key=lambda b: b["order"])
    assert [b["x"] for b in by_order] == [600, 50, 100]
    assert [b["id"] for b in by_order] == ["p01-c01-b01", "p01-c01-b02", "p01-c01-b03"]
    for b in bubbles:
        assert b["text"] == "" and b["source"] is None and b["translations"] == {}
        assert b["text_px"] > 0  # v1 fields kept


def test_order_matches_v01_rule():
    """The renderer gives the same sequence before and after migration."""
    v1 = copy.deepcopy(V1)
    before = _ordered_bubbles(v1["pages"][0]["panels"][0]["bubbles"], rtl=True)
    after = _ordered_bubbles(
        project.migrate(v1)["pages"][0]["panels"][0]["bubbles"], rtl=True
    )
    assert [(b["x"], b["y"]) for b in before] == [(b["x"], b["y"]) for b in after]


def test_manual_order_is_followed():
    data = project.migrate(copy.deepcopy(V1))
    bubbles = data["pages"][0]["panels"][0]["bubbles"]
    for b in bubbles:
        b["order"] = {600: 3, 50: 1, 100: 2}[b["x"]]  # user reorders by hand
    assert [b["x"] for b in _ordered_bubbles(bubbles, rtl=True)] == [50, 100, 600]


def test_migrate_is_idempotent_and_keeps_edits():
    data = project.migrate(copy.deepcopy(V1))
    b = data["pages"][0]["panels"][0]["bubbles"][0]
    b.update(text="صباح الخير، ça va ?", source="manual", order=9)
    again = project.migrate(copy.deepcopy(data))
    assert again == data


@pytest.mark.parametrize(
    ("data", "message"),
    [
        ({"version": 3, "pages": []}, "plus récente"),
        ({"version": "1", "pages": []}, "invalide"),
        ({"pages": []}, "invalide"),
        ({"version": 1}, "pas un projet"),
        ([], "pas un projet"),
    ],
)
def test_migrate_errors(data, message):
    with pytest.raises(project.ProjectError, match=message):
        project.migrate(data)


def test_load_save_round_trip(tmp_path, capsys):
    path = tmp_path / "projet.json"
    path.write_text(json.dumps(V1), encoding="utf-8")
    data = project.load(path)
    assert data["version"] == 2
    assert "converti" in capsys.readouterr().err
    project.save(data, path)
    assert project.load(path) == data
    assert not list(tmp_path.glob("*.tmp"))


def test_load_errors(tmp_path):
    with pytest.raises(project.ProjectError, match="introuvable"):
        project.load(tmp_path / "absent.json")
    bad = tmp_path / "bad.json"
    bad.write_text("{oops", encoding="utf-8")
    with pytest.raises(project.ProjectError, match="JSON valide"):
        project.load(bad)


def test_cli_writes_v2_and_reports_bad_project(
    tmp_path, monkeypatch, comic_page, capsys
):
    import cv2

    monkeypatch.chdir(tmp_path)
    cv2.imwrite("page.png", comic_page(600, 800))
    main(["analyser", "page.png"])
    data = json.loads((tmp_path / "projet.json").read_text(encoding="utf-8"))
    assert data["version"] == 2
    (tmp_path / "future.json").write_text(
        json.dumps({"version": 9, "pages": []}), encoding="utf-8"
    )
    assert main(["rendre", "future.json"]) == 2
    assert "plus récente" in capsys.readouterr().err
