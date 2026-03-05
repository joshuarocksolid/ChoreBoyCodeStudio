"""Unit tests for designer selection controller."""

from __future__ import annotations

import pytest

pytest.importorskip("PySide2.QtCore", exc_type=ImportError)

from app.designer.canvas.selection_controller import SelectionController

pytestmark = pytest.mark.unit


def test_selection_controller_emits_on_change() -> None:
    controller = SelectionController()
    seen: list[str] = []
    controller.selection_changed.connect(seen.append)

    controller.set_selected_object_name("buttonOne")
    controller.set_selected_object_name("buttonOne")
    controller.set_selected_object_name("buttonTwo")
    controller.set_selected_object_name(None)

    assert seen == ["buttonOne", "buttonTwo", ""]


def test_selection_controller_tracks_multi_selection_set() -> None:
    controller = SelectionController()
    seen: list[list[str]] = []
    controller.selection_set_changed.connect(seen.append)

    controller.set_selected_object_names(["buttonOne", "buttonTwo", "buttonOne"])
    assert controller.selected_object_name == "buttonOne"
    assert controller.selected_object_names == ["buttonOne", "buttonTwo"]
    controller.set_selected_object_names([])

    assert seen == [["buttonOne", "buttonTwo"], []]
