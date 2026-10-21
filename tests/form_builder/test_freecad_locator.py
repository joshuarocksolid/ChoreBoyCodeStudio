"""Locator behaviour for the FreeCAD .ui corpus slice."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


def _locator():
    path = Path(__file__).resolve().parent / "corpus" / "freecad_locator.py"
    spec = importlib.util.spec_from_file_location("cbcs_freecad_locator", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("freecad_locator.py is missing")
    module = importlib.util.module_from_spec(spec)
    loader = spec.loader
    exec_module = getattr(loader, "exec_module", None)
    if exec_module is None:
        raise RuntimeError("freecad_locator.py is missing")
    exec_module(module)
    return module


@pytest.mark.unit
def test_finds_ui_files_under_given_roots(tmp_path: Path) -> None:
    locator = _locator()
    tree = tmp_path / "freecad"
    ui_dir = tree / "Mod" / "Part" / "Gui"
    ui_dir.mkdir(parents=True)
    form = ui_dir / "DlgPart.ui"
    form.write_text("<ui version='4.0'/>", encoding="utf-8")
    (ui_dir / "notes.txt").write_text("not a form", encoding="utf-8")
    nested = tree / "Mod" / "Draft" / "task.ui"
    nested.parent.mkdir(parents=True)
    nested.write_text("<ui version='4.0'/>", encoding="utf-8")

    found = locator.find_freecad_ui_files([tree, tmp_path / "missing-root"])

    assert found == sorted(str(path.resolve()) for path in (form, nested))


@pytest.mark.unit
def test_missing_roots_yield_an_empty_list(tmp_path: Path) -> None:
    locator = _locator()
    assert locator.find_freecad_ui_files([tmp_path / "nope"]) == []
