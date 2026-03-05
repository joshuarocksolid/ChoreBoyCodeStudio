"""Unit tests for Designer editor surface composition."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from PySide2.QtWidgets import QApplication

from app.designer.editor_surface import DesignerEditorSurface

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module", autouse=True)
def _ensure_qapp():  # type: ignore[no-untyped-def]
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_editor_surface_loads_model_and_panels(tmp_path: Path) -> None:
    ui_file = tmp_path / "sample.ui"
    ui_file.write_text(
        (
            "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
            "<ui version=\"4.0\"><class>SampleForm</class>"
            "<widget class=\"QWidget\" name=\"SampleForm\"/>"
            "<resources/><connections/></ui>\n"
        ),
        encoding="utf-8",
    )

    surface = DesignerEditorSurface(str(ui_file.resolve()))

    assert surface.model is not None
    assert surface.model.form_class_name == "SampleForm"
    assert surface.file_path == str(ui_file.resolve())
    assert surface._validation_list.count() == 1  # type: ignore[attr-defined]
    assert "DLAYOUT001" in surface._validation_list.item(0).text()  # type: ignore[attr-defined]

    surface._selection_controller.set_selected_object_name("SampleForm")  # type: ignore[attr-defined]
    assert "Editable properties" in surface._property_summary.text()  # type: ignore[attr-defined]


def test_editor_surface_palette_insert_updates_model(tmp_path: Path) -> None:
    ui_file = tmp_path / "sample.ui"
    ui_file.write_text(
        (
            "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
            "<ui version=\"4.0\"><class>SampleForm</class>"
            "<widget class=\"QWidget\" name=\"SampleForm\"/>"
            "<resources/><connections/></ui>\n"
        ),
        encoding="utf-8",
    )

    surface = DesignerEditorSurface(str(ui_file.resolve()))
    assert surface.model is not None
    surface._handle_palette_insert_request("QPushButton")  # type: ignore[attr-defined]

    inserted = surface.model.root_widget.find_by_object_name("pushButton")
    assert inserted is not None
    assert inserted.class_name == "QPushButton"


def test_editor_surface_emits_dirty_state_on_mutation(tmp_path: Path) -> None:
    ui_file = tmp_path / "sample.ui"
    ui_file.write_text(
        (
            "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
            "<ui version=\"4.0\"><class>SampleForm</class>"
            "<widget class=\"QWidget\" name=\"SampleForm\"/>"
            "<resources/><connections/></ui>\n"
        ),
        encoding="utf-8",
    )

    surface = DesignerEditorSurface(str(ui_file.resolve()))
    states: list[bool] = []
    surface.dirty_state_changed.connect(states.append)

    surface._handle_palette_insert_request("QPushButton")  # type: ignore[attr-defined]
    assert states[-1] is True

    surface.mark_saved()
    assert states[-1] is False


def test_editor_surface_undo_redo_replays_snapshot_mutations(tmp_path: Path) -> None:
    ui_file = tmp_path / "sample.ui"
    ui_file.write_text(
        (
            "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
            "<ui version=\"4.0\"><class>SampleForm</class>"
            "<widget class=\"QWidget\" name=\"SampleForm\"/>"
            "<resources/><connections/></ui>\n"
        ),
        encoding="utf-8",
    )

    surface = DesignerEditorSurface(str(ui_file.resolve()))
    assert surface.model is not None
    assert surface.model.root_widget.find_by_object_name("pushButton") is None

    surface._handle_palette_insert_request("QPushButton")  # type: ignore[attr-defined]
    assert surface.can_undo is True
    assert surface.model.root_widget.find_by_object_name("pushButton") is not None

    assert surface.undo() is True
    assert surface.model.root_widget.find_by_object_name("pushButton") is None

    assert surface.redo() is True
    assert surface.model.root_widget.find_by_object_name("pushButton") is not None
