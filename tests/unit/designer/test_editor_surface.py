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
