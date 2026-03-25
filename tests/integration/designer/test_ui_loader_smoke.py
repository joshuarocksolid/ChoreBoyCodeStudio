"""Integration smoke tests for loading `.ui` fixtures via QUiLoader."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)
pytest.importorskip("PySide2.QtUiTools", exc_type=ImportError)

from PySide2.QtCore import QFile, QIODevice
from PySide2.QtUiTools import QUiLoader
from PySide2.QtWidgets import QApplication, QPushButton, QScrollArea, QTabWidget, QWidget

pytestmark = pytest.mark.integration

_FIXTURE_ROOT = Path(__file__).resolve().parents[2] / "fixtures" / "designer"


@pytest.fixture
def _ensure_qapp(monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _load_ui_from_fixture(file_name: str) -> QWidget:
    loader = QUiLoader()
    file_path = _FIXTURE_ROOT / file_name
    ui_file = QFile(str(file_path))
    if not ui_file.open(QIODevice.ReadOnly):
        raise AssertionError(f"Failed to open UI fixture: {file_path}")
    try:
        widget = loader.load(ui_file, None)
    finally:
        ui_file.close()
    if widget is None:
        raise AssertionError(f"QUiLoader returned None for fixture: {file_path}")
    return widget


def test_quiloader_loads_minimal_fixture_tree(_ensure_qapp) -> None:  # type: ignore[no-untyped-def]
    widget = _load_ui_from_fixture("minimal_form.ui")
    assert widget.objectName() == "MinimalForm"
    assert widget.metaObject().className() == "QWidget"

    button = widget.findChild(QPushButton, "pushButton")
    assert button is not None
    assert button.text() == "Run"
    widget.deleteLater()


def test_quiloader_loads_layout_fixture_with_scroll_and_tabs(_ensure_qapp) -> None:  # type: ignore[no-untyped-def]
    widget = _load_ui_from_fixture("layout_form.ui")
    assert widget.objectName() == "LayoutForm"

    scroll_area = widget.findChild(QScrollArea, "scrollArea")
    tab_widget = widget.findChild(QTabWidget, "tabWidget")
    assert scroll_area is not None
    assert tab_widget is not None
    assert tab_widget.count() == 1
    assert tab_widget.tabText(0) == "General"
    widget.deleteLater()
