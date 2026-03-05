"""Integration tests for object inspector reparent flow through designer surface."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from PySide2.QtWidgets import QApplication

from app.designer.editor_surface import DesignerEditorSurface

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module", autouse=True)
def _ensure_qapp():  # type: ignore[no-untyped-def]
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_surface_reparent_moves_widget_and_supports_undo(tmp_path: Path) -> None:
    ui_file = tmp_path / "reparent.ui"
    ui_file.write_text(
        (
            "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
            "<ui version=\"4.0\"><class>ReparentForm</class>"
            "<widget class=\"QWidget\" name=\"ReparentForm\">"
            "<widget class=\"QPushButton\" name=\"sourceButton\"/>"
            "<widget class=\"QGroupBox\" name=\"targetGroup\"/>"
            "</widget>"
            "<resources/><connections/></ui>\n"
        ),
        encoding="utf-8",
    )
    surface = DesignerEditorSurface(str(ui_file.resolve()))

    assert surface._handle_inspector_reparent_request("sourceButton", "targetGroup") is True  # type: ignore[attr-defined]
    assert surface.can_undo is True
    target = surface.model.root_widget.find_by_object_name("targetGroup")  # type: ignore[union-attr]
    assert target is not None
    assert [child.object_name for child in target.children] == ["sourceButton"]

    assert surface.undo() is True
    target_after_undo = surface.model.root_widget.find_by_object_name("targetGroup")  # type: ignore[union-attr]
    assert target_after_undo is not None
    assert target_after_undo.children == []


def test_surface_reparent_rejects_invalid_target(tmp_path: Path) -> None:
    ui_file = tmp_path / "invalid_reparent.ui"
    ui_file.write_text(
        (
            "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
            "<ui version=\"4.0\"><class>ReparentForm</class>"
            "<widget class=\"QWidget\" name=\"ReparentForm\">"
            "<widget class=\"QPushButton\" name=\"sourceButton\"/>"
            "<widget class=\"QLineEdit\" name=\"lineEdit\"/>"
            "</widget>"
            "<resources/><connections/></ui>\n"
        ),
        encoding="utf-8",
    )
    surface = DesignerEditorSurface(str(ui_file.resolve()))
    assert surface._handle_inspector_reparent_request("sourceButton", "lineEdit") is False  # type: ignore[attr-defined]
